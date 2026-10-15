"""Local HTTP server transport bound strictly to 127.0.0.1 with Bearer token authentication."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pathlib
import threading
from typing import Any, Dict, Optional

from .queue_manager import queue_manager
from .security import (
    audit_logger,
    generate_session_token,
    remove_session_file,
    write_session_file,
)

logger = logging.getLogger("blenderagent_bridge.server")


class BridgeHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler servicing BlenderAgent Bridge API endpoints."""

    server_token: str = ""
    workspace_dir: pathlib.Path = pathlib.Path(".")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default stderr HTTP request logging to avoid terminal clutter."""
        pass

    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200) -> None:
        try:
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests strictly for localhost."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Health check and diagnostic endpoint."""
        if self.path == "/api/v1/health":
            self._send_json_response({
                "status": "healthy",
                "service": "blenderagent-bridge",
                "version": "0.1.0",
                "active_tasks": audit_logger.total_count,
            })
            return

        self._send_json_response({
            "status": "error",
            "error": {"code": "NOT_FOUND", "message": f"Endpoint '{self.path}' not found."},
            "message": "Resource not found.",
        }, status_code=404)

    def do_POST(self) -> None:
        """Process API commands dispatched to Blender's main thread."""
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        # 1. Enforce localhost origin
        if client_ip not in ("127.0.0.1", "localhost", "::1"):
            audit_logger.log("UNAUTHORIZED_IP", "BLOCKED", f"Rejected remote connection attempt from {client_ip}", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "FORBIDDEN",
                    "message": "BlenderAgent Bridge only accepts connections from localhost (127.0.0.1).",
                },
                "message": "Access denied.",
            }, status_code=403)
            return

        # 2. Enforce Bearer Token Authentication
        auth_header = self.headers.get("Authorization", "")
        expected_header = f"Bearer {self.server_token}"
        if not auth_header or auth_header.strip() != expected_header:
            audit_logger.log("AUTH_FAILURE", "REJECTED", "Missing or invalid Bearer token", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing Bearer authorization token.",
                },
                "message": "Unauthorized: Session token required.",
            }, status_code=401)
            return

        if self.path != "/api/v1/command":
            self._send_json_response({
                "status": "error",
                "error": {"code": "NOT_FOUND", "message": f"Endpoint '{self.path}' not found."},
                "message": "Resource not found.",
            }, status_code=404)
            return

        # 3. Read and parse JSON payload
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0 or content_length > 10 * 1024 * 1024:  # 10MB limit
                raise ValueError("Invalid Content-Length or payload exceeds 10MB limit.")

            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as parse_err:
            audit_logger.log("BAD_REQUEST", "ERROR", f"Invalid JSON payload: {parse_err}", client_ip)
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "INVALID_JSON",
                    "message": f"Failed to parse request JSON: {parse_err}",
                },
                "message": "Bad Request: Malformed JSON.",
            }, status_code=400)
            return

        command_name = payload.get("command")
        if not command_name or not isinstance(command_name, str):
            self._send_json_response({
                "status": "error",
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": "Request must contain a valid string 'command' field.",
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

        # Inject server-authorized workspace directory
        params["workspace_dir"] = str(self.workspace_dir)

        request_id = payload.get("request_id")
        timeout = float(payload.get("timeout", 30.0))

        # 4. Dispatch to thread-safe execution queue
        response_dict = queue_manager.submit_task(
            command_name=command_name,
            params=params,
            timeout=timeout,
            request_id=request_id,
        )

        # 5. Return standardized response
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
            elif err_code == "BRIDGE_UNAVAILABLE":
                status_code = 503

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
            BridgeHTTPRequestHandler.workspace_dir = self._workspace

            try:
                # Bind strictly to 127.0.0.1 IPv4 loopback
                self._httpd = ThreadingHTTPServer(("127.0.0.1", self._port), BridgeHTTPRequestHandler)
            except OSError as err:
                audit_logger.log("SERVER_START", "FAILED", f"Cannot bind to 127.0.0.1:{self._port}: {err}")
                return False, f"Failed to bind port {self._port}: {err}"

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

            # Write session file in workspace
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
        remove_session_file(self._workspace)
        audit_logger.log("SERVER_STOP", "INACTIVE", "Bridge stopped cleanly.")

        return True, "BlenderAgent Bridge stopped."


# Global server instance
bridge_server = BlenderAgentServer()
