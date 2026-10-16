"""Local HTTP server transport bound strictly to 127.0.0.1 with hardened authentication and security."""

from __future__ import annotations

import json
import logging
import math
import os
import pathlib
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import sys
import threading
from typing import Any, Dict, Optional, Tuple
import urllib.parse

from .queue_manager import queue_manager
from .security import (
    audit_logger,
    generate_session_token,
    remove_session_file,
    write_session_file,
)

logger = logging.getLogger("blenderagent_bridge.server")


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Threading HTTPServer enforcing exclusive socket binding to prevent port collisions on Windows."""
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == "win32":
            try:
                # SO_EXCLUSIVEADDRUSE (-5) guarantees no other process can share or hijack the port
                opt = getattr(socket, "SO_EXCLUSIVEADDRUSE", -5)
                self.socket.setsockopt(socket.SOL_SOCKET, opt, 1)
            except Exception:
                pass
        super().server_bind()


class BridgeHTTPRequestHandler(BaseHTTPRequestHandler):
    """Hardened HTTP Request Handler servicing BlenderAgent Bridge API endpoints."""

    server_token: str = ""
    server_port: int = 9876
    workspace_dir: pathlib.Path = pathlib.Path(".")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr HTTP request logging to avoid terminal clutter."""
        pass

    def setup(self) -> None:
        super().setup()
        self._body_read = False

    def _drain_request_body(self) -> None:
        """Safely drain unread request body so socket close does not RST on Windows."""
        if getattr(self, "_body_read", False):
            return
        self._body_read = True
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                to_read = min(length, 1024 * 1024)
                self.rfile.read(to_read)
        except Exception:
            pass

    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200) -> None:
        try:
            self._drain_request_body()
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{self.server_port}")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Idempotency-Key")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests strictly for localhost."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{self.server_port}")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Idempotency-Key")
        self.end_headers()

    def _validate_client_and_headers(self) -> bool:
        """Validate client IP, Host header, and Origin header."""
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        # 1. Enforce localhost origin
        if client_ip not in ("127.0.0.1", "localhost", "::1"):
            audit_logger.log("FORBIDDEN_IP", "BLOCKED", f"Rejected remote attempt from {client_ip}", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "FORBIDDEN",
                    "message": "BlenderAgent Bridge only accepts connections from localhost (127.0.0.1).",
                },
                "message": "Access denied.",
            }, status_code=403)
            return False

        # 2. Host header verification (DNS Rebinding defense)
        host_header = self.headers.get("Host", "").split(":")[0].lower()
        if host_header not in ("127.0.0.1", "localhost", "::1"):
            audit_logger.log("FORBIDDEN_HOST", "BLOCKED", f"Rejected Host: '{host_header}'", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "FORBIDDEN_HOST",
                    "message": f"Invalid Host '{host_header}'. Requests must target 127.0.0.1 or localhost.",
                },
                "message": "Access denied: Host validation failed.",
            }, status_code=403)
            return False

        # 3. Origin header check (against CSRF from local browsers)
        origin_header = self.headers.get("Origin")
        if origin_header and origin_header != "null":
            is_valid_origin = False
            try:
                parsed_origin = urllib.parse.urlsplit(origin_header)
                if parsed_origin.scheme in ("http", "https"):
                    if parsed_origin.hostname in ("127.0.0.1", "localhost"):
                        if parsed_origin.port is None or parsed_origin.port == self.server_port:
                            is_valid_origin = True
            except Exception:
                is_valid_origin = False

            if not is_valid_origin:
                audit_logger.log("CSRF_BLOCKED", "BLOCKED", f"Rejected Origin: '{origin_header}'", client_ip)
                self._send_json_response({
                    "status": "error",
                    "error": {
                        "code": "FORBIDDEN_ORIGIN",
                        "message": f"Cross-origin access from '{origin_header}' is prohibited.",
                    },
                    "message": "Access denied: Origin untrusted.",
                }, status_code=403)
                return False

        return True

    @classmethod
    def _read_session_token_from_disk(cls) -> Optional[str]:
        """Attempt to read token from workspace or global live session file on disk, validating metadata."""
        current_pid = os.getpid()
        current_port = getattr(cls, "server_port", None)
        current_ws = getattr(cls, "workspace_dir", None)

        candidates = []
        if current_ws:
            candidates.append((pathlib.Path(current_ws) / ".blenderagent_session.json", True))
        try:
            from .security import get_global_session_file
            candidates.append((get_global_session_file(), False))
        except Exception:
            pass

        for p, is_local in candidates:
            if p and p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    tok = data.get("token")
                    if not tok or not isinstance(tok, str) or len(tok) != 32:
                        continue

                    file_port = data.get("port")
                    file_pid = data.get("pid")

                    if is_local:
                        if current_port and file_port and file_port != current_port:
                            continue
                        return tok
                    else:
                        # Global session file MUST match this instance's PID and port
                        if file_pid == current_pid and (current_port is None or file_port == current_port):
                            return tok
                except Exception:
                    pass
        return None

    def _verify_auth_token(self) -> bool:
        """Verify Bearer token using constant-time comparison with dynamic session reload."""
        auth_header = self.headers.get("Authorization", "").strip()
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        if not auth_header.startswith("Bearer "):
            audit_logger.log("AUTH_FAILURE", "REJECTED", "Missing Bearer token", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing Bearer authorization token header.",
                },
                "message": "Unauthorized.",
            }, status_code=401)
            return False

        token_candidate = auth_header[7:].strip()
        if not token_candidate:
            audit_logger.log("AUTH_FAILURE", "REJECTED", "Empty Bearer token", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid authentication token.",
                },
                "message": "Unauthorized: Access token rejected.",
            }, status_code=401)
            return False

        # 1. Match current in-memory server token
        if self.server_token and secrets.compare_digest(token_candidate, self.server_token):
            return True

        # 2. Dynamic reload fallback: Check if session file on disk has updated token
        disk_token = self._read_session_token_from_disk()
        if disk_token and secrets.compare_digest(token_candidate, disk_token):
            BridgeHTTPRequestHandler.server_token = disk_token
            return True

        audit_logger.log("AUTH_FAILURE", "REJECTED", "Incorrect Bearer token", client_ip)
        self._send_json_response({
            "status": "error",
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Invalid authentication token.",
            },
            "message": "Unauthorized: Access token rejected.",
        }, status_code=401)
        return False

    def do_GET(self) -> None:
        """Health check and task diagnostic endpoint."""
        if not self._validate_client_and_headers():
            return

        if self.path == "/api/v1/health":
            self._send_json_response({
                "status": "healthy",
                "service": "blenderagent-bridge",
                "version": "0.2.1",
                "active_tasks": queue_manager.active_count,
                "processed_total": audit_logger.total_count,
            })
            return

        # Task status query: /api/v1/tasks/<task_id>
        if self.path.startswith("/api/v1/tasks/"):
            if not self._verify_auth_token():
                return
            task_id = self.path[len("/api/v1/tasks/"):].strip()
            task = queue_manager.get_task(task_id)
            if not task:
                self._send_json_response({
                    "status": "error",
                    "error": {"code": "TASK_NOT_FOUND", "message": f"Task '{task_id}' not found."},
                    "message": "Task not found.",
                }, status_code=404)
                return

            self._send_json_response({
                "status": "success",
                "data": task.to_info_dict(),
                "message": f"Task status: {task.status.value}",
            })
            return

        self._send_json_response({
            "status": "error",
            "error": {"code": "NOT_FOUND", "message": f"Endpoint '{self.path}' not found."},
            "message": "Resource not found.",
        }, status_code=404)

    def do_POST(self) -> None:
        """Process API commands and task cancellations."""
        if not self._validate_client_and_headers():
            return

        if not self._verify_auth_token():
            return

        # Task cancellation: POST /api/v1/tasks/<task_id>/cancel
        if self.path.startswith("/api/v1/tasks/") and self.path.endswith("/cancel"):
            task_id = self.path[len("/api/v1/tasks/"): -len("/cancel")].strip()
            success, msg = queue_manager.cancel_task(task_id)
            status_code = 200 if success else 400
            self._send_json_response({
                "status": "success" if success else "error",
                "message": msg,
                "data": {"task_id": task_id, "cancelled": success},
            }, status_code=status_code)
            return

        if self.path != "/api/v1/command":
            self._send_json_response({
                "status": "error",
                "error": {"code": "NOT_FOUND", "message": f"Endpoint '{self.path}' not found."},
                "message": "Resource not found.",
            }, status_code=404)
            return

        # Validate Content-Type
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "INVALID_CONTENT_TYPE",
                    "message": f"Content-Type must be 'application/json', got '{content_type}'.",
                },
                "message": "Unsupported Media Type.",
            }, status_code=415)
            return

        # Read and parse JSON payload
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0 or content_length > 5 * 1024 * 1024:  # 5MB limit
                raise ValueError("Payload size must be between 1 byte and 5MB.")

            self._body_read = True
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as parse_err:
            audit_logger.log("BAD_REQUEST", "ERROR", f"Malformed payload: {parse_err}", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "INVALID_JSON",
                    "message": f"Failed to parse JSON body: {parse_err}",
                },
                "message": "Bad Request: Malformed JSON.",
            }, status_code=400)
            return

        if not isinstance(payload, dict):
            audit_logger.log("BAD_REQUEST", "ERROR", "Payload is not a JSON object", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "INVALID_JSON",
                    "message": "Request payload must be a JSON object.",
                },
                "message": "Bad Request: JSON object expected.",
            }, status_code=400)
            return

        command_name = payload.get("command")
        if not command_name or not isinstance(command_name, str):
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": "Field 'command' must be a non-empty string.",
                },
                "message": "Bad Request: Missing command.",
            }, status_code=400)
            return

        params = payload.get("params", {})
        if not isinstance(params, dict):
            params = {}

        # SECURITY: Strictly reject any client attempt to supply or override workspace_dir
        if "workspace_dir" in params:
            audit_logger.log(
                "SECURITY_VIOLATION",
                "BLOCKED",
                "Client attempted to supply custom workspace_dir in request parameters.",
                client_ip,
            )
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "SECURITY_VIOLATION",
                    "message": "Specifying 'workspace_dir' in request parameters is strictly prohibited.",
                },
                "message": "Security Violation: workspace_dir is governed exclusively by the server.",
                "request_id": payload.get("request_id"),
            }, status_code=403)
            return

        # Inject authoritative server workspace directory
        params["workspace_dir"] = str(self.workspace_dir)

        request_id = payload.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            request_id = str(request_id)

        try:
            raw_timeout = payload.get("timeout", 30.0)
            timeout = float(raw_timeout)
            if math.isnan(timeout) or math.isinf(timeout) or timeout <= 0:
                raise ValueError("Timeout must be a positive finite number.")
            timeout = min(timeout, 300.0)
        except Exception as timeout_err:
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": f"Field 'timeout' must be a positive finite number: {timeout_err}",
                },
                "message": "Bad Request: Invalid timeout.",
                "request_id": request_id,
            }, status_code=400)
            return

        idempotency_key = payload.get("idempotency_key") or self.headers.get("Idempotency-Key")
        if idempotency_key is not None and not isinstance(idempotency_key, str):
            idempotency_key = str(idempotency_key)

        # Dispatch to thread-safe execution queue
        response_dict = queue_manager.submit_task(
            command_name=command_name,
            params=params,
            timeout=timeout,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )

        status_code = 200
        if response_dict.get("status") == "error":
            err_code = response_dict.get("error", {}).get("code", "")
            if err_code in ("UNAUTHORIZED", "SECURITY_VIOLATION"):
                status_code = 403
            elif err_code == "OBJECT_NOT_FOUND":
                status_code = 404
            elif err_code == "ALREADY_EXISTS":
                status_code = 409
            elif err_code == "EXECUTION_TIMEOUT":
                status_code = 504
            elif err_code in ("BRIDGE_UNAVAILABLE", "QUEUE_FULL"):
                status_code = 503
            elif err_code == "INVALID_ARGUMENT":
                status_code = 400

        self._send_json_response(response_dict, status_code=status_code)


