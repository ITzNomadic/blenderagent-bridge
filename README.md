# BlenderAgent Bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![Blender: 4.2+ / 4.5 LTS / 5.2 LTS](https://img.shields.io/badge/Blender-4.2%2B%20%7C%204.5%20LTS%20%7C%205.2%20LTS-orange.svg)](https://www.blender.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Official%20SDK-purple.svg)](https://modelcontextprotocol.io/)

**BlenderAgent Bridge** (`v0.2.0`) is an open-source framework enabling autonomous AI agents (such as Google Antigravity, OpenAI Codex, Claude Desktop, Cursor, or autonomous pipelines) to inspect, model, shade, illuminate, render, and control Blender through structured, deterministic, and verifiable **Model Context Protocol (MCP)** tools.

### New in v0.2.0:
- **One-Click Windows Installer (`BlenderAgentBridge-Setup.exe`)**: Zero-command, standalone installer with modern wizard GUI.
- **Standalone MCP Launcher (`blenderagent-mcp.exe`)**: Built-in runtime requiring NO global Python installation.
- **Automatic Multi-Client Integration**: Automatic discovery and registration for Google Antigravity and OpenAI Codex with backup preservation.
- **DPAPI Credential Security**: Ephemeral Bearer tokens encrypted using Windows DPAPI and private filesystem ACLs.
- **Safe Non-Admin Workspace**: Authoritative user workspace at `%LOCALAPPDATA%\BlenderAgentBridge\workspace`.

Unlike conversational chatbots or insecure remote execution bridges (`eval`/`exec`), BlenderAgent Bridge enforces:
- **Thread Safety**: All Blender scene mutations execute strictly on Blender's main thread via `bpy.app.timers`.
- **Zero In-Blender Dependencies**: The Blender Add-on utilizes solely Python's standard library (`http.server`, `threading`, `queue`, `json`, `pathlib`, `secrets`).
- **Sandboxed File Operations**: All file reading and writing (`render_preview`, `capture_viewport`, `save_project`) is confined strictly to an authoritative workspace directory with rigorous path traversal defenses (guarding against `..`, Windows ADS `:`, reserved devices like `CON`/`NUL`, and shared prefixes).
- **Hardened Local HTTP Security**: Binds exclusively to `127.0.0.1`, validates `Host` headers against DNS rebinding, checks `Origin` against CSRF, and enforces constant-time Bearer token verification.
- **Task State Machine & Expiration Protection**: Full lifecycle tracking (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCEL_REQUESTED`, `CANCELLED`, `TIMED_OUT`, `INTERRUPTED`), timeout defenses that abort expired queued tasks before execution, cooperative cancellation, and idempotency caching.

---

## Architecture Topology

```
+-------------------------------------------------------------------------+
|                              AI AGENT                                   |
|   (Antigravity / Claude Desktop / Cursor / Custom Agent Script)        |
+-------------------------------------------------------------------------+
                                    |
                           MCP Protocol (stdio)
                                    v
+-------------------------------------------------------------------------+
|                         MCP SERVER COMPONENT                            |
|             (Independent Python Process, official MCP SDK)             |
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
|    - Dynamic Port & Transient WindowManager Auth Token                  |
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

## Installation & Quickstart

### Prerequisites
- Blender 4.2+, 4.5 LTS, or 5.2 LTS.
- Python 3.10+ (for the MCP server host environment).

### 1. Set Up MCP Server Environment
```bash
git clone https://github.com/ITzNomadic/blenderagent-bridge.git
cd blenderagent-bridge

# Create and activate virtual environment
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install package and entrypoint
pip install -e .
```

After installation, the CLI command `blenderagent-mcp` is directly available:
```bash
blenderagent-mcp --help
```

### 2. Install the Blender Add-on
1. Open Blender 5.2 or 4.5 LTS.
2. Go to **Edit > Preferences > Add-ons**.
3. Click the dropdown menu at the top right and select **Install from Disk...**.
4. Select the `addon/blenderagent_bridge` directory (or zip archive).
5. Enable **BlenderAgent Bridge**.
6. In the 3D Viewport, press `N` to open the sidebar and navigate to the **BlenderAgent** tab.
7. Click **Start Bridge**. The status banner will change to `Status: ACTIVE` with the port and token displayed.

---

## AI Agent Integration

### Antigravity Integration
Add the server entry to `~/.gemini/config/mcp_config.json`:
```json
{
  "mcpServers": {
    "blenderagent-bridge": {
      "command": "blenderagent-mcp",
      "args": [
        "--workspace",
        "E:\\Decalga\\Proyecto blender\\blenderagent-bridge\\workspace"
      ],
      "env": {
        "BLENDERAGENT_PORT": "9876",
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

### Claude Desktop Integration
Add the server entry to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "blenderagent-bridge": {
      "command": "blenderagent-mcp",
      "args": [
        "--workspace",
        "E:\\Decalga\\Proyecto blender\\blenderagent-bridge\\workspace"
      ]
    }
  }
}
```

---

## Security Model

- **Localhost Only**: The HTTP server strictly binds to `127.0.0.1`. Requests originating from any remote IP are blocked with HTTP 403.
- **Session Authentication**: A cryptographic 32-character hexadecimal token is generated on startup. Every command requires an `Authorization: Bearer <token>` header verified via `secrets.compare_digest`.
- **Transient Memory Storage**: The session token is stored in transient `bpy.types.WindowManager` runtime properties, ensuring tokens are **never** serialized into `.blend` project files.
- **Strict Path Containment**: File write operations are resolved against the authoritative workspace directory. Path traversal sequences (`../`, `..\`), Windows alternate data streams (`:`), reserved device names (`CON`, `PRN`, `AUX`, `NUL`), and shared prefixes are rejected with `SECURITY_VIOLATION`.
- **No Remote Code Execution**: `eval()`, `exec()`, arbitrary python scripts, and shell commands are completely disabled.
- **Resource Limits**: Clamped image resolutions (up to 4096px), sampling limits (up to 512 samples), and execution timeouts with automatic deadline enforcement.

---

## Running Automated Tests

The test suite includes 56 tests covering security attacks, Pydantic model validation, concurrency state machine, HTTP protocol defenses, and live end-to-end multi-object tests against real Blender 5.2:

```bash
# Run complete test suite (56 passed)
pytest -v
```

---

## License

This project is licensed under the [MIT License](LICENSE).
