"""BlenderAgent Bridge Add-on entry point and registration."""

from __future__ import annotations

bl_info = {
    "name": "BlenderAgent Bridge",
    "author": "BlenderAgent Team",
    "version": (0, 2, 0),
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


def unregister():
    """Gracefully stop active server and unregister all components."""
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
