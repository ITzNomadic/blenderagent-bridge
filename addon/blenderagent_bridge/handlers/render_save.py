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
    BlenderAgentError,
    FileAlreadyExistsError,
    InvalidArgumentError,
    SecurityViolationError,
    validate_workspace_path,
)


def _parse_strict_bool(val: Any, default: bool = False, param_name: str = "parameter") -> bool:
    """Strictly parse a boolean parameter, rejecting ambiguous strings and non-boolean structures."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("true", "1", "yes"):
            return True
        if v in ("false", "0", "no"):
            return False
        raise InvalidArgumentError(f"Parameter '{param_name}' must be a boolean ('true'/'false'), got '{val}'.")
    if isinstance(val, (int, float)):
        return bool(val)
    raise InvalidArgumentError(f"Parameter '{param_name}' must be a boolean.")


def _get_workspace_dir(params: Dict[str, Any]) -> pathlib.Path:
    """Resolve the authoritative workspace directory from server configuration."""
    # 1. Authoritative server configuration
    try:
        from ..server import bridge_server
        if bridge_server and bridge_server.workspace:
            return bridge_server.workspace.resolve()
    except Exception:
        pass

    # 2. Local scene property configured in Blender UI
    scene = getattr(bpy, "context", None)
    if scene and hasattr(scene, "scene") and hasattr(scene.scene, "blenderagent_workspace_dir"):
        ws_val = scene.scene.blenderagent_workspace_dir.strip()
        if ws_val:
            return pathlib.Path(ws_val).resolve()

    # 3. Environment variable fallback
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

    overwrite = _parse_strict_bool(params.get("overwrite"), default=True, param_name="overwrite")
    if target_path.exists() and not overwrite:
        raise FileAlreadyExistsError(
            f"Render target file '{raw_filename}' already exists. Set 'overwrite=true' to replace it.",
            details={"file_path": str(target_path)},
        )

    # Parameter boundaries
    try:
        w_val = int(params.get("width", 640))
        h_val = int(params.get("height", 480))
        s_val = int(params.get("samples", 32))
        if not (64 <= w_val <= 4096 and 64 <= h_val <= 4096 and 1 <= s_val <= 512):
            raise ValueError("Values outside allowable range.")
        width = w_val
        height = h_val
        samples = s_val
    except Exception as err:
        raise InvalidArgumentError(f"Render dimensions (64..4096) and samples (1..512) must be positive integers: {err}")

    if not bpy or not hasattr(bpy, "context") or not bpy.context:
        raise BlenderAgentError("ENV_NOT_INITIALIZED", "Blender environment not initialized: cannot perform render.")

    scene = bpy.context.scene

    # Verify or create camera
    if not scene.camera:
        cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
        if cams:
            scene.camera = cams[0]
        else:
            cam_data = bpy.data.cameras.new(name="Camera")
            cam_obj = bpy.data.objects.new(name="Camera", object_data=cam_data)
            cam_obj.location = (5.0, -5.0, 4.0)
            cam_obj.rotation_euler = (1.1, 0.0, 0.8)
            scene.collection.objects.link(cam_obj)
            scene.camera = cam_obj

    # Save original settings for guaranteed restoration
    orig_x = scene.render.resolution_x
    orig_y = scene.render.resolution_y
    orig_pct = scene.render.resolution_percentage
    orig_fmt = scene.render.image_settings.file_format
    orig_filepath = scene.render.filepath
    orig_cycles_samples = getattr(scene.cycles, "samples", None) if hasattr(scene, "cycles") else None
    orig_eevee_samples = getattr(scene.eevee, "taa_render_samples", None) if hasattr(scene, "eevee") else None

    try:
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
            if hasattr(scene.eevee, "taa_render_samples"):
                scene.eevee.taa_render_samples = min(samples, 64)

        # Perform render synchronously on main thread
        bpy.ops.render.render(write_still=True)
    finally:
        # Always restore original scene render settings
        scene.render.resolution_x = orig_x
        scene.render.resolution_y = orig_y
        scene.render.resolution_percentage = orig_pct
        scene.render.image_settings.file_format = orig_fmt
        scene.render.filepath = orig_filepath
        if orig_cycles_samples is not None and hasattr(scene, "cycles"):
            scene.cycles.samples = orig_cycles_samples
        if orig_eevee_samples is not None and hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = orig_eevee_samples

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

    overwrite = _parse_strict_bool(params.get("overwrite"), default=False, param_name="overwrite")
    if target_path.exists() and not overwrite:
        raise FileAlreadyExistsError(
            f"File '{filename}' already exists in workspace. Set 'overwrite=true' to overwrite it.",
            details={"file_path": str(target_path), "size_bytes": target_path.stat().st_size},
        )

    # Save copy of current mainfile
    as_copy = _parse_strict_bool(params.get("copy"), default=True, param_name="copy")
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


def handle_capture_viewport(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Capture rapid viewport buffer (OpenGL / Workbench) without full path-tracing overhead."""
    workspace = _get_workspace_dir(params)

    raw_filename = params.get("output_filename", "renders/viewport.png")
    if not isinstance(raw_filename, str) or not raw_filename.strip():
        raw_filename = "renders/viewport.png"
    if not (raw_filename.endswith(".png") or raw_filename.endswith(".jpg")):
        raw_filename += ".png"

    target_path = validate_workspace_path(workspace, raw_filename, allow_create_dir=True)

    overwrite = _parse_strict_bool(params.get("overwrite"), default=True, param_name="overwrite")
    if target_path.exists() and not overwrite:
        raise FileAlreadyExistsError(
            f"Viewport capture file '{raw_filename}' already exists. Set 'overwrite=true' to replace it.",
            details={"file_path": str(target_path)},
        )

    try:
        w_val = int(params.get("width", 640))
        h_val = int(params.get("height", 480))
        if not (64 <= w_val <= 1920 and 64 <= h_val <= 1080):
            raise ValueError("Dimensions out of range [64..1920] x [64..1080]")
        width = w_val
        height = h_val
    except Exception as err:
        raise InvalidArgumentError(f"Viewport capture dimensions must be integers in 64..1920 x 64..1080: {err}")

    if not bpy or not hasattr(bpy, "context") or not bpy.context:
        raise BlenderAgentError("ENV_NOT_INITIALIZED", "Blender environment not initialized: cannot capture viewport.")

    scene = bpy.context.scene
    if not scene.camera:
        cams = [o for o in bpy.data.objects if o.type == "CAMERA"]
        if cams:
            scene.camera = cams[0]
        else:
            cam_data = bpy.data.cameras.new(name="Camera")
            cam_obj = bpy.data.objects.new(name="Camera", object_data=cam_data)
            cam_obj.location = (5.0, -5.0, 4.0)
            cam_obj.rotation_euler = (1.1, 0.0, 0.8)
            scene.collection.objects.link(cam_obj)
            scene.camera = cam_obj

    # Save original settings for guaranteed restoration
    orig_x = scene.render.resolution_x
    orig_y = scene.render.resolution_y
    orig_pct = scene.render.resolution_percentage
    orig_fmt = scene.render.image_settings.file_format
    orig_filepath = scene.render.filepath
    orig_cycles_samples = getattr(scene.cycles, "samples", None) if hasattr(scene, "cycles") else None

    captured_opengl = False
    try:
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(target_path)

        if not bpy.app.background:
            try:
                bpy.ops.render.opengl(write_still=True)
                captured_opengl = True
            except Exception:
                pass

        if not captured_opengl:
            # Fallback to fast 4-sample render
            if hasattr(scene, "cycles"):
                scene.cycles.samples = 4
            bpy.ops.render.render(write_still=True)
    finally:
        # Restore all settings in finally
        scene.render.resolution_x = orig_x
        scene.render.resolution_y = orig_y
        scene.render.resolution_percentage = orig_pct
        scene.render.image_settings.file_format = orig_fmt
        scene.render.filepath = orig_filepath
        if orig_cycles_samples is not None and hasattr(scene, "cycles"):
            scene.cycles.samples = orig_cycles_samples

    if not target_path.exists():
        raise InvalidArgumentError(f"Viewport capture failed: '{target_path.name}' was not created.")

    file_size = target_path.stat().st_size
    rel_path = str(target_path.relative_to(workspace)).replace("\\", "/")

    return {
        "file_path": str(target_path).replace("\\", "/"),
        "relative_path": rel_path,
        "width": width,
        "height": height,
        "file_size_bytes": file_size,
        "mode": "opengl" if captured_opengl else "render_fallback",
    }
