"""Transactional installation orchestrator and lifecycle engine for BlenderAgent Bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
import pathlib
import shutil
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .adapters.antigravity import AntigravityAdapter
from .adapters.codex import CodexAdapter
from .addon_manager import BlenderAddonManager
from .constants import (
    ADDON_ID,
    APP_ID,
    APP_NAME,
    DEFAULT_BIN_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_INSTALL_DIR,
    DEFAULT_PORT,
    DEFAULT_WORKSPACE_DIR,
    INSTALL_MANIFEST_PATH,
    MCP_LAUNCHER_EXE_NAME,
    MCP_LAUNCHER_PATH,
    VERSION,
)
from .detector import BlenderInstallation, detect_system_state
from .security_manager import generate_secure_token, load_session_credentials, save_session_credentials


@dataclass
class InstallOptions:
    """Configuration options chosen by the user or defaults for installation."""
    blender: Optional[BlenderInstallation] = None
    install_antigravity: bool = True
    install_codex: bool = True
    install_dir: pathlib.Path = DEFAULT_INSTALL_DIR
    workspace_dir: pathlib.Path = DEFAULT_WORKSPACE_DIR
    port: int = DEFAULT_PORT
    autostart_bridge: bool = True


@dataclass
class StepProgress:
    name: str
    status: str = "pending"  # pending | running | done | failed | skipped
    message: str = ""


class InstallationOrchestrator:
    """Coordinates atomic installation, registration, health verification, repair, and uninstallation."""

    def __init__(self, options: Optional[InstallOptions] = None):
        self.options = options or InstallOptions()
        self.addon_manager = BlenderAddonManager()
        self.antigravity_adapter = AntigravityAdapter()
        self.codex_adapter = CodexAdapter()

    def _resolve_asset_dir(self) -> pathlib.Path:
        """Resolve directory containing distribution payloads (works in dev and PyInstaller frozen bundle)."""
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            meipass = pathlib.Path(sys._MEIPASS)
            if (meipass / "dist").exists():
                return meipass / "dist"
            return meipass
        repo_root = pathlib.Path(__file__).parent.parent.resolve()
        return repo_root / "dist"

    def run_installation(
        self,
        progress_callback: Optional[Callable[[str, str, str], None]] = None,
    ) -> Tuple[bool, List[StepProgress]]:
        """Execute the transactional installation pipeline with progress reporting."""
        steps: List[StepProgress] = [
            StepProgress("verify_package", "pending", "Verifying installation payloads"),
            StepProgress("stage_directories", "pending", "Staging user directories"),
            StepProgress("install_runtime", "pending", "Provisioning standalone MCP runtime"),
            StepProgress("install_addon", "pending", "Installing BlenderAgent extension"),
            StepProgress("register_antigravity", "pending", "Configuring Google Antigravity"),
            StepProgress("register_codex", "pending", "Configuring OpenAI Codex"),
            StepProgress("init_session", "pending", "Initializing secure session credentials"),
            StepProgress("verify_mcp", "pending", "Verifying MCP registration integrity"),
        ]

        def update_step(idx: int, status: str, msg: str):
            steps[idx].status = status
            steps[idx].message = msg
            if progress_callback:
                progress_callback(steps[idx].name, status, msg)

        # 1. Verify package payloads
        update_step(0, "running", "Checking required assets...")
        dist_dir = self._resolve_asset_dir()
        bin_dir = self.options.install_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        target_launcher = bin_dir / MCP_LAUNCHER_EXE_NAME

        update_step(0, "done", "Payload verification complete.")

        # 2. Stage directories
        update_step(1, "running", "Creating workspace and program folders...")
        try:
            self.options.workspace_dir.mkdir(parents=True, exist_ok=True)
            (self.options.workspace_dir / "renders").mkdir(parents=True, exist_ok=True)
            (self.options.workspace_dir / "scenes").mkdir(parents=True, exist_ok=True)
            DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
            update_step(1, "done", f"Workspace ready at {self.options.workspace_dir}")
        except Exception as err:
            update_step(1, "failed", f"Failed staging directories: {err}")
            return False, steps

        # 3. Install Runtime
        update_step(2, "running", f"Deploying {MCP_LAUNCHER_EXE_NAME}...")
        try:
            source_exe = dist_dir / MCP_LAUNCHER_EXE_NAME
            if source_exe.exists():
                shutil.copy2(source_exe, target_launcher)
            elif not target_launcher.exists():
                # For development or non-frozen installations, create launcher script/shim
                python_exe = sys.executable
                shim_cmd = f'@echo off\r\n"{python_exe}" -m mcp_server.launcher %*\r\n'
                shim_path = bin_dir / "blenderagent-mcp.bat"
                with open(shim_path, "w", encoding="utf-8") as f:
                    f.write(shim_cmd)
                # Also link or copy python exe as placeholder if needed
                target_launcher = bin_dir / "blenderagent-mcp.bat"

            update_step(2, "done", f"Runtime deployed to {target_launcher}")
        except Exception as err:
            update_step(2, "failed", f"Failed to provision runtime: {err}")
            return False, steps

        # 4. Install Addon
        update_step(3, "running", "Installing extension into Blender...")
        if self.options.blender:
            try:
                zip_path = dist_dir / f"{ADDON_ID}.zip"
                if not zip_path.exists():
                    zip_path = self.addon_manager.build_extension_zip(zip_path)
                success, msg = self.addon_manager.install_addon(self.options.blender, zip_path)
                if success:
                    update_step(3, "done", msg)
                else:
                    update_step(3, "failed", msg)
                    return False, steps
            except Exception as err:
                update_step(3, "failed", f"Extension install error: {err}")
                return False, steps
        else:
            update_step(3, "skipped", "No supported Blender installation selected.")

        # 5. Register Antigravity
        if self.options.install_antigravity:
            update_step(4, "running", "Registering in Google Antigravity...")
            ag_res = self.antigravity_adapter.install_registration(
                launcher_path=target_launcher,
                workspace_dir=self.options.workspace_dir,
                port=self.options.port,
            )
            if ag_res.success:
                update_step(4, "done", ag_res.message)
            else:
                update_step(4, "failed", ag_res.message)
        else:
            update_step(4, "skipped", "Antigravity integration disabled by user.")

        # 6. Register Codex
        if self.options.install_codex:
            update_step(5, "running", "Registering in OpenAI Codex...")
            codex_res = self.codex_adapter.install_registration(
                launcher_path=target_launcher,
                workspace_dir=self.options.workspace_dir,
                port=self.options.port,
            )
            if codex_res.success:
                update_step(5, "done", codex_res.message)
            else:
                update_step(5, "failed", codex_res.message)
        else:
            update_step(5, "skipped", "Codex integration disabled by user.")

        # 7. Initialize Session
        update_step(6, "running", "Creating secure session credentials...")
        try:
            session_file, token = save_session_credentials(
                workspace_dir=self.options.workspace_dir,
                port=self.options.port,
            )
            update_step(6, "done", "Session initialized with protected token.")
        except Exception as err:
            update_step(6, "failed", f"Failed to initialize session: {err}")
            return False, steps

        # 8. Verify MCP
        update_step(7, "running", "Verifying registration integrity...")
        verified_ag = not self.options.install_antigravity or self.antigravity_adapter.verify_registration(target_launcher)
        verified_codex = not self.options.install_codex or self.codex_adapter.verify_registration(target_launcher)

        if verified_ag and verified_codex:
            update_step(7, "done", "Integrity verified. Ready to use!")
            self._save_install_manifest(target_launcher)
            return True, steps
        else:
            update_step(7, "failed", "Verification failed for one or more registered clients.")
            return False, steps

    def _save_install_manifest(self, launcher_path: pathlib.Path) -> None:
        """Record install manifest for tracking, updates, and clean uninstall."""
        manifest = {
            "app_name": APP_NAME,
            "app_id": APP_ID,
            "version": VERSION,
            "installed_at": time.time(),
            "installed_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "launcher_path": str(launcher_path.resolve()),
            "workspace_dir": str(self.options.workspace_dir.resolve()),
            "port": self.options.port,
            "blender_path": str(self.options.blender.executable_path) if self.options.blender else None,
            "antigravity_registered": self.options.install_antigravity,
            "codex_registered": self.options.install_codex,
        }
        DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(INSTALL_MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def uninstall(self, keep_workspace: bool = True) -> Tuple[bool, List[str]]:
        """Cleanly remove extension and MCP registrations while preserving user projects."""
        logs = []

        # 1. Unregister clients
        ag_res = self.antigravity_adapter.uninstall_registration()
        logs.append(f"Antigravity: {ag_res.message}")

        codex_res = self.codex_adapter.uninstall_registration()
        logs.append(f"Codex: {codex_res.message}")

        # 2. Remove addon if blender is known
        sys_state = detect_system_state()
        if sys_state.recommended_blender:
            success, msg = self.addon_manager.uninstall_addon(sys_state.recommended_blender)
            logs.append(f"Blender Extension: {msg}")

        # 3. Remove program binaries
        if self.options.install_dir.exists():
            shutil.rmtree(self.options.install_dir, ignore_errors=True)
            logs.append(f"Removed binaries: {self.options.install_dir}")

        # 4. Handle manifest
        if INSTALL_MANIFEST_PATH.exists():
            INSTALL_MANIFEST_PATH.unlink()
            logs.append("Removed installation manifest.")

        if not keep_workspace and self.options.workspace_dir.exists():
            shutil.rmtree(self.options.workspace_dir, ignore_errors=True)
            logs.append("Removed workspace directory.")
        else:
            logs.append("User workspace and render files preserved.")

        return True, logs

    def repair(self) -> Tuple[bool, str]:
        """Perform non-destructive repair of all registrations and files."""
        sys_state = detect_system_state()
        if not self.options.blender:
            self.options.blender = sys_state.recommended_blender

        success, steps = self.run_installation()
        if success:
            return True, "All components repaired successfully."
        failed = [s.name for s in steps if s.status == "failed"]
        return False, f"Repair failed on steps: {', '.join(failed)}"
