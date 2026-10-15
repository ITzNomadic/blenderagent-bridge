"""Render preview and project save handlers with strict workspace directory containment."""

from __future__ import annotations

import os
import pathlib
from typing import Any, Dict
try:
    import bpy
except ImportError:
    bpy = None

from ..security import (
    FileAlreadyExistsError,
    InvalidArgumentError,
    SecurityViolationError,
    validate_workspace_path,
)


def _get_workspace_dir(params: Dict[str, Any]) -> pathlib.Path:
    """Resolve the authorized workspace directory."""
    # 1. Check params
    ws_param = params.get("workspace_dir")
    if ws_param:
        return pathlib.Path(ws_param).resolve()

    # 2. Check scene property
    scene = getattr(bpy.context, "scene", None)
    if scene and hasattr(scene, "blenderagent_workspace_dir") and scene.blenderagent_workspace_dir:
        return pathlib.Path(scene.blenderagent_workspace_dir).resolve()

    # 3. Check environment variable
    env_ws = os.environ.get("BLENDERAGENT_WORKSPACE")
    if env_ws:
        return pathlib.Path(env_ws).resolve()

    # 4. Fallback to current working directory
    return pathlib.Path.cwd().resolve()


def handle_render_preview(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Render a preview frame and write it safely into the workspace."""
    workspace = _get_workspace_dir(params)

    # Validate output filename
    raw_filename = params.get("output_filename", "renders/preview.png")
    if not isinstance(raw_filename, str) or not raw_filename.strip():
        raw_filename = "renders/preview.png"
    if not (raw_filename.endswith(".png") or raw_filename.endswith(".jpg")):
        raw_filename += ".png"

    target_path = validate_workspace_path(workspace, raw_filename, allow_create_dir=True)

    # Parameter boundaries
    try:
        width = max(64, min(4096, int(params.get("width", 640))))
        height = max(64, min(4096, int(params.get("height", 480))))
        samples = max(1, min(512, int(params.get("samples", 32))))
    except (TypeError, ValueError) as err:
        raise InvalidArgumentError(f"Render dimensions and samples must be positive integers: {err}")

    scene = bpy.context.scene

    # Verify or create camera
    if not scene.camera:
        # Search for any camera in scene
        cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
        if cams:
            scene.camera = cams[0]
        else:
            # Create a default camera
            cam_data = bpy.data.cameras.new(name="Camera")
            cam_obj = bpy.data.objects.new(name="Camera", object_data=cam_data)
            cam_obj.location = (5.0, -5.0, 4.0)
            cam_obj.rotation_euler = (1.1, 0.0, 0.8)
            scene.collection.objects.link(cam_obj)
            scene.camera = cam_obj

    # Configure render settings
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(target_path)

    # Configure sampling depending on engine
    if scene.render.engine == "CYCLES":
        if hasattr(scene, "cycles"):
            scene.cycles.samples = samples
    elif hasattr(scene, "eevee"):
        # Eevee Next / standard Eevee
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = min(samples, 64)

    # Perform render synchronously on main thread
    bpy.ops.render.render(write_still=True)

    if not target_path.exists():
        raise InvalidArgumentError(f"Render completed but output file '{target_path.name}' was not created.")

    file_size = target_path.stat().st_size
    rel_path = str(target_path.relative_to(workspace)).replace("\\", "/")

    return {
        "file_path": str(target_path).replace("\\", "/"),
        "relative_path": rel_path,
        "width": width,
        "height": height,
        "samples": samples,
        "file_size_bytes": file_size,
    }


def handle_save_project(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Save a copy of the active Blender project within the workspace."""
    workspace = _get_workspace_dir(params)

    raw_filename = params.get("filename")
    if not raw_filename or not isinstance(raw_filename, str) or not raw_filename.strip():
        raise InvalidArgumentError("Missing required parameter: 'filename'.")

    filename = raw_filename.strip()
    if not filename.endswith(".blend"):
        filename += ".blend"

    target_path = validate_workspace_path(workspace, filename, allow_create_dir=True)

    overwrite = bool(params.get("overwrite", False))
    if target_path.exists() and not overwrite:
        raise FileAlreadyExistsError(
            f"File '{filename}' already exists in workspace. Set 'overwrite=true' to overwrite it.",
            details={"file_path": str(target_path), "size_bytes": target_path.stat().st_size},
        )

    # Save copy of current mainfile
    as_copy = bool(params.get("copy", True))
    bpy.ops.wm.save_as_mainfile(filepath=str(target_path), copy=as_copy)

    if not target_path.exists():
        raise InvalidArgumentError(f"Save operation failed: '{target_path.name}' was not generated.")

    file_size = target_path.stat().st_size
    rel_path = str(target_path.relative_to(workspace)).replace("\\", "/")

    return {
        "file_path": str(target_path).replace("\\", "/"),
        "relative_path": rel_path,
        "file_size_bytes": file_size,
        "is_copy": as_copy,
    }
