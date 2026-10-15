"""Pytest configuration and shared fixtures for BlenderAgent Bridge tests."""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
import pytest


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory for testing."""
    tmp = tempfile.mkdtemp(prefix="blenderagent_test_ws_")
    tmp_path = pathlib.Path(tmp).resolve()
    renders_dir = tmp_path / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    yield tmp_path
    shutil.rmtree(tmp, ignore_errors=True)
