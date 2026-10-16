"""BlenderAgent Bridge Add-on entry point and registration."""

from __future__ import annotations

bl_info = {
    "name": "BlenderAgent Bridge",
    "author": "BlenderAgent Team",
    "version": (0, 2, 1),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > BlenderAgent",
    "description": "Structured, verifiable, and secure MCP control bridge for Blender",
    "category": "Development",
    "doc_url": "https://github.com/ITzNomadic/blenderagent-bridge",
}

import os
import pathlib
try:
    import bpy
    from bpy.props import BoolProperty, IntProperty, StringProperty
    from bpy.utils import register_class, unregister_class
except ImportError:
    bpy = None

from .operator import OPERATOR_CLASSES
from .panel import PANEL_CLASSES
from .security import generate_session_token
from .server import bridge_server

ALL_CLASSES = OPERATOR_CLASSES + PANEL_CLASSES


def _init_properties():
    if not bpy:
        return
    # 1. Register runtime-only properties on WindowManager (NEVER saved to .blend files)
    bpy.types.WindowManager.blenderagent_is_running = BoolProperty(
        name="Bridge Active",
        description="Whether the local bridge server is actively running",
        default=False,
    )
    bpy.types.WindowManager.blenderagent_port = IntProperty(
        name="Port",
        description="Localhost port for HTTP transport",
        default=int(os.environ.get("BLENDERAGENT_PORT", 9876)),
        min=1024,
        max=65535,
    )
    bpy.types.WindowManager.blenderagent_token = StringProperty(
        name="Session Token",
        description="Transient cryptographic Bearer token (never saved in .blend)",
        default="",
        subtype="PASSWORD",
    )
    default_ws = os.environ.get("BLENDERAGENT_WORKSPACE", "")
    if not default_ws:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            default_ws = str(pathlib.Path(local_appdata) / "BlenderAgentBridge" / "workspace")
        else:
            default_ws = str(pathlib.Path.home() / ".blenderagent" / "workspace")
    bpy.types.WindowManager.blenderagent_workspace_dir = StringProperty(
        name="Workspace Directory",
        description="Authorized directory for saving scenes and rendering previews",
        default=default_ws,
        subtype="DIR_PATH",
    )

    # 2. Register non-sensitive aliases on Scene for backward compatibility
    bpy.types.Scene.blenderagent_is_running = BoolProperty(
        name="Bridge Active",
        default=False,
    )
    bpy.types.Scene.blenderagent_port = IntProperty(
        name="Port",
        default=int(os.environ.get("BLENDERAGENT_PORT", 9876)),
        min=1024,
        max=65535,
    )
    bpy.types.Scene.blenderagent_workspace_dir = StringProperty(
        name="Workspace Directory",
        default=default_ws,
        subtype="DIR_PATH",
    )


def _clear_properties():
    if not bpy:
        return
    wm_props = [
        "blenderagent_is_running",
        "blenderagent_port",
        "blenderagent_token",
        "blenderagent_workspace_dir",
    ]
    for prop in wm_props:
        if hasattr(bpy.types.WindowManager, prop):
            delattr(bpy.types.WindowManager, prop)

    scene_props = [
        "blenderagent_is_running",
        "blenderagent_port",
        "blenderagent_workspace_dir",
    ]
    for prop in scene_props:
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)


def _auto_start_bridge_on_load():
    """Automatically initialize credentials and start the local bridge on Blender launch."""
    try:
        if bridge_server.is_running:
            return None

        # 1. Determine authorized workspace
        default_ws = os.environ.get("BLENDERAGENT_WORKSPACE", "")
        if not default_ws:
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                default_ws = str(pathlib.Path(local_appdata) / "BlenderAgentBridge" / "workspace")
            else:
                default_ws = str(pathlib.Path.home() / ".blenderagent" / "workspace")
        ws_path = pathlib.Path(default_ws).resolve()
        ws_path.mkdir(parents=True, exist_ok=True)

        port = int(os.environ.get("BLENDERAGENT_PORT", 9876))

        # 2. Check for existing valid session token (workspace or global live session)
        token = None
        session_file = ws_path / ".blenderagent_session.json"
        if session_file.exists():
            try:
                import json
                with open(session_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                tok = saved.get("token")
                if tok and isinstance(tok, str) and len(tok) == 32:
                    token = tok
            except Exception:
                pass

        if not token:
            try:
                from .security import get_global_session_file
                glob_f = get_global_session_file()
                if glob_f.exists():
                    import json
                    with open(glob_f, "r", encoding="utf-8") as gf:
                        saved = json.load(gf)
                    tok = saved.get("token")
                    if tok and isinstance(tok, str) and len(tok) == 32:
                        token = tok
            except Exception:
                pass

        # 3. If no existing valid token, generate a fresh cryptographic token automatically
        if not token:
            token = generate_session_token()

        # 4. Start the bridge HTTP server and main-thread task consumer
        success, msg = bridge_server.start(port=port, token=token, workspace_dir=ws_path)
        if success and bpy and hasattr(bpy, "context") and hasattr(bpy.context, "window_manager"):
            wm = bpy.context.window_manager
            if wm:
                wm.blenderagent_is_running = True
                wm.blenderagent_port = port
                wm.blenderagent_token = token
                wm.blenderagent_workspace_dir = str(ws_path)
    except Exception as err:
        print(f"[BlenderAgent Bridge] Auto-start notice: {err}")
    return None


def register():
    """Register all classes, operators, panels, and properties."""
    if not bpy:
        return
    for cls in ALL_CLASSES:
        try:
            register_class(cls)
        except ValueError:
            # Already registered
            pass

    _init_properties()

    # Schedule non-blocking auto-start once Blender finishes loading
    if hasattr(bpy, "app") and hasattr(bpy.app, "timers"):
        if not bpy.app.timers.is_registered(_auto_start_bridge_on_load):
            bpy.app.timers.register(_auto_start_bridge_on_load, first_interval=0.2, persistent=True)
    else:
        _auto_start_bridge_on_load()


def unregister():
    """Gracefully stop active server and unregister all components."""
    if bpy and hasattr(bpy, "app") and hasattr(bpy.app, "timers"):
        if bpy.app.timers.is_registered(_auto_start_bridge_on_load):
            try:
                bpy.app.timers.unregister(_auto_start_bridge_on_load)
            except Exception:
                pass

    # 1. Stop active server and timer
    try:
        bridge_server.stop()
    except Exception:
        pass

    # 2. Unregister classes safely
    for cls in reversed(ALL_CLASSES):
        try:
            unregister_class(cls)
        except Exception:
            pass

    # 3. Clean properties
    _clear_properties()


if __name__ == "__main__":
    register()
