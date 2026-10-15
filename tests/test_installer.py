"""Automated test suite for BlenderAgent Bridge v0.2.0 Installer, Adapters, and Security."""

from __future__ import annotations

import json
import pathlib
import tempfile
import pytest

from installer.adapters.antigravity import AntigravityAdapter
from installer.adapters.base import AdapterStatus
from installer.adapters.codex import CodexAdapter
from installer.addon_manager import BlenderAddonManager
from installer.detector import (
    BlenderInstallation,
    detect_antigravity,
    detect_codex,
    detect_system_state,
)
from installer.orchestrator import InstallationOrchestrator, InstallOptions
from installer.security_manager import (
    dpapi_protect,
    dpapi_unprotect,
    generate_secure_token,
    load_session_credentials,
    save_session_credentials,
)


def test_token_generation_and_dpapi():
    """Verify cryptographic token entropy and DPAPI roundtrip."""
    tok = generate_secure_token()
    assert isinstance(tok, str)
    assert len(tok) == 32

    # DPAPI roundtrip
    raw_data = tok.encode("utf-8")
    encrypted = dpapi_protect(raw_data)
    assert encrypted is not None
    assert encrypted != raw_data

    decrypted = dpapi_unprotect(encrypted)
    assert decrypted is not None
    assert decrypted.decode("utf-8") == tok


def test_session_credentials_save_and_load(tmp_path):
    """Verify saving and reading session metadata."""
    ws = tmp_path / "workspace"
    session_file, token = save_session_credentials(ws, port=9876)
    assert session_file.exists()

    loaded = load_session_credentials(ws)
    assert loaded is not None
    assert loaded["token"] == token
    assert loaded["port"] == 9876


def test_antigravity_adapter_lifecycle(tmp_path):
    """Verify Antigravity adapter preserves foreign servers, backs up, registers and unregisters."""
    cfg_file = tmp_path / "mcp_config.json"
    initial_content = {
        "mcpServers": {
            "existing-server": {
                "command": "node",
                "args": ["server.js"]
            }
        }
    }
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(initial_content, f)

    adapter = AntigravityAdapter(target_configs=[cfg_file])
    assert adapter.detect() == AdapterStatus.COMPATIBLE

    launcher = tmp_path / "bin" / "blenderagent-mcp.exe"
    ws = tmp_path / "workspace"

    # Install
    res = adapter.install_registration(launcher, ws, port=9876)
    assert res.success
    assert res.status == AdapterStatus.CONFIGURED

    # Verify existing server is preserved and bridge is added
    with open(cfg_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "existing-server" in data["mcpServers"]
    assert "blenderagent-bridge" in data["mcpServers"]
    assert data["mcpServers"]["blenderagent-bridge"]["command"] == str(launcher.resolve())

    # Verify registration check
    assert adapter.verify_registration(launcher)

    # Uninstall
    uninst_res = adapter.uninstall_registration()
    assert uninst_res.success
    with open(cfg_file, "r", encoding="utf-8") as f:
        data_after = json.load(f)
    assert "existing-server" in data_after["mcpServers"]
    assert "blenderagent-bridge" not in data_after["mcpServers"]


def test_codex_adapter_lifecycle(tmp_path):
    """Verify Codex adapter preserves foreign servers, backs up, registers and unregisters."""
    cfg_file = tmp_path / "config.toml"
    initial_toml = (
        'model = "gpt-5"\n\n'
        '[mcp_servers.existing_node]\n'
        'command = "node.exe"\n'
        'args = []\n'
    )
    with open(cfg_file, "w", encoding="utf-8") as f:
        f.write(initial_toml)

    adapter = CodexAdapter(config_path=cfg_file)
    assert adapter.detect() == AdapterStatus.COMPATIBLE

    launcher = tmp_path / "bin" / "blenderagent-mcp.exe"
    ws = tmp_path / "workspace"

    # Install
    res = adapter.install_registration(launcher, ws, port=9876)
    assert res.success
    assert res.status == AdapterStatus.CONFIGURED

    # Verify TOML content
    import tomli
    with open(cfg_file, "rb") as f:
        data = tomli.load(f)
    assert data.get("model") == "gpt-5"
    assert "existing_node" in data["mcp_servers"]
    assert "blenderagent-bridge" in data["mcp_servers"]
    assert data["mcp_servers"]["blenderagent-bridge"]["command"] == str(launcher.resolve())

    # Verify registration check
    assert adapter.verify_registration(launcher)

    # Uninstall
    uninst_res = adapter.uninstall_registration()
    assert uninst_res.success
    with open(cfg_file, "rb") as f:
        data_after = tomli.load(f)
    assert "existing_node" in data_after["mcp_servers"]
    assert "blenderagent-bridge" not in data_after["mcp_servers"]


def test_addon_manager_build_zip(tmp_path):
    """Verify extension zip is built with manifest and required files."""
    mgr = BlenderAddonManager()
    zip_out = tmp_path / "test_addon.zip"
    created_path = mgr.build_extension_zip(zip_out)
    assert created_path.exists()

    import zipfile
    with zipfile.ZipFile(created_path, "r") as zf:
        namelist = zf.namelist()
        assert "blender_manifest.toml" in namelist
        assert "__init__.py" in namelist
        assert "server.py" in namelist


def test_system_detector():
    """Verify system state detection produces valid structured records."""
    state = detect_system_state()
    assert isinstance(state.blender_installations, list)
    assert hasattr(state, "antigravity")
    assert hasattr(state, "codex")
