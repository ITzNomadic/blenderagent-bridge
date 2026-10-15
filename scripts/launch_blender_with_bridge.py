"""Startup script to launch Blender with BlenderAgent Bridge automatically started."""

import os
import pathlib
import bpy

def start_bridge_deferred():
    try:
        wm = bpy.context.window_manager
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            ws = str(pathlib.Path(local_appdata) / "BlenderAgentBridge" / "workspace")
        else:
            ws = str(pathlib.Path.home() / "AppData" / "Local" / "BlenderAgentBridge" / "workspace")

        if hasattr(wm, "blenderagent_workspace_dir"):
            wm.blenderagent_workspace_dir = ws
        if hasattr(bpy.context.scene, "blenderagent_workspace_dir"):
            bpy.context.scene.blenderagent_workspace_dir = ws

        bpy.ops.wm.blenderagent_start_bridge()
        print("[+] BlenderAgent Bridge auto-started successfully on port 9876 with workspace:", ws)
    except Exception as err:
        print(f"[!] Error auto-starting bridge: {err}")
    return None

bpy.app.timers.register(start_bridge_deferred, first_interval=1.0)
