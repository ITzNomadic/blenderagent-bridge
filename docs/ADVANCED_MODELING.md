# BlenderAgent Bridge — Advanced Modeling Architecture & Roadmap

## 1. Executive Summary & Vision

BlenderAgent Bridge provides an enterprise-grade Model Context Protocol (MCP) interface that empowers autonomous AI agents to construct, inspect, refine, shade, and render 3D scenes in Blender.

While initial versions (v0.1.0 – v0.1.1) established core primitives, spatial transformations, Principled BSDF shading, observation cameras, and raytraced rendering, production 3D asset generation requires **procedural geometric operations**: boolean CSG, topological inspection, extrusions, edge bevels, modifier stacks, and instant viewport visual feedback.

This document formalizes the architectural principles, safety boundaries, and design contracts governing advanced procedural modeling in BlenderAgent Bridge.

---

## 2. Core Architectural Philosophy: BMesh vs `bpy.ops`

Blender exposes two primary paradigms for geometry manipulation:

1. **High-Level Operators (`bpy.ops.*`)**:
   - *Advantages*: Replicates user actions; handles collection linking, default UVs, and undo steps automatically.
   - *Disadvantages*: Context-dependent (`poll()` failures when run headless or in non-view contexts), modal execution overhead, potential UI freezing, and fragile active object state.
2. **Low-Level Mesh API (`bmesh`)**:
   - *Advantages*: Fast, deterministic, in-memory geometric modifications. Operates strictly on topological elements (verts, edges, faces). Context-independent; does not fail `poll()` in background worker threads or timers.
   - *Disadvantages*: Requires manual index validation, normal recalculation, and explicit syncing back to `bpy.types.Mesh` (`bm.to_mesh()`).

### The Hybrid Execution Strategy

```
                +---------------------------------------+
                |     AI Agent / MCP Client Request     |
                +---------------------------------------+
                                    |
                                    v
                +---------------------------------------+
                |    Input Validation & Range Clamping   |
                |    (Pydantic Models + Finite Floats)  |
                +---------------------------------------+
                                    |
                                    v
                +---------------------------------------+
                |   Command Queue (Main Thread Timer)   |
                +---------------------------------------+
                                    |
             +----------------------+----------------------+
             |                                             |
             v                                             v
  [High-Level Macro Tools]                      [Micro-Geometry Tools]
  - Scene creation / linking                    - Vertex/Edge/Face extrude
  - Object primitives (`primitive_*_add`)        - Beveling, Inset, Loop-cuts
  - Material assignment                         - Boolean CSG operations
  - Camera & Render outputs                     - Manifoldness & topology audits
  - Engine: `bpy.ops` / `bpy.data`               - Engine: `bmesh`
             |                                             |
             +----------------------+----------------------+
                                    |
                                    v
                +---------------------------------------+
                | Synchronous Geometry Sync (`to_mesh`) |
                | Recalculate Normals & Update Bounds   |
                +---------------------------------------+
                                    |
                                    v
                +---------------------------------------+
                | Structured Response Envelope + Audits  |
                +---------------------------------------+
```

---

## 3. Implemented v0.1.1 Advanced Tools

### 3.1 `get_mesh_info(name: str)`
Retrieves full topological metrics and manifold integrity for any named mesh object.

- **Contracts**:
  - `name`: Target object name. Must be of type `MESH`.
- **Returned Metrics**:
  - `vertex_count`: Total vertices.
  - `edge_count`: Total edges.
  - `polygon_count`: Total faces/polygons.
  - `has_uvs` & `uv_layers`: UV map status and layer names.
  - `vertex_groups`: Configured weight groups.
  - `materials`: Material names linked to mesh data slots.
  - `is_manifold`: Boolean indicating zero boundary holes or non-manifold edge junctions.

### 3.2 `capture_viewport(output_filename, width, height)`
Provides sub-second visual feedback for agent loops without the heavy overhead of Cycles/EEVEE raytracing.

- In interactive GUI mode, captures the OpenGL 3D viewport buffer (`bpy.ops.render.opengl`).
- In headless background mode, automatically falls back to a 4-sample Workbench/still render, guaranteeing consistent output delivery.

---

## 4. Planned Procedural Modeling Tool Contracts (v0.2.0+)

### 4.1 Boolean Operations: `boolean_operation`

Executes constructive solid geometry (CSG) between two objects.

```python
class BooleanOperationInput(BaseModel):
    target: str = Field(..., description="Target object receiving modification")
    cutter: str = Field(..., description="Tool object to intersect, union, or subtract")
    operation: Literal["DIFFERENCE", "UNION", "INTERSECT"] = "DIFFERENCE"
    solver: Literal["EXACT", "FAST"] = "EXACT"
    apply_immediately: bool = True
    delete_cutter: bool = False
```

### 4.2 Face Extrusion: `extrude_faces`

Procedurally extrudes specified faces along face normals or a directional vector.

```python
class ExtrudeFacesInput(BaseModel):
    name: str = Field(..., description="Target mesh name")
    face_indices: Optional[List[int]] = Field(None, description="Specific faces, or None for all selected")
    distance: float = Field(..., ge=-100.0, le=100.0, description="Extrusion distance in meters")
    recalculate_normals: bool = True
```

### 4.3 Edge Beveling: `bevel_edges`

Creates mechanical or organic chamfers/fillets along sharp edges.

```python
class BevelEdgesInput(BaseModel):
    name: str = Field(..., description="Target mesh name")
    offset: float = Field(..., ge=0.001, le=10.0, description="Bevel width offset")
    segments: int = Field(default=2, ge=1, le=16, description="Rounding segment count")
    affect: Literal["EDGES", "VERTICES"] = "EDGES"
```

### 4.4 Modifier Stack Automation: `manage_modifier`

Allows adding, configuring, and applying modifiers without modal UI interactions.

```python
class AddModifierInput(BaseModel):
    object_name: str
    modifier_type: Literal["SUBSURF", "SOLIDIFY", "MIRROR", "BEVEL", "ARRAY", "DECIMATE"]
    modifier_name: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    apply: bool = False
```

---

## 5. Geometric Guardrails & Safety Defenses

To prevent autonomous agents from triggering out-of-memory errors or locking up the host workstation, the bridge enforces:

1. **Polygon Budget Clamping**:
   - Maximum vertex limit per mesh operation: `1,000,000` vertices.
   - Subsurf level restricted to `le=3` in viewport and `le=4` in render.
2. **Dimension & Scale Bounding**:
   - Coordinates constrained to finite values: `math.isfinite(coord)`.
   - Scale clamped to non-zero: `abs(s) >= 1e-6` to avoid non-invertible singular transformation matrices.
3. **Cooperative Cancellation**:
   - Long topological operations check `task.cancel_event.is_set()` between iterations and abort before committing changes if cancelled.
4. **Authoritative File Containment**:
   - All assets (textures, caches, preview renders, exported `.blend` or `.obj` files) remain strictly within the validated workspace directory.
