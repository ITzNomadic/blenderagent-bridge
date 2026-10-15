"""Object manipulation handlers (inspection, creation, and transformation)."""

from __future__ import annotations

import math
from typing import Any, Dict
try:
    import bpy
except ImportError:
    bpy = None

from ..security import InvalidArgumentError, ObjectNotFoundError


def _find_object(name: str) -> bpy.types.Object:
    if not bpy or not hasattr(bpy, "data"):
        raise ObjectNotFoundError(f"Blender environment not initialized: cannot find object '{name}'.")
    if not name or not isinstance(name, str):
        raise InvalidArgumentError("Object 'name' must be a non-empty string.")
    obj = bpy.data.objects.get(name)
    if not obj:
        available = [o.name for o in bpy.data.objects]
        raise ObjectNotFoundError(
            f"Object '{name}' not found in active scene.",
            details={"requested_name": name, "available_objects": available},
        )
    return obj


def handle_get_object_info(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Retrieve full structural and spatial info of a specific Blender object."""
    name = params.get("name")
    obj = _find_object(name)

    materials = [slot.material.name for slot in obj.material_slots if slot.material]
    modifiers = [
        {"name": m.name, "type": m.type, "show_viewport": m.show_viewport}
        for m in obj.modifiers
    ]

    return {
        "name": obj.name,
        "type": obj.type,
        "location": [round(float(v), 4) for v in obj.location],
        "rotation_euler_deg": [round(math.degrees(float(v)), 2) for v in obj.rotation_euler],
        "rotation_euler_rad": [round(float(v), 4) for v in obj.rotation_euler],
        "scale": [round(float(v), 4) for v in obj.scale],
        "dimensions": [round(float(v), 4) for v in obj.dimensions],
        "materials": materials,
        "modifiers": modifiers,
        "visible": not obj.hide_viewport,
    }


def handle_create_primitive(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Create a standard mesh primitive and assign transform properties."""
    raw_type = params.get("type", "cube")
    if not isinstance(raw_type, str):
        raise InvalidArgumentError("Primitive 'type' must be a string.")
    
    prim_type = raw_type.lower().strip()
    name = params.get("name")
    location = params.get("location", [0.0, 0.0, 0.0])
    scale = params.get("scale", [1.0, 1.0, 1.0])

    if not isinstance(location, (list, tuple)) or len(location) != 3:
        raise InvalidArgumentError("Location must be a list/tuple of 3 numbers: [x, y, z].")
    if not isinstance(scale, (list, tuple)) or len(scale) != 3:
        raise InvalidArgumentError("Scale must be a list/tuple of 3 numbers: [sx, sy, sz].")

    loc_tuple = (float(location[0]), float(location[1]), float(location[2]))
    scale_tuple = (float(scale[0]), float(scale[1]), float(scale[2]))

    # Dispatch primitive creation operator safely
    if prim_type == "cube":
        bpy.ops.mesh.primitive_cube_add(location=loc_tuple)
    elif prim_type in ("sphere", "uv_sphere"):
        bpy.ops.mesh.primitive_uv_sphere_add(location=loc_tuple)
    elif prim_type in ("ico_sphere", "icosphere"):
        bpy.ops.mesh.primitive_ico_sphere_add(location=loc_tuple)
    elif prim_type == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(location=loc_tuple)
    elif prim_type == "plane":
        bpy.ops.mesh.primitive_plane_add(location=loc_tuple)
    elif prim_type == "cone":
        bpy.ops.mesh.primitive_cone_add(location=loc_tuple)
    elif prim_type == "torus":
        bpy.ops.mesh.primitive_torus_add(location=loc_tuple)
    elif prim_type in ("monkey", "suzanne"):
        bpy.ops.mesh.primitive_monkey_add(location=loc_tuple)
    else:
        supported = ["cube", "sphere", "cylinder", "plane", "cone", "torus", "monkey"]
        raise InvalidArgumentError(
            f"Unsupported primitive type '{prim_type}'. Supported types: {supported}"
        )

    created_obj = bpy.context.active_object
    if not created_obj:
        raise InvalidArgumentError("Failed to instantiate primitive: active object is null.")

    if name and isinstance(name, str) and name.strip():
        created_obj.name = name.strip()

    created_obj.scale = scale_tuple

    return {
        "name": created_obj.name,
        "type": created_obj.type,
        "location": [round(float(v), 4) for v in created_obj.location],
        "scale": [round(float(v), 4) for v in created_obj.scale],
        "dimensions": [round(float(v), 4) for v in created_obj.dimensions],
    }


def handle_transform_object(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Modify spatial transformations (location, rotation, scale) of an existing object."""
    name = params.get("name")
    obj = _find_object(name)

    if "location" in params and params["location"] is not None:
        loc = params["location"]
        if not isinstance(loc, (list, tuple)) or len(loc) != 3:
            raise InvalidArgumentError("Location must be a list/tuple of 3 numbers: [x, y, z].")
        obj.location = (float(loc[0]), float(loc[1]), float(loc[2]))

    if "rotation" in params and params["rotation"] is not None:
        rot = params["rotation"]
        if not isinstance(rot, (list, tuple)) or len(rot) != 3:
            raise InvalidArgumentError("Rotation must be a list/tuple of 3 Euler angles in degrees: [rx, ry, rz].")
        obj.rotation_euler = (
            math.radians(float(rot[0])),
            math.radians(float(rot[1])),
            math.radians(float(rot[2])),
        )

    if "scale" in params and params["scale"] is not None:
        sc = params["scale"]
        if not isinstance(sc, (list, tuple)) or len(sc) != 3:
            raise InvalidArgumentError("Scale must be a list/tuple of 3 factors: [sx, sy, sz].")
        obj.scale = (float(sc[0]), float(sc[1]), float(sc[2]))

    return {
        "name": obj.name,
        "location": [round(float(v), 4) for v in obj.location],
        "rotation_euler_deg": [round(math.degrees(float(v)), 2) for v in obj.rotation_euler],
        "scale": [round(float(v), 4) for v in obj.scale],
        "dimensions": [round(float(v), 4) for v in obj.dimensions],
    }
