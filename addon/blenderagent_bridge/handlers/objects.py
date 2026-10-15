"""Object manipulation handlers (inspection, creation, and transformation)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
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


def _parse_vector_3d(v: Any, param_name: str) -> Tuple[float, float, float]:
    """Strictly parse and validate a 3D float coordinate vector."""
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise InvalidArgumentError(f"'{param_name}' must be a list/tuple of 3 numbers: [x, y, z].")
    parsed: List[float] = []
    for idx, val in enumerate(v):
        try:
            fv = float(val)
            if not math.isfinite(fv):
                raise ValueError()
            parsed.append(fv)
        except Exception:
            raise InvalidArgumentError(f"'{param_name}' element at index {idx} must be a finite number, got {val}.")
    return (parsed[0], parsed[1], parsed[2])


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
    loc_tuple = _parse_vector_3d(params.get("location", [0.0, 0.0, 0.0]), "location")
    scale_tuple = _parse_vector_3d(params.get("scale", [1.0, 1.0, 1.0]), "scale")

    for idx, s in enumerate(scale_tuple):
        if abs(s) < 1e-6:
            raise InvalidArgumentError(f"Scale factor at index {idx} cannot be zero.")

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

    requested_name: Optional[str] = None
    if name and isinstance(name, str) and name.strip():
        requested_name = name.strip()
        created_obj.name = requested_name

    actual_name = created_obj.name
    was_renamed = bool(requested_name is not None and actual_name != requested_name)

    created_obj.scale = scale_tuple

    return {
        "name": actual_name,
        "requested_name": requested_name,
        "renamed": was_renamed,
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
        obj.location = _parse_vector_3d(params["location"], "location")

    if "rotation" in params and params["rotation"] is not None:
        rot_deg = _parse_vector_3d(params["rotation"], "rotation")
        obj.rotation_euler = (
            math.radians(rot_deg[0]),
            math.radians(rot_deg[1]),
            math.radians(rot_deg[2]),
        )

    if "scale" in params and params["scale"] is not None:
        sc = _parse_vector_3d(params["scale"], "scale")
        for idx, s in enumerate(sc):
            if abs(s) < 1e-6:
                raise InvalidArgumentError(f"Scale factor at index {idx} cannot be zero.")
        obj.scale = sc

    return {
        "name": obj.name,
        "location": [round(float(v), 4) for v in obj.location],
        "rotation_euler_deg": [round(math.degrees(float(v)), 2) for v in obj.rotation_euler],
        "scale": [round(float(v), 4) for v in obj.scale],
        "dimensions": [round(float(v), 4) for v in obj.dimensions],
    }
