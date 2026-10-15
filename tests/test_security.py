"""Unit tests for security containment, path traversal defense, and session management."""

from __future__ import annotations

import pathlib
import pytest

from addon.blenderagent_bridge.security import (
    AuditLogger,
    FileAlreadyExistsError,
    InvalidArgumentError,
    SecurityViolationError,
    generate_session_token,
    validate_workspace_path,
)


def test_token_generation():
    token1 = generate_session_token()
    token2 = generate_session_token()
    assert len(token1) == 32
    assert len(token2) == 32
    assert token1 != token2


def test_validate_workspace_path_valid(temp_workspace):
    safe_path = validate_workspace_path(temp_workspace, "renders/output.png")
    assert safe_path.is_relative_to(temp_workspace)
    assert safe_path.name == "output.png"


def test_validate_workspace_path_traversal_attack(temp_workspace):
    # Attempting to escape via ../
    with pytest.raises(SecurityViolationError):
        validate_workspace_path(temp_workspace, "../../sensitive.txt")


def test_validate_workspace_path_absolute_escape(temp_workspace):
    # Attempting an absolute path outside workspace
    outside_path = pathlib.Path("C:/Windows/System32/cmd.exe")
    with pytest.raises(SecurityViolationError):
        validate_workspace_path(temp_workspace, outside_path)


def test_validate_workspace_path_null_byte(temp_workspace):
    with pytest.raises(InvalidArgumentError):
        validate_workspace_path(temp_workspace, "test\x00.blend")


def test_validate_workspace_path_empty(temp_workspace):
    with pytest.raises(InvalidArgumentError):
        validate_workspace_path(temp_workspace, "   ")


def test_audit_logger():
    logger = AuditLogger(maxlen=3)
    logger.log("test_cmd1", "SUCCESS", "Summary 1")
    logger.log("test_cmd2", "ERROR", "Summary 2")
    logger.log("test_cmd3", "SUCCESS", "Summary 3")
    logger.log("test_cmd4", "SUCCESS", "Summary 4")  # Should push out cmd1

    assert logger.total_count == 4
    recent = logger.get_recent(5)
    assert len(recent) == 3
    assert recent[0]["command"] == "test_cmd4"
    assert recent[-1]["command"] == "test_cmd2"

    logger.clear()
    assert logger.total_count == 0
    assert len(logger.get_recent()) == 0
