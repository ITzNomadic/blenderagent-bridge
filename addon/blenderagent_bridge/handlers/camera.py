"""Camera setup and scene observation handlers."""

from __future__ import annotations

import math
from typing import Any, Dict
try:
    import bpy
except ImportError:
    bpy = None

from ..security import BlenderAgentError, InvalidArgumentError
from .objects import _parse_vector_3d


def handle_set_camera(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Create or update camera position, orientation, focal length, and active scene camera."""
    cam_name = params.get("camera_name", "Camera")
    if not isinstance(cam_name, str) or not cam_name.strip():
        cam_name = "Camera"

    location = params.get("location")
    rotation = params.get("rotation")
    make_active = bool(params.get("make_active", True))

    try:
        raw_fl = float(params.get("focal_length", 50.0))
        if not (math.isfinite(raw_fl) and 1.0 <= raw_fl <= 500.0):
            raise ValueError()
        focal_length = raw_fl
    except Exception:
        raise InvalidArgumentError("focal_length must be a finite float between 1.0 and 500.0 mm.")

    parsed_loc = _parse_vector_3d(location, "location") if location is not None else None
    parsed_rot = _parse_vector_3d(rotation, "rotation") if rotation is not None else None

    if not bpy or not hasattr(bpy, "data"):
        raise BlenderAgentError("Blender environment not initialized: cannot configure camera.")

    cam_obj = bpy.data.objects.get(cam_name)
    if not cam_obj or cam_obj.type != "CAMERA":
        cam_data = bpy.data.cameras.new(name=cam_name)
        cam_obj = bpy.data.objects.new(name=cam_name, object_data=cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)

    if parsed_loc is not None:
        cam_obj.location = parsed_loc

    if parsed_rot is not None:
        cam_obj.rotation_euler = (
            math.radians(parsed_rot[0]),
            math.radians(parsed_rot[1]),
            math.radians(parsed_rot[2]),
        )

    if hasattr(cam_obj.data, "lens"):
        cam_obj.data.lens = focal_length

    if make_active:
        bpy.context.scene.camera = cam_obj

    # Basic illumination check: ensure at least one light exists in scene
    existing_lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
    light_created = False
    if not existing_lights:
        light_data = bpy.data.lights.new(name="SunLight", type="SUN")
        light_data.energy = 2.5
        light_obj = bpy.data.objects.new(name="SunLight", object_data=light_data)
        light_obj.location = (5.0, -5.0, 10.0)
        bpy.context.scene.collection.objects.link(light_obj)
        light_created = True

    return {
        "camera_name": cam_obj.name,
        "location": [round(float(v), 4) for v in cam_obj.location],
        "rotation_euler_deg": [round(math.degrees(float(v)), 2) for v in cam_obj.rotation_euler],
        "is_active_scene_camera": (bpy.context.scene.camera == cam_obj),
        "focal_length": cam_obj.data.lens if hasattr(cam_obj.data, "lens") else focal_length,
        "lighting_ensured": light_created or bool(existing_lights),
    }
