"""Tests for command handler error conditions and argument validation."""

from __future__ import annotations

import pathlib
import pytest

from addon.blenderagent_bridge.handlers import dispatch_command
from addon.blenderagent_bridge.security import (
    BlenderAgentError,
    FileAlreadyExistsError,
    InvalidArgumentError,
    ObjectNotFoundError,
    SecurityViolationError,
)


def test_dispatch_unknown_command():
    with pytest.raises(InvalidArgumentError) as exc_info:
        dispatch_command("non_existent_command", {})
    assert "Unknown command" in str(exc_info.value)
    assert exc_info.value.code == "INVALID_ARGUMENT"


def test_object_handlers_when_blender_not_loaded():
    # Outside blender, object lookup should raise appropriate error
    with pytest.raises(BlenderAgentError):
        dispatch_command("get_object_info", {"name": "NonExistent"})


def test_save_project_missing_filename(temp_workspace):
    with pytest.raises(InvalidArgumentError):
        dispatch_command("save_project", {"workspace_dir": str(temp_workspace)})


def test_save_project_path_traversal(temp_workspace):
    with pytest.raises(SecurityViolationError):
        dispatch_command(
            "save_project",
            {"filename": "../../escape.blend", "workspace_dir": str(temp_workspace)},
        )


def test_create_primitive_validation_errors():
    with pytest.raises(InvalidArgumentError):
        dispatch_command("create_primitive", {"type": 123})

    with pytest.raises(InvalidArgumentError):
        dispatch_command("create_primitive", {"type": "cube", "location": [1.0, 2.0]})

    with pytest.raises(InvalidArgumentError):
        dispatch_command("create_primitive", {"type": "cube", "location": [float("nan"), 0.0, 0.0]})

    with pytest.raises(InvalidArgumentError):
        dispatch_command("create_primitive", {"type": "cube", "scale": [0.0, 1.0, 1.0]})


def test_material_validation_errors():
    with pytest.raises(InvalidArgumentError):
        dispatch_command("set_material", {"name": "Cube", "color": [1.0, 2.0]})  # len != 3 or 4

    with pytest.raises(InvalidArgumentError):
        dispatch_command("set_material", {"name": "Cube", "color": [float("nan"), 0.0, 0.0]})

    with pytest.raises(InvalidArgumentError):
        dispatch_command("set_material", {"name": "Cube", "color": [0.5, 0.5, 0.5], "metallic": 1.5})


def test_camera_validation_errors():
    with pytest.raises(InvalidArgumentError):
        dispatch_command("set_camera", {"location": [float("inf"), 0.0, 0.0]})

    with pytest.raises(InvalidArgumentError):
        dispatch_command("set_camera", {"focal_length": float("nan")})

    with pytest.raises(InvalidArgumentError):
        dispatch_command("set_camera", {"focal_length": 0.0})


def test_get_mesh_info_outside_blender():
    with pytest.raises(BlenderAgentError):
        dispatch_command("get_mesh_info", {"name": "Cube"})


def test_capture_viewport_validation_errors(temp_workspace):
    with pytest.raises(InvalidArgumentError):
        dispatch_command("capture_viewport", {"width": 10})  # Min width is 64

    with pytest.raises(InvalidArgumentError):
        dispatch_command("capture_viewport", {"height": -100})


