"""Adapter for OpenAI Codex CLI and IDE MCP configuration."""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import time
from typing import Any, Dict, List, Optional

try:
    from ..constants import APP_ID, CODEX_GLOBAL_CONFIG
    from .base import AdapterPlan, AdapterResult, AdapterStatus, ClientAdapter
except ImportError:
    from installer.constants import APP_ID, CODEX_GLOBAL_CONFIG
    from installer.adapters.base import AdapterPlan, AdapterResult, AdapterStatus, ClientAdapter

# Use Python 3.11+ built-in tomllib with fallback to tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

try:
    import tomli_w
except ImportError:
    tomli_w = None


class CodexAdapter(ClientAdapter):
    """Integrates BlenderAgent Bridge with OpenAI Codex."""

    def __init__(self, config_path: Optional[pathlib.Path] = None):
        self._config_path = config_path or CODEX_GLOBAL_CONFIG

    @property
    def client_name(self) -> str:
        return "OpenAI Codex"

    def detect(self) -> AdapterStatus:
        if not self._config_path.exists():
            if self._config_path.parent.exists():
                return AdapterStatus.COMPATIBLE
            return AdapterStatus.NOT_FOUND

        if not tomllib:
            return AdapterStatus.COMPATIBLE

        try:
            with open(self._config_path, "rb") as f:
                data = tomllib.load(f)
            servers = data.get("mcp_servers", {})
            if APP_ID in servers:
                return AdapterStatus.ALREADY_INSTALLED
            return AdapterStatus.COMPATIBLE
        except Exception:
            return AdapterStatus.ERROR

    def plan_install(self, launcher_path: pathlib.Path) -> AdapterPlan:
        backup_candidate = self._config_path.with_name(
            f"{self._config_path.name}.bak.{time.strftime('%Y%m%d_%H%M%S')}"
        )
        return AdapterPlan(
            client_name=self.client_name,
            target_config_file=self._config_path,
            backup_file=backup_candidate,
            action_description=f"Register '{APP_ID}' in Codex [mcp_servers] pointing to {launcher_path.name}",
            will_modify=True,
            requires_client_restart=True,
        )

    def backup_config(self) -> Optional[pathlib.Path]:
        if self._config_path.exists():
            backup_path = self._config_path.with_name(
                f"{self._config_path.name}.bak.{time.strftime('%Y%m%d_%H%M%S')}"
            )
            try:
                shutil.copy2(self._config_path, backup_path)
                return backup_path
            except Exception:
                pass
        return None

    def _render_toml_entry(self, command: str, args: List[str]) -> str:
        """Render a clean TOML table snippet for the MCP server."""
        cmd_esc = command.replace("\\", "\\\\")
        args_esc = ", ".join(f'"{a.replace(chr(92), chr(92)+chr(92))}"' for a in args)
        return (
            f"[mcp_servers.{APP_ID}]\n"
            f'command = "{cmd_esc}"\n'
            f"args = [{args_esc}]\n"
        )

    def install_registration(
        self,
        launcher_path: pathlib.Path,
        workspace_dir: pathlib.Path,
        port: int = 9876,
    ) -> AdapterResult:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        backup_file = self.backup_config()

        launcher_str = str(launcher_path.resolve())
        args = [
            "--workspace", str(workspace_dir.resolve()),
            "--port", str(port),
        ]

        original_text = ""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    original_text = f.read()
            except Exception as err:
                return AdapterResult(
                    success=False,
                    status=AdapterStatus.ERROR,
                    message=f"Corrupt or unreadable Codex config.toml: {err}",
                    error_code="CLIENT_CONFIG_INVALID",
                )

        # Method 1: If tomli_w is available, update structured dictionary
        applied_via_dict = False
        if tomllib and tomli_w and original_text.strip():
            try:
                data = tomllib.loads(original_text)
                if "mcp_servers" not in data or not isinstance(data["mcp_servers"], dict):
                    data["mcp_servers"] = {}
                data["mcp_servers"][APP_ID] = {
                    "command": launcher_str,
                    "args": args,
                }
                new_bytes = tomli_w.dumps(data).encode("utf-8")
                # Validate
                if tomllib:
                    _ = tomllib.loads(new_bytes.decode("utf-8"))
                new_content = new_bytes.decode("utf-8")
                applied_via_dict = True
            except Exception:
                applied_via_dict = False

        # Method 2: High-fidelity preservation via surgical text replacement/append
        if not applied_via_dict:
            new_entry = self._render_toml_entry(launcher_str, args)
            pattern = rf"\[mcp_servers\.{re.escape(APP_ID)}\][^\[]*"
            if re.search(pattern, original_text):
                new_content = re.sub(pattern, new_entry, original_text)
            else:
                sep = "\n\n" if original_text and not original_text.endswith("\n\n") else ""
                new_content = original_text + sep + new_entry

        # Validate with tomllib if available
        if tomllib:
            try:
                _ = tomllib.loads(new_content)
            except Exception as err:
                return AdapterResult(
                    success=False,
                    status=AdapterStatus.ERROR,
                    message=f"Validation failed for generated config.toml: {err}",
                    error_code="CLIENT_CONFIG_INVALID",
                )

        # Atomic write
        tmp_path = self._config_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            tmp_path.replace(self._config_path)

            return AdapterResult(
                success=True,
                status=AdapterStatus.CONFIGURED,
                message=f"Registered '{APP_ID}' in Codex configuration.",
                target_file=self._config_path,
                backup_file=backup_file,
                details={"target_file": str(self._config_path)},
            )
        except Exception as err:
            if tmp_path.exists():
                tmp_path.unlink()
            return AdapterResult(
                success=False,
                status=AdapterStatus.ERROR,
                message=f"Failed to write Codex config.toml: {err}",
                error_code="WRITE_FAILED",
            )

    def verify_registration(self, launcher_path: pathlib.Path) -> bool:
        if not self._config_path.exists():
            return False

        launcher_str = str(launcher_path.resolve()).lower()

        # Try structured validation if tomllib is available
        if tomllib:
            try:
                with open(self._config_path, "rb") as f:
                    data = tomllib.load(f)
                entry = data.get("mcp_servers", {}).get(APP_ID)
                if entry and str(entry.get("command", "")).lower() == launcher_str:
                    return True
            except Exception:
                pass

        # Text-based check fallback
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
            return f"[mcp_servers.{APP_ID.lower()}]" in content and launcher_str in content
        except Exception:
            return False

    def verify_runtime(self) -> bool:
        return self.detect() in (AdapterStatus.ALREADY_INSTALLED, AdapterStatus.CONFIGURED)

    def repair(self, launcher_path: pathlib.Path, workspace_dir: pathlib.Path) -> AdapterResult:
        return self.install_registration(launcher_path, workspace_dir)

    def uninstall_registration(self) -> AdapterResult:
        if not self._config_path.exists():
            return AdapterResult(success=True, status=AdapterStatus.COMPATIBLE, message="Nothing to uninstall.")

        backup_file = self.backup_config()

        # Method 1: Clean structured removal via tomli_w if available
        if tomllib and tomli_w:
            try:
                with open(self._config_path, "rb") as f:
                    data = tomllib.load(f)
                if "mcp_servers" in data and isinstance(data["mcp_servers"], dict):
                    removed = False
                    for key in list(data["mcp_servers"].keys()):
                        if key.lower() == APP_ID.lower():
                            del data["mcp_servers"][key]
                            removed = True
                    if removed:
                        new_content = tomli_w.dumps(data)
                        tmp = self._config_path.with_suffix(".tmp")
                        with open(tmp, "w", encoding="utf-8") as f:
                            f.write(new_content)
                        tmp.replace(self._config_path)
                        return AdapterResult(
                            success=True,
                            status=AdapterStatus.COMPATIBLE,
                            message=f"Removed '{APP_ID}' from Codex configuration.",
                            backup_file=backup_file,
                        )
            except Exception:
                pass

        # Method 2: Text regex fallback
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                content = f.read()

            pattern = rf"\n*\[mcp_servers\.(?:{re.escape(APP_ID)}|\"{re.escape(APP_ID)}\")\][^\[]*"
            new_content = re.sub(pattern, "", content)

            if tomllib:
                _ = tomllib.loads(new_content)

            tmp = self._config_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(new_content)
            tmp.replace(self._config_path)

            return AdapterResult(
                success=True,
                status=AdapterStatus.COMPATIBLE,
                message=f"Removed '{APP_ID}' from Codex configuration.",
                backup_file=backup_file,
            )
        except Exception as err:
            return AdapterResult(
                success=False,
                status=AdapterStatus.ERROR,
                message=f"Failed to remove '{APP_ID}' from Codex configuration: {err}",
            )
