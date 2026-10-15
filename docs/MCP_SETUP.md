# BlenderAgent Bridge — MCP Client Configuration Guide

## 1. Antigravity Verification & Configuration

Antigravity natively supports the Model Context Protocol (MCP) using both **stdio** and **Streamable HTTP** transports.

Configuration file location:
- Machine-wide: `~/.gemini/config/mcp_config.json` (on Windows: `C:\Users\<Username>\.gemini\config\mcp_config.json`)
- Or project/workspace level: inside a plugin folder or `.agents/` configuration.

### Recommended Configuration for Antigravity

Add the `blenderagent-bridge` server definition to your `C:\Users\Yhamil\.gemini\config\mcp_config.json`:

```json
{
  "mcpServers": {
    "blenderagent-bridge": {
      "command": "E:\\Decalga\\Proyecto blender\\blenderagent-bridge\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "mcp_server.server",
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

### Verification in Antigravity
1. Open Antigravity.
2. In the chat or options menu, navigate to **Additional Options (...) > MCP Servers**.
3. Verify that `blenderagent-bridge` is listed as active.
4. The following tools will be automatically discovered and available to the agent:
   - `blender_get_scene_info`
   - `blender_get_object_info`
   - `blender_create_primitive`
   - `blender_transform_object`
   - `blender_set_material`
   - `blender_set_camera`
   - `blender_render_preview`
   - `blender_save_project`

---

## 2. Standalone MCP Inspector / Claude Desktop Configuration

For debugging or using Claude Desktop:

### Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "blenderagent-bridge": {
      "command": "E:\\Decalga\\Proyecto blender\\blenderagent-bridge\\.venv\\Scripts\\python.exe",
      "args": [
        "-m",
        "mcp_server.server",
        "--workspace",
        "E:\\Decalga\\Proyecto blender\\blenderagent-bridge\\workspace"
      ]
    }
  }
}
```

### Direct Verification via Python Test Client:
The repository includes an automated test client and integration tests that verify MCP server behavior directly without requiring an external UI.
Run:
```bash
.\.venv\Scripts\pytest tests/ -v
```
