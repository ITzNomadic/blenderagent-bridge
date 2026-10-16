"""HTTP client communicating with the in-Blender bridge server."""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import sys
import time
from typing import Any, Dict, Optional, Set

import httpx

from .models import ErrorDetail, ResponseEnvelope


class BlenderBridgeClient:
    """Manages resilient HTTP RPC communication with BlenderAgent Bridge."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9876,
        token: str = "",
        workspace_dir: Optional[pathlib.Path] = None,
    ):
        self.host = host
        self.port = port
        self.token = token
        self.workspace_dir = workspace_dir
        self._explicit_port = port != 9876 or "BLENDERAGENT_PORT" in os.environ
        self._rejected_tokens: Set[str] = set()

    def _discover_session(self, force: bool = False) -> bool:
        """Dynamically load port and token from live session or workspace file."""
        if self.token and not force and self.token not in self._rejected_tokens:
            return True

        candidates = []
        # 1. Global live session file
        try:
            local_appdata = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData" / "Local"))
            candidates.append(local_appdata / "BlenderAgentBridge" / "live_session.json")
        except Exception:
            pass

        # 2. Workspace session file
        if self.workspace_dir:
            candidates.append(self.workspace_dir / ".blenderagent_session.json")

        # 3. Fallback to default workspace
        try:
            default_ws = local_appdata / "BlenderAgentBridge" / "workspace" / ".blenderagent_session.json"
            candidates.append(default_ws)
        except Exception:
            pass

        for path in candidates:
            if not path or not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tok = data.get("token", "")
                if not tok or tok in self._rejected_tokens:
                    continue

                if self._explicit_port:
                    file_port = int(data.get("port", self.port))
                    if file_port != self.port:
                        continue

                self.token = tok
                self.port = int(data.get("port", self.port))
                return True
            except Exception:
                pass
        return bool(self.token and self.token not in self._rejected_tokens)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def check_health(self) -> bool:
        """Check if Blender bridge HTTP endpoint is alive."""
        self._discover_session()
        try:
            with httpx.Client(timeout=2.0, trust_env=False) as client:
                res = client.get(
                    f"{self.base_url}/api/v1/health",
                    headers={"Accept-Encoding": "identity"},
                )
                return res.status_code == 200
        except Exception:
            try:
                import http.client
                conn = http.client.HTTPConnection(self.host, self.port, timeout=2.0)
                conn.request("GET", "/api/v1/health")
                r = conn.getresponse()
                status = r.status
                conn.close()
                return status == 200
            except Exception:
                return False

    def _execute_raw_fallback(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        timeout: float,
    ) -> ResponseEnvelope:
        """Fallback to standard library http.client to completely bypass proxy and decompression issues."""
        import http.client
        import json

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Content-Length": str(len(body)),
            "Accept-Encoding": "identity",
        }
        conn = None
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
            conn.request("POST", endpoint, body=body, headers=headers)
            res = conn.getresponse()
            raw_text = res.read().decode("utf-8", errors="replace")
            raw_json = json.loads(raw_text)
            return ResponseEnvelope.model_validate(raw_json)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def send_command(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 35.0,
    ) -> ResponseEnvelope:
        """Send a command payload to the BlenderAgent Bridge with transparent 401 re-authentication."""
        self._discover_session()

        payload = {
            "command": command,
            "params": params or {},
            "request_id": f"req-{int(time.time() * 1000)}",
            "timeout": timeout - 2.0,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Accept-Encoding": "identity",
        }

        try:
            with httpx.Client(timeout=timeout, trust_env=False) as client:
                res = client.post(
                    f"{self.base_url}/api/v1/command",
                    json=payload,
                    headers=headers,
                )

                # Automatic recovery on 401: Token rotated or out-of-sync
                if res.status_code == 401:
                    if self.token:
                        self._rejected_tokens.add(self.token)
                    self.token = ""
                    if self._discover_session(force=True):
                        headers["Authorization"] = f"Bearer {self.token}"
                        res = client.post(
                            f"{self.base_url}/api/v1/command",
                            json=payload,
                            headers=headers,
                        )

                try:
                    raw_json = res.json()
                except Exception as json_err:
                    # If decompression or JSON stream decode failed, fallback to raw socket HTTP
                    try:
                        return self._execute_raw_fallback("/api/v1/command", payload, timeout)
                    except Exception:
                        raise json_err

                return ResponseEnvelope.model_validate(raw_json)

        except httpx.ConnectError:
            # Check if port or session changed and retry once (unless port was explicitly fixed)
            old_port = self.port
            if not self._explicit_port and self._discover_session(force=True) and self.port != old_port:
                try:
                    with httpx.Client(timeout=timeout, trust_env=False) as client:
                        headers["Authorization"] = f"Bearer {self.token}"
                        res = client.post(
                            f"{self.base_url}/api/v1/command",
                            json=payload,
                            headers=headers,
                        )
                        return ResponseEnvelope.model_validate(res.json())
                except Exception:
                    pass

            return ResponseEnvelope(
                status="error",
                error=ErrorDetail(
                    code="BRIDGE_UNAVAILABLE",
                    message=(
                        f"Cannot connect to Blender on {self.base_url}. "
                        "Ensure Blender is running and BlenderAgent Bridge is started in the 3D Viewport sidebar."
                    ),
                    details={"target_url": self.base_url},
                ),
                message="Connection failed: Blender bridge unreachable.",
            )

        except httpx.TimeoutException:
            return ResponseEnvelope(
                status="error",
                error=ErrorDetail(
                    code="EXECUTION_TIMEOUT",
                    message=f"Request to Blender timed out after {timeout} seconds.",
                    details={"timeout_seconds": timeout},
                ),
                message="Operation timed out awaiting response from Blender.",
            )

        except Exception as exc:
            exc_str = str(exc).lower()
            # If decompression error or proxy corruption occurred, fallback to raw standard library connection
            if "decompress" in exc_str or "header check" in exc_str or "zlib" in exc_str or type(exc).__name__ == "error":
                try:
                    return self._execute_raw_fallback("/api/v1/command", payload, timeout)
                except Exception as fb_exc:
                    exc = fb_exc

            return ResponseEnvelope(
                status="error",
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message=f"Unexpected error communicating with Blender: {exc}",
                    details={"exception_type": type(exc).__name__},
                ),
                message="Communication error.",
            )
