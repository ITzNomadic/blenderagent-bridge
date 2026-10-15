"""Official MCP Server for BlenderAgent Bridge.

Exposes structured, verifiable, and secure tools allowing AI agents to control Blender.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any, Dict, List, Literal, Optional
from pydantic import ValidationError

# Compatible with both modern MCP 2.x (MCPServer) and 1.x (FastMCP)
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        raise ImportError("The official MCP SDK is required. Run 'pip install mcp>=1.0.0'.")

from .client import BlenderBridgeClient
from .models import (
    CaptureViewportInput,
    CreatePrimitiveInput,
    ErrorDetail,
    GetMeshInfoInput,
    RenderPreviewInput,
    ResponseEnvelope,
    SaveProjectInput,
    SetCameraInput,
    SetMaterialInput,
    TransformObjectInput,
)

# Global bridge client instance
_client: Optional[BlenderBridgeClient] = None


def get_client() -> BlenderBridgeClient:
    global _client
    if _client is None:
        _client = BlenderBridgeClient()
    return _client


def _validation_error_response(err: ValidationError) -> Dict[str, Any]:
    """Format Pydantic validation errors into a standard ResponseEnvelope dictionary."""
    errors_summary = [
        {"field": " -> ".join(str(loc) for loc in e.get("loc", [])), "message": e.get("msg")}
        for e in err.errors(include_url=False)
    ]
    return ResponseEnvelope(
        status="error",
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message=f"Input parameter validation failed: {err.error_count()} error(s).",
            details={"validation_errors": errors_summary},
        ),
        message="Validation error: check parameter types, ranges, or dimensions.",
    ).model_dump()


def create_mcp_server(
    name: str = "blenderagent-bridge",
    client: Optional[BlenderBridgeClient] = None,
) -> MCPServer:
    """Instantiate and configure the official MCP Server exposing Blender tools."""
    global _client
    if client is not None:
        _client = client

    mcp = MCPServer(
        name=name,
        instructions=(
            "BlenderAgent Bridge provides deterministic, verifiable tools to inspect, "
            "model, transform, shade, illuminate, render, and save 3D scenes in Blender. "
            "Always inspect the scene or objects before and after transformations to verify results."
        ),
    )

    @mcp.tool(
        name="get_scene_info",
        description=(
            "Inspect the active Blender scene state: returns scene name, object counts, "
            "list of objects and their types, active collections, frame range, and active camera."
        ),
    )
    def get_scene_info() -> Dict[str, Any]:
        """Retrieve overall scene state and all contained objects."""
        cl = get_client()
        resp = cl.send_command("get_scene_info", {})
        return resp.model_dump()

    @mcp.tool(
        name="get_object_info",
        description=(
            "Retrieve detailed structural, geometric, and material properties of an object: "
            "3D coordinates, rotation (in degrees and radians), scale, bounding dimensions, "
            "active materials, and modifier stack."
        ),
    )
    def get_object_info(name: str) -> Dict[str, Any]:
        """Retrieve properties for a specific object by name."""
        if not name or not isinstance(name, str) or not name.strip():
            return ResponseEnvelope(
                status="error",
                error=ErrorDetail(code="INVALID_ARGUMENT", message="Parameter 'name' must be a non-empty string."),
                message="Missing required object name.",
            ).model_dump()
        cl = get_client()
        resp = cl.send_command("get_object_info", {"name": name.strip()})
        return resp.model_dump()

    @mcp.tool(
        name="create_primitive",
        description=(
            "Create a standard 3D mesh primitive in the scene. Supported types: "
            "'cube', 'sphere', 'cylinder', 'plane', 'cone', 'torus', 'monkey'. "
            "Returns the actual assigned name, requested name, collision rename status, and spatial properties."
        ),
    )
    def create_primitive(
        type: Literal["cube", "sphere", "cylinder", "plane", "cone", "torus", "monkey"] = "cube",
        name: Optional[str] = None,
        location: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Create a 3D primitive mesh."""
        try:
            validated = CreatePrimitiveInput(
                type=type,
                name=name,
                location=location or [0.0, 0.0, 0.0],
                scale=scale or [1.0, 1.0, 1.0],
            )
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("create_primitive", validated.model_dump())
        return resp.model_dump()

    @mcp.tool(
        name="transform_object",
        description=(
            "Translate, rotate, or scale an existing object in 3D space. "
            "Location in meters [x, y, z], rotation Euler angles in DEGREES [rx, ry, rz], scale factors [sx, sy, sz]."
        ),
    )
    def transform_object(
        name: str,
        location: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        scale: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Apply spatial transformations to a named object."""
        try:
            validated = TransformObjectInput(
                name=name,
                location=location,
                rotation=rotation,
                scale=scale,
            )
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("transform_object", validated.model_dump(exclude_none=True))
        return resp.model_dump()

    @mcp.tool(
        name="set_material",
        description=(
            "Create or configure a node-based Principled BSDF material and assign it to an object. "
            "Takes color as [R, G, B] or [R, G, B, A] floats in range 0.0 to 1.0, "
            "metallic factor [0.0 to 1.0], and roughness [0.0 to 1.0]."
        ),
    )
    def set_material(
        name: str,
        color: List[float],
        metallic: float = 0.0,
        roughness: float = 0.5,
        material_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assign or update a Principled BSDF material."""
        try:
            validated = SetMaterialInput(
                name=name,
                color=color,
                metallic=metallic,
                roughness=roughness,
                material_name=material_name,
            )
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("set_material", validated.model_dump(exclude_none=True))
        return resp.model_dump()

    @mcp.tool(
        name="set_camera",
        description=(
            "Position and orient the observation camera, and ensure scene illumination. "
            "Location in meters [x, y, z], rotation Euler angles in DEGREES [rx, ry, rz]."
        ),
    )
    def set_camera(
        location: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None,
        camera_name: str = "Camera",
        focal_length: float = 50.0,
        make_active: bool = True,
    ) -> Dict[str, Any]:
        """Configure scene camera and basic lighting."""
        try:
            validated = SetCameraInput(
                location=location,
                rotation=rotation,
                camera_name=camera_name,
                focal_length=focal_length,
                make_active=make_active,
            )
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("set_camera", validated.model_dump(exclude_none=True))
        return resp.model_dump()

    @mcp.tool(
        name="render_preview",
        description=(
            "Render a preview frame of the current scene from the active camera. "
            "Saves the image into the authorized workspace directory and returns its verified path and size."
        ),
    )
    def render_preview(
        width: int = 640,
        height: int = 480,
        samples: int = 32,
        output_filename: str = "renders/preview.png",
    ) -> Dict[str, Any]:
        """Render a preview image to workspace."""
        try:
            validated = RenderPreviewInput(
                width=width,
                height=height,
                samples=samples,
                output_filename=output_filename,
            )
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("render_preview", validated.model_dump(exclude_none=True), timeout=60.0)
        return resp.model_dump()

    @mcp.tool(
        name="save_project",
        description=(
            "Save a copy of the current Blender project into the authorized workspace. "
            "Path must be within the workspace and end in '.blend'. Overwrite requires overwrite=True."
        ),
    )
    def save_project(
        filename: str,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Save scene to a .blend file in the workspace."""
        try:
            validated = SaveProjectInput(
                filename=filename,
                overwrite=overwrite,
            )
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("save_project", validated.model_dump())
        return resp.model_dump()

    @mcp.tool(
        name="get_mesh_info",
        description=(
            "Inspect detailed mesh topology metrics: vertex count, edge count, polygon count, "
            "UV layers, vertex groups, assigned materials, and manifold geometric check."
        ),
    )
    def get_mesh_info(name: str) -> Dict[str, Any]:
        """Inspect mesh topology and geometric integrity."""
        try:
            validated = GetMeshInfoInput(name=name)
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("get_mesh_info", validated.model_dump())
        return resp.model_dump()

    @mcp.tool(
        name="capture_viewport",
        description=(
            "Quickly capture the 3D viewport or preview buffer without full raytracing overhead. "
            "Saves PNG to authorized workspace and returns verified file path."
        ),
    )
    def capture_viewport(
        width: int = 640,
        height: int = 480,
        output_filename: str = "renders/viewport.png",
    ) -> Dict[str, Any]:
        """Capture rapid viewport buffer image."""
        try:
            validated = CaptureViewportInput(
                width=width,
                height=height,
                output_filename=output_filename,
            )
        except ValidationError as err:
            return _validation_error_response(err)

        cl = get_client()
        resp = cl.send_command("capture_viewport", validated.model_dump(exclude_none=True), timeout=30.0)
        return resp.model_dump()

    return mcp


def main():
    """CLI entrypoint for running the MCP server."""
    parser = argparse.ArgumentParser(description="BlenderAgent Bridge MCP Server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("BLENDERAGENT_PORT", 9876)))
    parser.add_argument("--token", type=str, default=os.environ.get("BLENDERAGENT_TOKEN", ""))
    parser.add_argument("--workspace", type=str, default=os.environ.get("BLENDERAGENT_WORKSPACE", ""))
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")

    args = parser.parse_args()

    workspace_path = pathlib.Path(args.workspace or (pathlib.Path.cwd() / "workspace")).resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)

    client = BlenderBridgeClient(
        port=args.port,
        token=args.token or None,
        workspace_dir=workspace_path,
    )

    server = create_mcp_server("blenderagent-bridge", client=client)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
