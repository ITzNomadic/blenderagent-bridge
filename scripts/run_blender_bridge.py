"""Runner script to launch Blender and start BlenderAgent Bridge in headless or interactive mode."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time

# Ensure addon is on sys.path
repo_root = pathlib.Path(__file__).parent.parent.resolve()
addon_path = repo_root / "addon"
if str(addon_path) not in sys.path:
    sys.path.insert(0, str(addon_path))

try:
    import bpy
except ImportError:
    print("ERROR: This script must be run inside Blender using: blender -P scripts/run_blender_bridge.py")
    sys.exit(1)

import blenderagent_bridge
from blenderagent_bridge.queue_manager import queue_manager
from blenderagent_bridge.server import bridge_server


def parse_args():
    # Blender arguments come before '--', custom script arguments come after '--'
    argv = sys.argv
    if "--" in argv:
        custom_argv = argv[argv.index("--") + 1:]
    else:
        custom_argv = []

    parser = argparse.ArgumentParser(description="BlenderAgent Bridge Runner")
    parser.add_argument("--port", type=int, default=int(os.environ.get("BLENDERAGENT_PORT", 9876)))
    parser.add_argument("--token", type=str, default=os.environ.get("BLENDERAGENT_TOKEN", ""))
    parser.add_argument("--workspace", type=str, default=os.environ.get("BLENDERAGENT_WORKSPACE", str(repo_root / "workspace")))
    parser.add_argument("--duration", type=float, default=0.0, help="Run for N seconds then exit (0 = run indefinitely until stopped)")
    return parser.parse_args(custom_argv)


def main():
    args = parse_args()
    print(f"[BlenderAgent Runner] Registering BlenderAgent Bridge addon...")
    blenderagent_bridge.register()

    # Configure runtime properties on WindowManager
    wm = getattr(bpy.context, "window_manager", None)
    if wm and hasattr(wm, "blenderagent_port"):
        wm.blenderagent_port = args.port
        if args.token:
            wm.blenderagent_token = args.token
        wm.blenderagent_workspace_dir = args.workspace

    # Also configure scene if present for fallback
    scene = getattr(bpy.context, "scene", None)
    if scene and hasattr(scene, "blenderagent_port"):
        scene.blenderagent_port = args.port
        scene.blenderagent_workspace_dir = args.workspace

    print(f"[BlenderAgent Runner] Starting bridge on port {args.port} (Workspace: {args.workspace})...")
    res = bpy.ops.wm.blenderagent_start_bridge()
    if res != {"FINISHED"}:
        print(f"[BlenderAgent Runner] Failed to start bridge operator: {res}")
        sys.exit(1)

    print(f"[BlenderAgent Runner] Bridge successfully started. Token: {scene.blenderagent_token}")
    print(f"[BlenderAgent Runner] Ready for agent connections.")

    # In background/headless mode (-b), keep the main thread pumping
    if bpy.app.background:
        start_time = time.time()
        try:
            while bridge_server.is_running:
                queue_manager.process_queue_tick()
                time.sleep(0.01)
                if args.duration > 0 and (time.time() - start_time) >= args.duration:
                    print(f"[BlenderAgent Runner] Duration reached ({args.duration}s). Stopping.")
                    break
        except KeyboardInterrupt:
            print("\n[BlenderAgent Runner] KeyboardInterrupt received. Shutting down...")
        finally:
            blenderagent_bridge.unregister()
            print("[BlenderAgent Runner] Unregistered and exited cleanly.")


if __name__ == "__main__":
    main()
