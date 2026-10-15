"""Scene inspection handlers for BlenderAgent Bridge."""

from __future__ import annotations

from typing import Any, Dict
import bpy


def handle_get_scene_info(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Retrieve detailed scene state, object counts, active collections, and render engine."""
    scene = bpy.context.scene
    
    objects_list = []
    counts = {
        "total_objects": len(bpy.data.objects),
        "mesh_count": 0,
        "camera_count": 0,
        "light_count": 0,
        "other_count": 0,
    }

    for obj in bpy.data.objects:
        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "visible": not obj.hide_viewport,
        }
        objects_list.append(obj_info)

        if obj.type == "MESH":
            counts["mesh_count"] += 1
        elif obj.type == "CAMERA":
            counts["camera_count"] += 1
        elif obj.type == "LIGHT":
            counts["light_count"] += 1
        else:
            counts["other_count"] += 1

    collections = [col.name for col in bpy.data.collections]
    if not collections and hasattr(scene, "collection"):
        collections = [scene.collection.name]

    active_obj_name = None
    if bpy.context.view_layer and bpy.context.view_layer.objects.active:
        active_obj_name = bpy.context.view_layer.objects.active.name

    camera_name = scene.camera.name if scene.camera else None

    return {
        "scene_name": scene.name,
        "frame_current": scene.frame_current,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "unit_system": getattr(scene.unit_settings, "system", "METRIC"),
        "render_engine": scene.render.engine,
        "active_camera": camera_name,
        "active_object": active_obj_name,
        "counts": counts,
        "objects": objects_list,
        "collections": collections,
    }
