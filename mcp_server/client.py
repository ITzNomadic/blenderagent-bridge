"""HTTP client for communicating with the BlenderAgent Bridge add-on in Blender."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from typing import Any, Dict, Optional, Set
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
        self._explicit_port = port != 9876 or "BLENDERAGENT_PORT" in os.environ
        self.port = int(os.environ.get("BLENDERAGENT_PORT", port))
        self._explicit_workspace = workspace_dir is not None
        self.workspace_dir = pathlib.Path(
            workspace_dir or os.environ.get("BLENDERAGENT_WORKSPACE", pathlib.Path.cwd() / "workspace")
        ).resolve()
        self.token = token or os.environ.get("BLENDERAGENT_TOKEN", "")
        self._rejected_tokens: Set[str] = set()

    def _is_pid_alive(self, pid: Optional[int]) -> bool:
        """Check if a process ID is currently running on the system."""
        if not pid or pid <= 0:
            return True
        if sys.platform == "win32":
            try:
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                SYNCHRONIZE = 0x00100000
                h_proc = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
                )
                if h_proc:
                    exit_code = ctypes.c_ulong()
                    ctypes.windll.kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code))
                    ctypes.windll.kernel32.CloseHandle(h_proc)
                    return exit_code.value == 259  # STILL_ACTIVE
                return False
            except Exception:
                return True
        else:
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

    def _discover_session(self, force: bool = False) -> bool:
        """Attempt auto-discovery of session metadata from workspace or global live session."""
        if not force and self.token and self.token not in self._rejected_tokens:
            return True

        candidate_paths = []
        if self._explicit_workspace:
            # If caller explicitly requested a workspace, prioritize it
            candidate_paths.append(self.workspace_dir / ".blenderagent_session.json")
        else:
            # Default auto-discovery: Global live session of the running Blender process
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                candidate_paths.append(pathlib.Path(local_appdata) / "BlenderAgentBridge" / "live_session.json")
                candidate_paths.append(pathlib.Path(local_appdata) / "BlenderAgentBridge" / "workspace" / ".blenderagent_session.json")
            if self.workspace_dir:
                candidate_paths.append(self.workspace_dir / ".blenderagent_session.json")
            candidate_paths.append(pathlib.Path.home() / ".blenderagent" / "live_session.json")
            candidate_paths.append(pathlib.Path.cwd() / "workspace" / ".blenderagent_session.json")

        # Sort candidate files that exist by modification time (most recent first)
        existing_candidates = [p for p in candidate_paths if p.exists()]
        existing_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        for session_file in existing_candidates:
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tok = data.get("token")
                pid = data.get("pid")

                if not tok or tok in self._rejected_tokens:
                    continue

                if pid and not self._is_pid_alive(pid):
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
        }

        try:
            with httpx.Client(timeout=timeout) as client:
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

                raw_json = res.json()
                return ResponseEnvelope.model_validate(raw_json)

        except httpx.ConnectError:
            # Check if port or session changed and retry once (unless port was explicitly fixed)
            old_port = self.port
            if not self._explicit_port and self._discover_session(force=True) and self.port != old_port:
                try:
                    with httpx.Client(timeout=timeout) as client:
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
            return ResponseEnvelope(
                status="error",
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message=f"Unexpected error communicating with Blender: {exc}",
                    details={"exception_type": type(exc).__name__},
                ),
                message="Communication error.",
            )
