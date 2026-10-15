"""HTTP client for communicating with the BlenderAgent Bridge add-on in Blender."""

from __future__ import annotations

import json
import os
import pathlib
import time
from typing import Any, Dict, Optional
import httpx

from .models import ErrorDetail, ResponseEnvelope


class BlenderBridgeClient:
    """Client for dispatching validated MCP commands to the local Blender Add-on."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9876,
        token: Optional[str] = None,
        workspace_dir: Optional[str | pathlib.Path] = None,
    ):
        self.host = host
        self.port = int(os.environ.get("BLENDERAGENT_PORT", port))
        self.workspace_dir = pathlib.Path(
            workspace_dir or os.environ.get("BLENDERAGENT_WORKSPACE", pathlib.Path.cwd() / "workspace")
        ).resolve()
        self.token = token or os.environ.get("BLENDERAGENT_TOKEN", "")

    def _discover_session(self) -> None:
        """Attempt auto-discovery of session metadata from workspace if token is unset."""
        if self.token:
            return

        session_file = self.workspace_dir / ".blenderagent_session.json"
        if session_file.exists():
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.token = data.get("token", self.token)
                    self.port = int(data.get("port", self.port))
            except Exception:
                pass

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def check_health(self) -> bool:
        """Check if Blender bridge HTTP endpoint is alive."""
        self._discover_session()
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.base_url}/api/v1/health")
                return res.status_code == 200
        except Exception:
            return False

    def send_command(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 35.0,
    ) -> ResponseEnvelope:
        """Send a command payload to the BlenderAgent Bridge and receive the standardized response."""
        self._discover_session()

        payload = {
            "command": command,
            "params": params or {},
            "request_id": f"req-{int(time.time() * 1000)}",
            "timeout": timeout - 2.0,
        }

        # Include authorized workspace in parameters
        if "workspace_dir" not in payload["params"]:
            payload["params"]["workspace_dir"] = str(self.workspace_dir)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                res = client.post(
                    f"{self.base_url}/api/v1/command",
                    json=payload,
                    headers=headers,
                )
                raw_json = res.json()
                return ResponseEnvelope.model_validate(raw_json)

        except httpx.ConnectError:
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
            return ResponseEnvelope(
                status="error",
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message=f"Unexpected error communicating with Blender: {exc}",
                    details={"exception_type": type(exc).__name__},
                ),
                message="Communication error.",
            )
