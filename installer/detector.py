"""Environment and agent detection engine for BlenderAgent Bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

from .constants import (
    ANTIGRAVITIY_GLOBAL_CONFIG,
    ANTIGRAVITIY_IDE_CONFIG,
    CODEX_GLOBAL_CONFIG,
    MCP_LAUNCHER_PATH,
    MIN_BLENDER_VERSION,
)

try:
    import winreg
except ImportError:
    winreg = None

try:
    import tomli
except ImportError:
    tomli = None


@dataclass
class BlenderInstallation:
    """Represents a discovered Blender installation on the system."""
    executable_path: pathlib.Path
    version_str: str
    version_tuple: Tuple[int, ...]
    is_supported: bool
    is_running: bool
    extension_repos: Dict[str, pathlib.Path] = field(default_factory=dict)
    default_user_repo_dir: Optional[pathlib.Path] = None

    @property
    def display_name(self) -> str:
        status = " (Running)" if self.is_running else ""
        return f"Blender {self.version_str} at {self.executable_path}{status}"


@dataclass
class AntigravityDetection:
    """Detection state for Google Antigravity."""
    installed: bool
    config_paths: List[pathlib.Path] = field(default_factory=list)
    is_configured: bool = False
    configured_command: Optional[str] = None
    configured_args: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class CodexDetection:
    """Detection state for OpenAI Codex."""
    installed: bool
    config_path: Optional[pathlib.Path] = None
    cli_available: bool = False
    cli_version: Optional[str] = None
    is_configured: bool = False
    configured_command: Optional[str] = None
    configured_args: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class SystemDetectionResult:
    """Consolidated system detection results."""
    blender_installations: List[BlenderInstallation] = field(default_factory=list)
    recommended_blender: Optional[BlenderInstallation] = None
    antigravity: AntigravityDetection = field(default_factory=lambda: AntigravityDetection(installed=False))
    codex: CodexDetection = field(default_factory=lambda: CodexDetection(installed=False))
    is_bridge_running: bool = False
    bridge_port: int = 9876


def is_process_running(process_name: str) -> bool:
    """Check if a process with a given name is actively running on Windows."""
    if sys.platform != "win32":
        return False
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
            text=True,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return process_name.lower() in output.lower()
    except Exception:
        return False


def _query_blender_version(executable: pathlib.Path) -> Optional[Tuple[str, Tuple[int, ...]]]:
    """Invoke blender.exe --version to extract actual semantic version."""
    if not executable.exists():
        return None
    try:
        proc = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if proc.returncode != 0:
            return None

        # Output format typically starts with: 'Blender 5.2.2 (hash ...)'
        match = re.search(r"Blender\s+([0-9]+(?:\.[0-9]+)+)", proc.stdout)
        if match:
            v_str = match.group(1)
            parts = tuple(int(p) for p in v_str.split("."))
            return v_str, parts
    except Exception:
        pass
    return None


def _query_blender_extension_repos(executable: pathlib.Path) -> Dict[str, pathlib.Path]:
    """Query blender extension repositories using `blender --command extension repo-list`."""
    repos = {}
    try:
        proc = subprocess.run(
            [str(executable), "--command", "extension", "repo-list"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if proc.returncode == 0:
            current_id = None
            for line in proc.stdout.splitlines():
                line_stripped = line.strip()
                if line_stripped.endswith(":") and not line_stripped.startswith("directory:"):
                    current_id = line_stripped[:-1].strip()
                elif current_id and "directory:" in line_stripped:
                    dir_match = re.search(r'directory:\s*"([^"]+)"', line_stripped)
                    if dir_match:
                        repos[current_id] = pathlib.Path(dir_match.group(1))
    except Exception:
        pass
    return repos


def detect_blender_installations() -> List[BlenderInstallation]:
    """Detect all Blender installations on the Windows machine."""
    candidates = set()

    # 1. Check PATH
    which_blender = shutil.which("blender")
    if which_blender:
        candidates.add(pathlib.Path(which_blender).resolve())

    # 2. Check Windows Registry
    if winreg:
        for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root_key, r"SOFTWARE\BlenderFoundation") as bf_key:
                    sub_count, _, _ = winreg.QueryInfoKey(bf_key)
                    for i in range(sub_count):
                        sub_name = winreg.EnumKey(bf_key, i)
                        try:
                            with winreg.OpenKey(bf_key, rf"{sub_name}\InstallDir") as inst_key:
                                val, _ = winreg.QueryValueEx(inst_key, "")
                                if val:
                                    exe = pathlib.Path(val) / "blender.exe"
                                    if exe.exists():
                                        candidates.add(exe.resolve())
                        except Exception:
                            pass
            except Exception:
                pass

    # 3. Check Standard Program Files Locations
    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    bf_dir = pathlib.Path(prog_files) / "Blender Foundation"
    if bf_dir.exists():
        for sub in bf_dir.iterdir():
            exe = sub / "blender.exe"
            if exe.exists():
                candidates.add(exe.resolve())

    # 4. Check Local AppData Programs
    local_prog = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Blender Foundation"
    if local_prog.exists():
        for sub in local_prog.iterdir():
            exe = sub / "blender.exe"
            if exe.exists():
                candidates.add(exe.resolve())

    # 5. Check Steam installation
    steam_blender = pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe")
    if steam_blender.exists():
        candidates.add(steam_blender.resolve())

    # Inspect each candidate
    installations = []
    blender_running = is_process_running("blender.exe")

    for exe in sorted(candidates):
        res = _query_blender_version(exe)
        if not res:
            continue
        v_str, v_tuple = res
        is_supported = v_tuple >= MIN_BLENDER_VERSION
        repos = _query_blender_extension_repos(exe)

        # Identify default user extension repo
        default_user_dir = repos.get("user_default")
        if not default_user_dir and repos:
            # Fall back to first user repository or blender_org
            default_user_dir = list(repos.values())[0]

        installations.append(
            BlenderInstallation(
                executable_path=exe,
                version_str=v_str,
                version_tuple=v_tuple,
                is_supported=is_supported,
                is_running=blender_running,
                extension_repos=repos,
                default_user_repo_dir=default_user_dir,
            )
        )

    # Sort descending by version tuple
    installations.sort(key=lambda b: b.version_tuple, reverse=True)
    return installations


def detect_antigravity() -> AntigravityDetection:
    """Detect Google Antigravity configuration files and registered MCP servers."""
    target_configs = [ANTIGRAVITIY_GLOBAL_CONFIG, ANTIGRAVITIY_IDE_CONFIG]
    found_configs = []
    is_configured = False
    cmd_found = None
    args_found = []

    for cfg_path in target_configs:
        if cfg_path.exists():
            found_configs.append(cfg_path)
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                servers = data.get("mcpServers", {})
                if "blenderagent-bridge" in servers:
                    is_configured = True
                    entry = servers["blenderagent-bridge"]
                    cmd_found = entry.get("command")
                    args_found = entry.get("args", [])
            except Exception:
                pass

    installed = len(found_configs) > 0 or ANTIGRAVITIY_GLOBAL_CONFIG.parent.exists()
    return AntigravityDetection(
        installed=installed,
        config_paths=found_configs,
        is_configured=is_configured,
        configured_command=cmd_found,
        configured_args=args_found,
    )


def detect_codex() -> CodexDetection:
    """Detect OpenAI Codex installation and config.toml registration."""
    cfg_path = CODEX_GLOBAL_CONFIG
    installed = cfg_path.exists() or cfg_path.parent.exists()
    cli_path = shutil.which("codex")
    cli_version = None

    if cli_path:
        try:
            res = subprocess.run(
                ["codex", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if res.returncode == 0:
                cli_version = res.stdout.strip()
        except Exception:
            pass

    is_configured = False
    cmd_found = None
    args_found = []

    if cfg_path.exists() and tomli:
        try:
            with open(cfg_path, "rb") as f:
                data = tomli.load(f)
            servers = data.get("mcp_servers", {})
            if "blenderagent-bridge" in servers:
                is_configured = True
                entry = servers["blenderagent-bridge"]
                cmd_found = entry.get("command")
                args_found = entry.get("args", [])
        except Exception as err:
            return CodexDetection(
                installed=installed,
                config_path=cfg_path,
                cli_available=bool(cli_path),
                cli_version=cli_version,
                error_message=f"Failed to parse config.toml: {err}",
            )

    return CodexDetection(
        installed=installed,
        config_path=cfg_path if cfg_path.exists() else None,
        cli_available=bool(cli_path),
        cli_version=cli_version,
        is_configured=is_configured,
        configured_command=cmd_found,
        configured_args=args_found,
    )


def detect_system_state() -> SystemDetectionResult:
    """Run full system detection for Blender, Antigravity, and Codex."""
    blenders = detect_blender_installations()
    recommended = None
    for b in blenders:
        if b.is_supported:
            recommended = b
            break

    antigravity = detect_antigravity()
    codex = detect_codex()

    # Check local bridge health via HTTP
    import httpx
    is_bridge_running = False
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.get("http://127.0.0.1:9876/api/v1/health")
            if resp.status_code == 200:
                is_bridge_running = True
    except Exception:
        pass

    return SystemDetectionResult(
        blender_installations=blenders,
        recommended_blender=recommended,
        antigravity=antigravity,
        codex=codex,
        is_bridge_running=is_bridge_running,
    )
