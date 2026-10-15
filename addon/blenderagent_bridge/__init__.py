"""BlenderAgent Bridge Add-on entry point and registration."""

from __future__ import annotations

bl_info = {
    "name": "BlenderAgent Bridge",
    "author": "BlenderAgent Team",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > BlenderAgent",
    "description": "Structured, verifiable, and secure MCP control bridge for Blender",
    "category": "Development",
    "doc_url": "https://github.com/blenderagent/blenderagent-bridge",
}

import os
import pathlib
import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.utils import register_class, unregister_class

from .operator import OPERATOR_CLASSES
from .panel import PANEL_CLASSES
from .security import generate_session_token
from .server import bridge_server

ALL_CLASSES = OPERATOR_CLASSES + PANEL_CLASSES


def _init_properties():
    bpy.types.Scene.blenderagent_is_running = BoolProperty(
        name="Bridge Active",
        description="Whether the local bridge server is actively running",
        default=False,
    )
    bpy.types.Scene.blenderagent_port = IntProperty(
        name="Port",
        description="Localhost port for HTTP transport",
        default=int(os.environ.get("BLENDERAGENT_PORT", 9876)),
        min=1024,
        max=65535,
    )
    bpy.types.Scene.blenderagent_token = StringProperty(
        name="Session Token",
        description="Cryptographic Bearer token for local API authentication",
        default="",
        subtype="NONE",
    )
    default_ws = os.environ.get("BLENDERAGENT_WORKSPACE", "")
    if not default_ws:
        default_ws = str(pathlib.Path.cwd() / "workspace")
    bpy.types.Scene.blenderagent_workspace_dir = StringProperty(
        name="Workspace Directory",
        description="Authorized directory for saving scenes and rendering previews",
        default=default_ws,
        subtype="DIR_PATH",
    )


def _clear_properties():
    props = [
        "blenderagent_is_running",
        "blenderagent_port",
        "blenderagent_token",
        "blenderagent_workspace_dir",
    ]
    for prop in props:
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)


def register():
    """Register all classes, operators, panels, and properties."""
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
