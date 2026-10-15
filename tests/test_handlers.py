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
