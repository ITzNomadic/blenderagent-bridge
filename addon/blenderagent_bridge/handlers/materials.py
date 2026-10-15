"""Material assignment handlers utilizing Blender's Principled BSDF node system."""

from __future__ import annotations

from typing import Any, Dict
try:
    import bpy
except ImportError:
    bpy = None

from ..security import InvalidArgumentError, ObjectNotFoundError
from .objects import _find_object


def handle_set_material(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Configure or create a Principled BSDF material and assign it to an object."""
    raw_color = params.get("color", [0.8, 0.8, 0.8, 1.0])
    if not isinstance(raw_color, (list, tuple)) or len(raw_color) not in (3, 4):
        raise InvalidArgumentError("Color must be a list of 3 (RGB) or 4 (RGBA) numbers in [0.0, 1.0].")

    import math
    color_floats = []
    for idx, c in enumerate(raw_color):
        try:
            fc = float(c)
            if not math.isfinite(fc) or not (0.0 <= fc <= 1.0):
                raise ValueError()
            color_floats.append(fc)
        except Exception:
            raise InvalidArgumentError(f"Color component at index {idx} must be a finite float in [0.0, 1.0], got {c}.")

    if len(color_floats) == 3:
        color_floats.append(1.0)  # Alpha default
    color_rgba = tuple(color_floats)

    try:
        raw_m = float(params.get("metallic", 0.0))
        raw_r = float(params.get("roughness", 0.5))
        if not (math.isfinite(raw_m) and 0.0 <= raw_m <= 1.0):
            raise ValueError(f"Invalid metallic value '{raw_m}'")
        if not (math.isfinite(raw_r) and 0.0 <= raw_r <= 1.0):
            raise ValueError(f"Invalid roughness value '{raw_r}'")
        metallic = raw_m
        roughness = raw_r
    except Exception as err:
        raise InvalidArgumentError(f"Metallic and Roughness must be finite floats in [0.0, 1.0]: {err}")

    name = params.get("name")
    obj = _find_object(name)

    mat_name = params.get("material_name") or f"{obj.name}_Material"
    if not isinstance(mat_name, str) or not mat_name.strip():
        mat_name = f"{obj.name}_Material"

    # Find or create material
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)

    mat.use_nodes = True
    node_tree = mat.node_tree
    nodes = node_tree.nodes

    # Find or create Principled BSDF
    bsdf = None
    for node in nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break

    if not bsdf:
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        # Find or create Material Output
        output_node = None
        for node in nodes:
            if node.type == "OUTPUT_MATERIAL":
                output_node = node
                break
        if not output_node:
            output_node = nodes.new(type="ShaderNodeOutputMaterial")
        node_tree.links.new(bsdf.outputs["BSDF"], output_node.inputs["Surface"])

    # Configure Principled BSDF inputs (compatible with Blender 4.0, 4.5 LTS, 5.2 LTS)
    if "Base Color" in bsdf.inputs:
        bsdf.inputs["Base Color"].default_value = color_rgba
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = metallic
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = roughness

    # Synchronize with Viewport Display settings (essential for Solid Shading mode)
    try:
        mat.diffuse_color = color_rgba
        if hasattr(mat, "roughness"):
            mat.roughness = roughness
        if hasattr(mat, "metallic"):
            mat.metallic = metallic
    except Exception:
        pass

    # Assign to target object's data
    if hasattr(obj, "data") and obj.data and hasattr(obj.data, "materials"):
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat

    return {
        "object_name": obj.name,
        "material_name": mat.name,
        "color": list(color_rgba),
        "metallic": metallic,
        "roughness": roughness,
    }
