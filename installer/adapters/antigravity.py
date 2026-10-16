"""Adapter for Google Antigravity IDE and CLI MCP configuration."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import time
from typing import Any, Dict, List, Optional

from ..constants import (
    ANTIGRAVITIY_GLOBAL_CONFIG,
    ANTIGRAVITIY_IDE_CONFIG,
    APP_ID,
)
from .base import AdapterPlan, AdapterResult, AdapterStatus, ClientAdapter


class AntigravityAdapter(ClientAdapter):
    """Integrates BlenderAgent Bridge with Google Antigravity."""

    def __init__(self, target_configs: Optional[List[pathlib.Path]] = None):
        self._target_configs = target_configs or [ANTIGRAVITIY_GLOBAL_CONFIG, ANTIGRAVITIY_IDE_CONFIG]

    @property
    def client_name(self) -> str:
        return "Google Antigravity"

    def _get_active_configs(self) -> List[pathlib.Path]:
        """Find all applicable existing Antigravity configuration files, or primary target."""
        existing = [p for p in self._target_configs if p.exists()]
        if not existing:
            # Default to primary global config
            return [self._target_configs[0]]
        return existing

    def detect(self) -> AdapterStatus:
        active = [p for p in self._target_configs if p.exists() or p.parent.exists()]
        if not active:
            return AdapterStatus.NOT_FOUND

        configured_count = 0
        for cfg in active:
            if not cfg.exists():
                continue
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if APP_ID in data.get("mcpServers", {}):
                    configured_count += 1
            except Exception:
                pass

        if configured_count > 0:
            return AdapterStatus.ALREADY_INSTALLED
        return AdapterStatus.COMPATIBLE

    def plan_install(self, launcher_path: pathlib.Path) -> AdapterPlan:
        targets = self._get_active_configs()
        primary = targets[0]
        backup_candidate = primary.with_name(f"{primary.name}.bak.{time.strftime('%Y%m%d_%H%M%S')}")
        return AdapterPlan(
            client_name=self.client_name,
            target_config_file=primary,
            backup_file=backup_candidate,
            action_description=f"Register '{APP_ID}' in Antigravity mcpServers pointing to {launcher_path.name}",
            will_modify=True,
            requires_client_restart=True,
        )

    def backup_config(self) -> Optional[pathlib.Path]:
        for cfg in self._get_active_configs():
            if cfg.exists():
                backup_path = cfg.with_name(f"{cfg.name}.bak.{time.strftime('%Y%m%d_%H%M%S')}")
                try:
                    shutil.copy2(cfg, backup_path)
                    return backup_path
                except Exception:
                    pass
        return None

    def install_registration(
        self,
        launcher_path: pathlib.Path,
        workspace_dir: pathlib.Path,
        port: int = 9876,
    ) -> AdapterResult:
        targets = self._get_active_configs()
        backup_file = self.backup_config()
        launcher_str = str(launcher_path.resolve())

        # Clean absolute arguments
        args = [
            "--workspace", str(workspace_dir.resolve()),
            "--port", str(port),
        ]

        server_entry = {
            "command": launcher_str,
            "args": args,
        }

        success_count = 0
        last_error = None

        for cfg in targets:
            try:
                cfg.parent.mkdir(parents=True, exist_ok=True)
                data: Dict[str, Any] = {"mcpServers": {}}
                if cfg.exists():
                    try:
                        with open(cfg, "r", encoding="utf-8") as f:
                            loaded = json.load(f)
                            if isinstance(loaded, dict):
                                data = loaded
                            else:
                                raise ValueError("Root element must be a JSON object.")
                    except Exception as parse_err:
                        return AdapterResult(
                            status=AdapterStatus.ERROR,
                            client_name=self.client_name,
                            modified_file=cfg,
                            message=f"Configuration file '{cfg.name}' exists but contains invalid JSON ({parse_err}). Aborted to protect existing user configuration.",
                        )

                if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
                    data["mcpServers"] = {}

                # Idempotent write: update or insert entry preserving others
                data["mcpServers"][APP_ID] = server_entry

                # Atomic write
                tmp_path = cfg.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                # Validate parsing before replacing
                with open(tmp_path, "r", encoding="utf-8") as f:
                    _ = json.load(f)

                tmp_path.replace(cfg)
                success_count += 1
            except Exception as err:
                last_error = str(err)

        if success_count > 0:
            return AdapterResult(
                success=True,
                status=AdapterStatus.CONFIGURED,
                message=f"Registered '{APP_ID}' in {success_count} Antigravity configuration(s).",
                target_file=targets[0],
                backup_file=backup_file,
                details={"configured_paths": [str(p) for p in targets]},
            )

        return AdapterResult(
            success=False,
            status=AdapterStatus.ERROR,
            message=f"Failed to update Antigravity configuration: {last_error}",
            error_code="CLIENT_CONFIG_INVALID",
        )

    def verify_registration(self, launcher_path: pathlib.Path) -> bool:
        launcher_str = str(launcher_path.resolve()).lower()
        for cfg in self._get_active_configs():
            if not cfg.exists():
                continue
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entry = data.get("mcpServers", {}).get(APP_ID)
                if entry and str(entry.get("command", "")).lower() == launcher_str:
                    return True
            except Exception:
                pass
        return False

    def verify_runtime(self) -> bool:
        # Runtime verification handled via bridge health and MCP stdio handshake
        return self.detect() in (AdapterStatus.ALREADY_INSTALLED, AdapterStatus.CONFIGURED)

    def repair(self, launcher_path: pathlib.Path, workspace_dir: pathlib.Path) -> AdapterResult:
        return self.install_registration(launcher_path, workspace_dir)

    def uninstall_registration(self) -> AdapterResult:
        targets = self._get_active_configs()
        backup_file = self.backup_config()
        removed_count = 0

        for cfg in targets:
            if not cfg.exists():
                continue
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "mcpServers" in data and APP_ID in data["mcpServers"]:
                    del data["mcpServers"][APP_ID]
                    tmp = cfg.with_suffix(".tmp")
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    tmp.replace(cfg)
                    removed_count += 1
            except Exception:
                pass

        return AdapterResult(
            success=True,
            status=AdapterStatus.COMPATIBLE,
            message=f"Removed '{APP_ID}' from {removed_count} Antigravity configuration(s).",
            backup_file=backup_file,
        )
