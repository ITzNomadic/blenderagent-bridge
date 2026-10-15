"""Command handlers registry and dispatcher for BlenderAgent Bridge."""

from __future__ import annotations

from typing import Any, Callable, Dict

from ..security import InvalidArgumentError
from .camera import handle_set_camera
from .materials import handle_set_material
from .objects import (
    handle_create_primitive,
    handle_get_mesh_info,
    handle_get_object_info,
    handle_transform_object,
)
from .render_save import handle_capture_viewport, handle_render_preview, handle_save_project
from .scene import handle_get_scene_info

HANDLER_REGISTRY: Dict[str, Callable[[Dict[str, Any], Any], Dict[str, Any]]] = {
    "get_scene_info": handle_get_scene_info,
    "get_object_info": handle_get_object_info,
    "get_mesh_info": handle_get_mesh_info,
    "create_primitive": handle_create_primitive,
    "transform_object": handle_transform_object,
    "set_material": handle_set_material,
    "set_camera": handle_set_camera,
    "render_preview": handle_render_preview,
    "capture_viewport": handle_capture_viewport,
    "save_project": handle_save_project,
}


def dispatch_command(command_name: str, params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Dispatch a validated command to its registered handler."""
    handler = HANDLER_REGISTRY.get(command_name)
    if not handler:
        supported = list(HANDLER_REGISTRY.keys())
        raise InvalidArgumentError(
            f"Unknown command '{command_name}'. Supported commands: {supported}",
            details={"requested_command": command_name, "supported_commands": supported},
        )
    return handler(params, context)


__all__ = [
    "HANDLER_REGISTRY",
    "dispatch_command",
    "handle_get_scene_info",
    "handle_get_object_info",
    "handle_get_mesh_info",
    "handle_create_primitive",
    "handle_transform_object",
    "handle_set_material",
    "handle_set_camera",
    "handle_render_preview",
    "handle_capture_viewport",
    "handle_save_project",
]
