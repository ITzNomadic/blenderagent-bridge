# BlenderAgent Bridge — Data Contracts & Error Schemas

This document defines the formal data contracts, API schemas, and structured error responses used across BlenderAgent Bridge (Blender Add-on, Local Bridge HTTP transport, and MCP Server).

---

## 1. Universal Response Envelope

All API endpoints and MCP tools return a predictable, standardized envelope:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["status", "message"],
  "properties": {
    "status": {
      "type": "string",
      "enum": ["success", "error"]
    },
    "data": {
      "type": ["object", "null"]
    },
    "error": {
      "type": ["object", "null"],
      "properties": {
        "code": { "type": "string" },
        "message": { "type": "string" },
        "details": { "type": "object" }
      },
      "required": ["code", "message"]
    },
    "message": { "type": "string" },
    "request_id": { "type": "string" }
  }
}
```

---

## 2. Standard Error Codes

| Code | HTTP Status | Description |
|---|---|---|
| `UNAUTHORIZED` | 401 | Missing or invalid Bearer session token. |
| `SECURITY_VIOLATION` | 403 | Path traversal attempt, unauthorized directory write/read, or prohibited operation. |
| `INVALID_ARGUMENT` | 400 | Parameter failed type, range, or value constraints. |
| `OBJECT_NOT_FOUND` | 404 | Target Blender object does not exist in the active scene. |
| `ALREADY_EXISTS` | 409 | Attempting to save to an existing file without explicit overwrite confirmation. |
| `BRIDGE_UNAVAILABLE` | 503 | MCP Server cannot reach Blender on 127.0.0.1 (Add-on not started). |
| `EXECUTION_TIMEOUT` | 504 | Main thread task did not complete within the allotted timeout window. |
| `INTERNAL_ERROR` | 500 | Unhandled internal exception occurred during `bpy` execution. |

---

## 3. Tool Specifications

### 3.1 `get_scene_info`
- **Description**: Returns name of active scene, object counts, list of objects and their types, active collections, and render settings.
- **Parameters**: None.
- **Success Data**:
  ```json
  {
    "scene_name": "Scene",
    "frame_current": 1,
    "unit_system": "METRIC",
    "active_object": "Cube",
    "counts": {
      "total_objects": 3,
      "mesh_count": 1,
      "camera_count": 1,
      "light_count": 1
    },
    "objects": [
      { "name": "Camera", "type": "CAMERA", "visible": true },
      { "name": "Cube", "type": "MESH", "visible": true },
      { "name": "Light", "type": "LIGHT", "visible": true }
    ],
    "collections": ["Scene Collection"]
  }
  ```

### 3.2 `get_object_info`
- **Description**: Inspects a specific object's location, rotation, scale, dimensions, assigned materials, and modifiers.
- **Parameters**:
  - `name` (string, required): Name of the object in Blender.
- **Success Data**:
  ```json
  {
    "name": "AgentCube",
    "type": "MESH",
    "location": [2.0, 0.0, 1.0],
    "rotation_euler_deg": [0.0, 0.0, 0.0],
    "scale": [1.0, 1.0, 1.0],
    "dimensions": [2.0, 2.0, 2.0],
    "materials": ["MetallicBlue"],
    "modifiers": [],
    "visible": true
  }
  ```

### 3.3 `create_primitive`
- **Description**: Creates a supported mesh primitive and returns its actual identifier.
- **Parameters**:
  - `type` (string, required): `cube`, `sphere`, `cylinder`, `plane`, `cone`, `torus`, or `monkey`.
  - `name` (string, optional): Desired name.
  - `location` (list[float], optional): `[x, y, z]` coordinates (default `[0, 0, 0]`).
  - `scale` (list[float], optional): `[sx, sy, sz]` factors (default `[1, 1, 1]`).
- **Success Data**:
  ```json
  {
    "name": "AgentCube",
    "type": "MESH",
    "location": [2.0, 0.0, 1.0],
    "scale": [1.0, 1.0, 1.0],
    "dimensions": [2.0, 2.0, 2.0]
  }
  ```

### 3.4 `transform_object`
- **Description**: Applies translation, rotation (in degrees), and scale to an object.
- **Parameters**:
  - `name` (string, required): Object identifier.
  - `location` (list[float], optional): New `[x, y, z]`.
  - `rotation` (list[float], optional): Euler angles `[rx, ry, rz]` in degrees.
  - `scale` (list[float], optional): New `[sx, sy, sz]`.
- **Success Data**:
  ```json
  {
    "name": "AgentCube",
    "location": [2.0, 0.0, 1.0],
    "rotation_euler_deg": [0.0, 0.0, 45.0],
    "scale": [1.5, 1.5, 1.5],
    "dimensions": [3.0, 3.0, 3.0]
  }
  ```

### 3.5 `set_material`
- **Description**: Creates or updates a node-based Principled BSDF material and assigns it to the target mesh.
- **Parameters**:
  - `name` (string, required): Name of target object.
  - `color` (list[float], required): RGB or RGBA normalized floats `[0.0 - 1.0]`.
  - `metallic` (float, required): Value between `0.0` (dielectric) and `1.0` (metal).
  - `roughness` (float, required): Surface roughness between `0.0` (mirror) and `1.0` (diffuse).
  - `material_name` (string, optional): Custom name for the material.
- **Success Data**:
  ```json
  {
    "object_name": "AgentCube",
    "material_name": "AgentCube_Material",
    "color": [0.1, 0.4, 0.9, 1.0],
    "metallic": 0.9,
    "roughness": 0.2
  }
  ```

### 3.6 `set_camera`
- **Description**: Creates or configures the scene camera and basic lighting for scene observation.
- **Parameters**:
  - `location` (list[float], optional): `[x, y, z]` camera position.
  - `rotation` (list[float], optional): `[rx, ry, rz]` Euler angles in degrees.
  - `camera_name` (string, optional): Name of camera (default "Camera").
  - `make_active` (bool, optional): Set as active scene camera (default true).
  - `focal_length` (float, optional): Lens focal length in mm (default 50.0).
- **Success Data**:
  ```json
  {
    "camera_name": "Camera",
    "location": [5.0, -5.0, 4.0],
    "rotation_euler_deg": [60.0, 0.0, 45.0],
    "is_active_scene_camera": true,
    "focal_length": 50.0
  }
  ```

### 3.7 `render_preview`
- **Description**: Renders an image using the active camera and saves it into the authorized workspace directory.
- **Parameters**:
  - `width` (int, optional): Width in pixels (64 - 4096, default 640).
  - `height` (int, optional): Height in pixels (64 - 4096, default 480).
  - `samples` (int, optional): Render samples (1 - 512, default 32).
  - `output_filename` (string, optional): Relative filename within workspace (default `preview.png`).
- **Success Data**:
  ```json
  {
    "file_path": "E:/Decalga/Proyecto blender/blenderagent-bridge/workspace/renders/preview.png",
    "relative_path": "workspace/renders/preview.png",
    "width": 640,
    "height": 480,
    "samples": 32,
    "file_size_bytes": 142850
  }
  ```

### 3.8 `save_project`
- **Description**: Saves a copy of the current Blender project to an authorized relative path in the workspace.
- **Parameters**:
  - `filename` (string, required): Target `.blend` filename within workspace.
  - `overwrite` (bool, optional): Must be explicitly `true` if file already exists (default false).
- **Success Data**:
  ```json
  {
    "file_path": "E:/Decalga/Proyecto blender/blenderagent-bridge/workspace/blenderagent_demo.blend",
    "relative_path": "workspace/blenderagent_demo.blend",
    "file_size_bytes": 984520
  }
  ```
