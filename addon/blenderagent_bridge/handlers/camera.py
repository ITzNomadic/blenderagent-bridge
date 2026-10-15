"""Camera setup and scene observation handlers."""

from __future__ import annotations

import math
from typing import Any, Dict
try:
    import bpy
except ImportError:
    bpy = None

from ..security import InvalidArgumentError


def handle_set_camera(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Create or update camera position, orientation, focal length, and active scene camera."""
    cam_name = params.get("camera_name", "Camera")
    if not isinstance(cam_name, str) or not cam_name.strip():
        cam_name = "Camera"

    location = params.get("location")
    rotation = params.get("rotation")
    make_active = bool(params.get("make_active", True))
    focal_length = float(params.get("focal_length", 50.0))

    cam_obj = bpy.data.objects.get(cam_name)
    if not cam_obj or cam_obj.type != "CAMERA":
        cam_data = bpy.data.cameras.new(name=cam_name)
        cam_obj = bpy.data.objects.new(name=cam_name, object_data=cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)

    if location is not None:
        if not isinstance(location, (list, tuple)) or len(location) != 3:
            raise InvalidArgumentError("Location must be a list/tuple of 3 numbers: [x, y, z].")
        cam_obj.location = (float(location[0]), float(location[1]), float(location[2]))

    if rotation is not None:
        if not isinstance(rotation, (list, tuple)) or len(rotation) != 3:
            raise InvalidArgumentError("Rotation must be a list/tuple of 3 Euler angles in degrees: [rx, ry, rz].")
        cam_obj.rotation_euler = (
            math.radians(float(rotation[0])),
            math.radians(float(rotation[1])),
            math.radians(float(rotation[2])),
        )

    if hasattr(cam_obj.data, "lens"):
        cam_obj.data.lens = max(1.0, min(500.0, focal_length))

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
