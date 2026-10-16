# BlenderAgent Bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![Blender: 4.2+ / 4.5 LTS / 5.2 LTS](https://img.shields.io/badge/Blender-4.2%2B%20%7C%204.5%20LTS%20%7C%205.2%20LTS-orange.svg)](https://www.blender.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Official%20SDK-purple.svg)](https://modelcontextprotocol.io/)
[![Release: Beta / Experimental](https://img.shields.io/badge/Release-v0.2.2--beta%20(Experimental)-yellow.svg)](https://github.com/ITzNomadic/blenderagent-bridge/releases)

**BlenderAgent Bridge** (`v0.2.2-beta`) is an open-source framework enabling autonomous AI agents (such as Google Antigravity, OpenAI Codex, Claude Desktop, Cursor, or autonomous agent loops) to inspect, model, shade, illuminate, render, and control Blender through structured, deterministic, and verifiable **Model Context Protocol (MCP)** tools.

> **Note:** This release is tagged as **Beta / Experimental**. It provides comprehensive automation and stability fixes, but ongoing refinements and community feedback are actively welcomed.

---

### Highlights in v0.2.2-beta:
- **Automatic System Language Detection (i18n)**: Automatically detects whether your operating system is in English or Spanish and displays the interface in that language, with an instant header toggle button (`🌐 Language / Idioma`).
- **Fully Automated Token Synchronization**: Zero manual token configuration. Tokens are cryptographically generated, written to user-private files with ACLs, and automatically synchronized between Blender and the MCP server.
- **Cleaned-up UI**: The 3D Viewport sidebar panel is streamlined and clutter-free (tokens and credentials remain safely managed internally).
- **One-Click Windows Installer (`BlenderAgentBridge-Setup.exe`)**: Standalone graphical installer that discovers Blender, registers Google Antigravity and OpenAI Codex, and provisions the MCP binary without needing global Python.
- **Standalone MCP Launcher (`blenderagent-mcp.exe`)**: Embedded self-contained runtime.
- **Hardened Security & Concurrency**: 86 automated test cases covering DNS rebinding, CSRF defenses, Windows ADS path traversal, in-flight idempotency deduplication, and atomic NTFS file operations.

---

## Architecture Topology

```
+-------------------------------------------------------------------------+
|                              AI AGENT                                   |
|   (Antigravity / OpenAI Codex / Claude Desktop / Cursor / Script)       |
+-------------------------------------------------------------------------+
                                    |
                           MCP Protocol (stdio)
                                    v
+-------------------------------------------------------------------------+
|                         MCP SERVER COMPONENT                            |
|             (Standalone executable or Python process, MCP SDK)         |
|                                                                         |
|  * Exposes official MCP tools (FastMCP / MCPServer)                     |
|  * Validates parameters using Pydantic schemas (finite float guards)    |
|  * Dispatches HTTP commands with Bearer authentication                  |
+-------------------------------------------------------------------------+
                                    |
                        HTTP / JSON (127.0.0.1:9876)
                      Authorization: Bearer <session-token>
                                    v
+-------------------------------------------------------------------------+
|                        BLENDER ADD-ON / EXTENSION                       |
|                   (Blender 4.2+ / 4.5 LTS / 5.2 LTS)                    |
|                                                                         |
|  [Background Thread]                                                    |
|    - ThreadingHTTPServer on 127.0.0.1:<port>                            |
|    - Validates Bearer token, Host, Origin & Content-Type                |
|    - Enqueues command tasks with deadlines                              |
|                                                                         |
|  [Main Thread Loop - bpy.app.timers]                                    |
|    - Dequeues command tasks (10ms tick rate)                            |
|    - Skips expired or cancelled tasks                                   |
|    - Dispatches safe bpy handlers synchronously                         |
|    - Returns structured result envelope                                 |
|                                                                         |
|  [3D Viewport UI Panel]                                                 |
|    - Status indicator (ACTIVE / STOPPED)                                |
|    - Start / Stop Bridge operators                                      |
|    - Bilingual support (English / Spanish)                              |
|    - Command counter & compact operational audit log                    |
+-------------------------------------------------------------------------+
```

---

## Available MCP Tools

BlenderAgent Bridge exposes 10 standardized, typed tools:

| Tool | Parameters | Description |
|---|---|---|
| `get_scene_info` | None | Returns active scene name, object counts, list of objects and types, collections, active camera. |
| `get_object_info` | `name` (str) | Returns coordinates `[x,y,z]`, rotation (deg/rad), scale, bounding dimensions, materials, and modifiers. |
| `get_mesh_info` | `name` (str) | Returns detailed mesh topology: vertex count, edge count, polygon count, UV layers, vertex groups, and manifoldness. |
| `create_primitive` | `type`, `name`, `location`, `scale` | Creates a 3D mesh (`cube`, `sphere`, `cylinder`, `plane`, `cone`, `torus`, `monkey`). Detects collisions and returns actual name and rename flag. |
| `transform_object` | `name`, `location`, `rotation`, `scale` | Applies translation in meters, Euler rotation in degrees, and scale factors with strict non-finite guards. |
| `set_material` | `name`, `color`, `metallic`, `roughness`, `material_name` | Creates or updates a node-based Principled BSDF material and binds it to the object. |
| `set_camera` | `location`, `rotation`, `camera_name`, `focal_length`, `make_active` | Positions and rotates the scene camera, sets lens focal length, and ensures scene illumination. |
| `render_preview` | `width`, `height`, `samples`, `output_filename` | Renders a preview frame and saves it to authorized workspace. Returns validated disk path and size. |
| `capture_viewport` | `width`, `height`, `output_filename` | Rapidly captures 3D viewport/workbench buffer without full raytracing overhead. |
| `save_project` | `filename`, `overwrite` | Saves a copy of the `.blend` scene to the workspace. Explicit overwrite confirmation required. |

---

## Quickstart (Windows)

### Option 1: One-Click Installer (Recommended)
1. Download `BlenderAgentBridge-Setup.exe` from the latest [Release](https://github.com/ITzNomadic/blenderagent-bridge/releases).
2. Run `BlenderAgentBridge-Setup.exe`.
3. The wizard detects your Blender version, Google Antigravity, and OpenAI Codex configurations automatically.
4. Click **Install & Connect**. Open Blender, and you're ready!

### Option 2: Manual / Developer Setup
```bash
git clone https://github.com/ITzNomadic/blenderagent-bridge.git
cd blenderagent-bridge

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies and bridge in editable mode
pip install -e .
```

---

## AI Agent Integration

### Google Antigravity Integration
In `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "blenderagent-bridge": {
      "command": "blenderagent-mcp",
      "args": [
        "--workspace",
        "%LOCALAPPDATA%\\BlenderAgentBridge\\workspace"
      ],
      "env": {
        "BLENDERAGENT_PORT": "9876",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

### OpenAI Codex Integration
In `~/.codex/config.toml`:
```toml
[mcp_servers.blenderagent-bridge]
command = "blenderagent-mcp"
args = ["--workspace", "%LOCALAPPDATA%\\BlenderAgentBridge\\workspace"]

[mcp_servers.blenderagent-bridge.env]
BLENDERAGENT_PORT = "9876"
PYTHONUNBUFFERED = "1"
```

---

## Running Automated Tests

The test suite runs with `pytest` and verifies all security models, adapters, and handlers:

```bash
pytest -v
# 86 passed in ~28s
```

---

## License

This project is licensed under the [MIT License](LICENSE).
