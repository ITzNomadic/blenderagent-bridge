"""Blender extension packaging, deployment, and lifecycle manager."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import zipfile
from typing import Optional, Tuple

from .constants import ADDON_ID
from .detector import BlenderInstallation


class BlenderAddonManager:
    """Manages the lifecycle of the BlenderAgent Bridge Blender Extension."""

    def __init__(self, addon_source_dir: Optional[pathlib.Path] = None):
        if addon_source_dir:
            self._source_dir = pathlib.Path(addon_source_dir).resolve()
        else:
            # Default to repo structure: addon/blenderagent_bridge
            repo_root = pathlib.Path(__file__).parent.parent.resolve()
            self._source_dir = repo_root / "addon" / "blenderagent_bridge"

    def build_extension_zip(self, output_path: Optional[pathlib.Path] = None) -> pathlib.Path:
        """Create a clean Blender 4.2+ extension zip archive from the source directory."""
        if not self._source_dir.exists():
            raise FileNotFoundError(f"Add-on source directory not found: {self._source_dir}")

        manifest = self._source_dir / "blender_manifest.toml"
        if not manifest.exists():
            raise FileNotFoundError(f"Missing blender_manifest.toml in: {self._source_dir}")

        if output_path is None:
            dist_dir = self._source_dir.parent.parent / "dist"
            dist_dir.mkdir(parents=True, exist_ok=True)
            output_path = dist_dir / f"{ADDON_ID}.zip"
        else:
            output_path = pathlib.Path(output_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)

        # Standard zip structure: files at the root of the archive for modern Blender extensions
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(self._source_dir):
                # Exclude __pycache__ and test artifacts
                dirs[:] = [d for d in dirs if d != "__pycache__" and not d.startswith(".")]
                for file in files:
                    if file.endswith((".pyc", ".pyo")):
                        continue
                    full_p = pathlib.Path(root) / file
                    rel_p = full_p.relative_to(self._source_dir)
                    zf.write(full_p, arcname=str(rel_p))

        return output_path

    def install_addon(
        self,
        blender_inst: BlenderInstallation,
        zip_path: Optional[pathlib.Path] = None,
    ) -> Tuple[bool, str]:
        """Deploy and enable the extension into the target Blender installation."""
        if not zip_path or not zip_path.exists():
            zip_path = self.build_extension_zip()

        # Identify repository ID (preference for 'user_default')
        repo_id = "user_default"
        if blender_inst.extension_repos and "user_default" not in blender_inst.extension_repos:
            repo_id = list(blender_inst.extension_repos.keys())[0]

        # 1. Attempt official CLI installation: blender --command extension install-file -r <repo> -e <zip>
        cli_success = False
        cli_message = ""
        try:
            cmd = [
                str(blender_inst.executable_path),
                "--command",
                "extension",
                "install-file",
                "-r",
                repo_id,
                "-e",
                str(zip_path.resolve()),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if proc.returncode == 0:
                cli_success = True
                cli_message = "Extension installed via Blender official CLI."
            else:
                cli_message = f"CLI output: {proc.stdout} {proc.stderr}"
        except Exception as err:
            cli_message = str(err)

        # 2. Fallback / Direct copy to user repository if CLI didn't complete
        if not cli_success:
            user_repo_dir = blender_inst.default_user_repo_dir
            if not user_repo_dir:
                # Deduce standard AppData user repository path for Blender
                user_repo_dir = (
                    pathlib.Path(os.environ.get("APPDATA", ""))
                    / "Blender Foundation"
                    / "Blender"
                    / f"{blender_inst.version_tuple[0]}.{blender_inst.version_tuple[1]}"
                    / "extensions"
                    / "user_default"
                )

            target_addon_dir = user_repo_dir / ADDON_ID
            target_addon_dir.mkdir(parents=True, exist_ok=True)

            # Extract zip contents into target repository directory
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(target_addon_dir)

            cli_message = f"Directly extracted package to {target_addon_dir}."

        is_running_note = ""
        if blender_inst.is_running:
            is_running_note = " (Note: Blender is currently open; please reload extensions or restart Blender to activate)."

        return True, f"BlenderAgent Bridge extension installed successfully.{is_running_note}"

    def verify_addon(self, blender_inst: BlenderInstallation) -> bool:
        """Verify that the add-on files and manifest are installed in user repository."""
        user_repo_dir = blender_inst.default_user_repo_dir
        if not user_repo_dir:
            user_repo_dir = (
                pathlib.Path(os.environ.get("APPDATA", ""))
                / "Blender Foundation"
                / "Blender"
                / f"{blender_inst.version_tuple[0]}.{blender_inst.version_tuple[1]}"
                / "extensions"
                / "user_default"
            )

        target_manifest = user_repo_dir / ADDON_ID / "blender_manifest.toml"
        target_init = user_repo_dir / ADDON_ID / "__init__.py"
        return target_manifest.exists() and target_init.exists()

    def uninstall_addon(self, blender_inst: BlenderInstallation) -> Tuple[bool, str]:
        """Safely remove the extension from the target Blender user repository."""
        user_repo_dir = blender_inst.default_user_repo_dir
        if not user_repo_dir:
            user_repo_dir = (
                pathlib.Path(os.environ.get("APPDATA", ""))
                / "Blender Foundation"
                / "Blender"
                / f"{blender_inst.version_tuple[0]}.{blender_inst.version_tuple[1]}"
                / "extensions"
                / "user_default"
            )

        target_addon_dir = user_repo_dir / ADDON_ID
        if target_addon_dir.exists():
            shutil.rmtree(target_addon_dir, ignore_errors=True)
            return True, f"Removed extension from {target_addon_dir}."
        return True, "Extension was not installed."
