"""Unit tests for MCP server Pydantic models and input validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mcp_server.models import (
    CreatePrimitiveInput,
    ErrorDetail,
    RenderPreviewInput,
    ResponseEnvelope,
    SaveProjectInput,
    SetCameraInput,
    SetMaterialInput,
    TransformObjectInput,
)


def test_response_envelope_success():
    data = {"scene_name": "TestScene", "objects": []}
    envelope = ResponseEnvelope(
        status="success",
        data=data,
        error=None,
        message="Operation succeeded",
        request_id="req-123",
    )
    dumped = envelope.model_dump()
    assert dumped["status"] == "success"
    assert dumped["data"]["scene_name"] == "TestScene"
    assert dumped["error"] is None


def test_response_envelope_error():
    envelope = ResponseEnvelope(
        status="error",
        data=None,
        error=ErrorDetail(
            code="OBJECT_NOT_FOUND",
            message="Object not found",
            details={"requested_name": "Cube"},
        ),
        message="Failed operation",
    )
    dumped = envelope.model_dump()
    assert dumped["status"] == "error"
    assert dumped["error"]["code"] == "OBJECT_NOT_FOUND"


def test_create_primitive_input_valid():
    inp = CreatePrimitiveInput(
        type="cube",
        name="AgentCube",
        location=[2.0, 0.0, 1.0],
        scale=[1.0, 1.0, 1.0],
    )
    assert inp.type == "cube"
    assert inp.location == [2.0, 0.0, 1.0]


def test_create_primitive_invalid_vector():
    with pytest.raises(ValidationError):
        CreatePrimitiveInput(type="cube", location=[1.0, 2.0])  # Only 2 elements


def test_create_primitive_invalid_type():
    with pytest.raises(ValidationError):
        CreatePrimitiveInput(type="invalid_shape")


def test_transform_object_input_valid():
    inp = TransformObjectInput(
        name="Cube",
        location=[0.0, 0.0, 5.0],
        rotation=[0.0, 45.0, 90.0],
    )
    assert inp.name == "Cube"
    assert inp.rotation == [0.0, 45.0, 90.0]


def test_set_material_input_valid():
    inp = SetMaterialInput(
        name="Cube",
        color=[0.1, 0.4, 0.9],
        metallic=0.8,
        roughness=0.2,
    )
    assert len(inp.color) == 3
    assert inp.metallic == 0.8


def test_set_material_invalid_color_range():
    with pytest.raises(ValidationError):
        SetMaterialInput(name="Cube", color=[1.5, 0.0, 0.0])  # > 1.0


def test_render_preview_boundary_clamping():
    inp = RenderPreviewInput(width=1920, height=1080, samples=64)
    assert inp.width == 1920
    assert inp.height == 1080
    assert inp.samples == 64

    with pytest.raises(ValidationError):
        RenderPreviewInput(width=20)  # Min is 64

    with pytest.raises(ValidationError):
        RenderPreviewInput(samples=1000)  # Max is 512


def test_save_project_input():
    inp = SaveProjectInput(filename="my_scene.blend", overwrite=True)
    assert inp.filename == "my_scene.blend"
    assert inp.overwrite is True