class BlenderAgentServer:
    """Server lifecycle controller for BlenderAgent Bridge."""

    def __init__(self):
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._token: str = ""
        self._port: int = 9876
        self._workspace: pathlib.Path = pathlib.Path.cwd()
        self._is_running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def port(self) -> int:
        return self._port

    @property
    def token(self) -> str:
        return self._token

    @property
    def workspace(self) -> pathlib.Path:
        return self._workspace

    def start(
        self,
        port: int = 9876,
        token: Optional[str] = None,
        workspace_dir: Optional[str | pathlib.Path] = None,
    ) -> Tuple[bool, str]:
        """Start the HTTP server on 127.0.0.1:<port> and register main thread timer."""
        with self._lock:
            if self._is_running:
                return True, f"Bridge already running on port {self._port}."

            self._port = port
            self._token = token or generate_session_token()
            self._workspace = pathlib.Path(workspace_dir or pathlib.Path.cwd()).resolve()
            self._workspace.mkdir(parents=True, exist_ok=True)

            BridgeHTTPRequestHandler.server_token = self._token
            BridgeHTTPRequestHandler.server_port = self._port
            BridgeHTTPRequestHandler.workspace_dir = self._workspace

            try:
                # Bind strictly to 127.0.0.1 IPv4 loopback exclusively
                self._httpd = ExclusiveThreadingHTTPServer(("127.0.0.1", self._port), BridgeHTTPRequestHandler)
            except OSError as err:
                audit_logger.log("SERVER_START", "FAILED", f"Cannot bind to 127.0.0.1:{self._port}: {err}")
                return False, f"Failed to bind port {self._port} (port already in use by another instance): {err}"

            # Start main thread queue consumer
            queue_manager.start()

            # Start HTTP listener thread
            self._thread = threading.Thread(
                target=self._httpd.serve_forever,
                name="BlenderAgent_HTTP_Server",
                daemon=True,
            )
            self._thread.start()
            self._is_running = True

            # Write protected session file in workspace
            write_session_file(self._token, self._port, self._workspace)
            audit_logger.log("SERVER_START", "ACTIVE", f"Listening on 127.0.0.1:{self._port}")

            return True, f"BlenderAgent Bridge started on 127.0.0.1:{self._port}."

    def stop(self) -> Tuple[bool, str]:
        """Stop HTTP server, stop queue timer, and remove session metadata."""
        with self._lock:
            if not self._is_running:
                return True, "Bridge is not running."

            self._is_running = False

        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None

        self._thread = None

        # Stop queue manager timer
        queue_manager.stop()

        # Remove session file
        remove_session_file(self._workspace, pid=os.getpid(), port=self._port)
        audit_logger.log("SERVER_STOP", "INACTIVE", "Bridge stopped cleanly.")

        return True, "BlenderAgent Bridge stopped."


# Global server instance
bridge_server = BlenderAgentServer()
