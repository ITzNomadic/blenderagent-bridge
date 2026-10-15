"""Command-line interface and entrypoint for BlenderAgent Bridge v0.2.0 Windows Installer."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import pathlib
import sys

# Ensure repository root / frozen bundle directory is in sys.path
if getattr(sys, "frozen", False):
    bundle_dir = pathlib.Path(sys._MEIPASS).resolve()
    if str(bundle_dir) not in sys.path:
        sys.path.insert(0, str(bundle_dir))
else:
    repo_root = pathlib.Path(__file__).parent.parent.resolve()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

# In Windows GUI mode, attach to parent terminal console if invoked from CLI
if sys.platform == "win32":
    import ctypes
    try:
        # ATTACH_PARENT_PROCESS = -1
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:
        pass

# Ensure stdout and stderr are never None in --noconsole mode
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

try:
    from installer.constants import DEFAULT_PORT, DEFAULT_WORKSPACE_DIR, VERSION
    from installer.detector import detect_system_state
    from installer.orchestrator import InstallationOrchestrator, InstallOptions
except ImportError:
    from .constants import DEFAULT_PORT, DEFAULT_WORKSPACE_DIR, VERSION
    from .detector import detect_system_state
    from .orchestrator import InstallationOrchestrator, InstallOptions


def main():
    parser = argparse.ArgumentParser(description=f"BlenderAgent Bridge v{VERSION} CLI & Installer Engine")
    parser.add_argument("--gui", action="store_true", help="Launch interactive graphical user interface (default if no flags)")
    parser.add_argument("--install", action="store_true", help="Perform unattended silent installation")
    parser.add_argument("--detect", action="store_true", help="Inspect and print system state in JSON format")
    parser.add_argument("--repair", action="store_true", help="Repair existing installation and MCP configurations")
    parser.add_argument("--uninstall", action="store_true", help="Remove registrations and extension safely")
    parser.add_argument("--workspace", type=str, default=str(DEFAULT_WORKSPACE_DIR), help="Custom workspace path")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local bridge port (default 9876)")
    parser.add_argument("--no-antigravity", action="store_true", help="Skip Google Antigravity registration")
    parser.add_argument("--no-codex", action="store_true", help="Skip OpenAI Codex registration")

    args = parser.parse_args()

    # Determine if an explicit headless CLI operation was requested
    is_cli_action = any([args.install, args.detect, args.repair, args.uninstall])

    # Default to GUI when double-clicked or executed without explicit CLI action flags
    if not is_cli_action or args.gui:
        try:
            try:
                from installer.gui import launch_gui
            except ImportError:
                from .gui import launch_gui
            launch_gui()
            return 0
        except Exception as err:
            import traceback
            tb = traceback.format_exc()
            if sys.platform == "win32":
                try:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(
                        0,
                        f"An error occurred while launching BlenderAgent Bridge Installer:\n\n{err}\n\n{tb[:500]}",
                        "BlenderAgent Bridge Installer Error",
                        0x10,  # MB_ICONERROR
                    )
                except Exception:
                    pass
            print(f"[!] Error launching graphical interface: {err}\n{tb}")
            return 1

    if args.detect:
        state = detect_system_state()
        data = {
            "blenders": [
                {
                    "path": str(b.executable_path),
                    "version": b.version_str,
                    "supported": b.is_supported,
                    "running": b.is_running,
                    "repos": list(b.extension_repos.keys()),
                }
                for b in state.blender_installations
            ],
            "antigravity": {
                "installed": state.antigravity.installed,
                "configured": state.antigravity.is_configured,
                "config_paths": [str(p) for p in state.antigravity.config_paths],
            },
            "codex": {
                "installed": state.codex.installed,
                "configured": state.codex.is_configured,
                "config_path": str(state.codex.config_path) if state.codex.config_path else None,
            },
            "bridge_running": state.is_bridge_running,
        }
        print(json.dumps(data, indent=2))
        return 0

    if args.repair:
        orch = InstallationOrchestrator()
        success, msg = orch.repair()
        print(f"[*] Repair result: {msg}")
        return 0 if success else 1

    if args.uninstall:
        orch = InstallationOrchestrator()
        success, logs = orch.uninstall(keep_workspace=True)
        print("[*] Uninstallation completed:")
        for line in logs:
            print(f"    - {line}")
        return 0 if success else 1

    if args.install:
        state = detect_system_state()
        options = InstallOptions(
            blender=state.recommended_blender,
            install_antigravity=not args.no_antigravity,
            install_codex=not args.no_codex,
            workspace_dir=pathlib.Path(args.workspace),
            port=args.port,
        )
        orch = InstallationOrchestrator(options)

        def print_progress(name: str, status: str, msg: str):
            print(f"[{status.upper():<7}] {name}: {msg}")

        success, steps = orch.run_installation(progress_callback=print_progress)
        print("=" * 60)
        if success:
            print("[+] BlenderAgent Bridge v0.2.0 installed successfully!")
            return 0
        else:
            print("[!] Installation encountered failures.")
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
