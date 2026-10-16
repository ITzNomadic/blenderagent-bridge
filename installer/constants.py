"""Constants and path configuration for BlenderAgent Bridge v0.2.0."""

from __future__ import annotations

import os
import pathlib
import sys

APP_NAME = "BlenderAgent Bridge"
APP_ID = "blenderagent-bridge"
ADDON_ID = "blenderagent_bridge"
VERSION = "0.2.0"
DEFAULT_PORT = 9876

# Windows per-user directories (no admin elevation required)
LOCALAPPDATA = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData" / "Local"))
APPDATA_ROAMING = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home() / "AppData" / "Roaming"))
USERPROFILE = pathlib.Path(os.environ.get("USERPROFILE", pathlib.Path.home()))

DEFAULT_DATA_DIR = LOCALAPPDATA / "BlenderAgentBridge"
DEFAULT_WORKSPACE_DIR = DEFAULT_DATA_DIR / "workspace"
DEFAULT_RENDERS_DIR = DEFAULT_WORKSPACE_DIR / "renders"
DEFAULT_SCENES_DIR = DEFAULT_WORKSPACE_DIR / "scenes"

DEFAULT_INSTALL_DIR = LOCALAPPDATA / "Programs" / "BlenderAgentBridge"
DEFAULT_BIN_DIR = DEFAULT_INSTALL_DIR / "bin"
MCP_LAUNCHER_EXE_NAME = "blenderagent-mcp.exe"
MCP_LAUNCHER_PATH = DEFAULT_BIN_DIR / MCP_LAUNCHER_EXE_NAME

INSTALL_MANIFEST_PATH = DEFAULT_DATA_DIR / "install_manifest.json"
SESSION_FILE_PATH = DEFAULT_WORKSPACE_DIR / ".blenderagent_session.json"
LIVE_SESSION_FILE_PATH = DEFAULT_DATA_DIR / "live_session.json"

MIN_BLENDER_VERSION = (4, 2, 0)
TARGET_BLENDER_VERSION = (5, 2, 0)

# Known AI Agent Configuration Locations
ANTIGRAVITIY_GLOBAL_CONFIG = USERPROFILE / ".gemini" / "config" / "mcp_config.json"
ANTIGRAVITIY_IDE_CONFIG = USERPROFILE / ".gemini" / "antigravity-ide" / "mcp_config.json"
CODEX_GLOBAL_CONFIG = USERPROFILE / ".codex" / "config.toml"
