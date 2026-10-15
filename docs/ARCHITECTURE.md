# BlenderAgent Bridge — Architecture & Technical Design

## 1. Executive Summary

**BlenderAgent Bridge** is an open-source framework enabling autonomous AI agents (such as Antigravity, Claude, ChatGPT, or custom agents) to inspect, automate, and control Blender through structured, deterministic, and verifiable **Model Context Protocol (MCP)** tools.

Unlike conversational chatbots inside Blender or unsafe remote-code-execution bridges (`eval`/`exec`), BlenderAgent Bridge enforces:
1. **Tool-based determinism**: Explicit, strongly typed tools (`get_scene_info`, `create_primitive`, `set_material`, `transform_object`, etc.).
2. **Main-thread execution safety**: Blender's `bpy` C-RNA data structures are not thread-safe. All commands arriving over the network are queued and executed synchronously on Blender's main thread via `bpy.app.timers`.
3. **Strict Local Isolation & Security**: Localhost only (`127.0.0.1`), token-based Bearer authentication, strict workspace directory containment, timeout enforcement, and absolute rejection of arbitrary code execution.
4. **Zero Add-on Dependencies**: The Blender Add-on utilizes solely Python's standard library (`http.server`, `threading`, `queue`, `json`, `pathlib`, `secrets`), guaranteeing zero conflicts across Blender versions (4.2+, 4.5 LTS, 5.2 LTS).
5. **Decoupled Architecture**: The MCP server runs independently from Blender in a modern Python environment with the official MCP SDK.

---

## 2. Component Topology

```
+-------------------------------------------------------------------------+
|                              AI AGENT                                   |
|   (Antigravity / Claude Desktop / Cursor / Autonomous Agent Pipeline)   |
+-------------------------------------------------------------------------+
                                    |
                           MCP Protocol (stdio)
                                    v
+-------------------------------------------------------------------------+
|                         MCP SERVER COMPONENT                            |
|             (Independent Python Process, official MCP SDK)             |
|                                                                         |
|  * Exposes FastMCP / Low-level MCP Tools                                |
|  * Validates tool parameters (Pydantic models, ranges, names, types)    |
|  * Enforces path containment (canonicalized workspace check)            |
|  * Translates MCP tool calls to Local Bridge HTTP requests              |
|  * Formats responses & structured error schemas                         |
+-------------------------------------------------------------------------+
                                    |
                        HTTP / JSON (127.0.0.1:9876)
                      Authorization: Bearer <session-token>
                                    v
+-------------------------------------------------------------------------+
|                        BLENDER ADD-ON / EXTENSION                       |
|                          (Inside Blender 5.2 / 4.5)                     |
|                                                                         |
|  [Background Thread]                                                    |
|    - ThreadingHTTPServer on 127.0.0.1:<port>                            |
|    - Validates Bearer token & JSON payload                              |
|    - Enqueues command to thread-safe execution queue                    |
|    - Awaits completion Event (with timeout)                             |
|                                                                         |
|  [Main Thread Loop - bpy.app.timers]                                    |
|    - Dequeues command tasks                                             |
|    - Executes target bpy handlers safely                                |
|    - Catches exceptions and builds structured response                  |
|    - Sets completion Event and returns output to HTTP handler           |
|                                                                         |
|  [3D Viewport UI Panel]                                                 |
|    - Status indicator (Connected / Disconnected / Error)                |
|    - Start / Stop Bridge operator buttons                               |
|    - Dynamic Port & Auth Token display/generation                       |
|    - Activity counter & compact operational log                         |
+-------------------------------------------------------------------------+
```

---

## 3. Communication Protocol & Handshake

### 3.1 Session Token Lifecycle
1. When the Blender Add-on starts the bridge:
   - A cryptographically secure random token (32 hex characters) is generated via `secrets.token_hex(16)`.
   - The token is stored in memory and optionally persisted to a temporary session file `.blenderagent_session.json` in the user's workspace or runtime directory (restricted permissions).
   - The token is displayed in the Blender 3D Viewport UI panel for manual inspection or copy.
2. The MCP Server is configured with the session token (via environment variable `BLENDERAGENT_TOKEN`, CLI argument `--token`, or auto-discovery from the session file in the active workspace).
3. Every HTTP request sent from the MCP Server to Blender must include:
   ```http
   POST /api/v1/command HTTP/1.1
   Host: 127.0.0.1:9876
   Authorization: Bearer <token>
   Content-Type: application/json
   ```

### 3.2 Request Structure
```json
{
  "command": "create_primitive",
  "params": {
    "type": "cube",
    "name": "AgentCube",
    "location": [2.0, 0.0, 1.0],
    "scale": [1.0, 1.0, 1.0]
  },
  "request_id": "req-1729023456-001"
}
```

### 3.3 Response Structure
All responses adhere to a consistent contract:
```json
{
  "status": "success",
  "data": {
    "name": "AgentCube",
    "type": "MESH",
    "location": [2.0, 0.0, 1.0],
    "dimensions": [2.0, 2.0, 2.0]
  },
  "error": null,
  "message": "Primitive 'AgentCube' created successfully.",
  "request_id": "req-1729023456-001"
}
```

In case of error:
```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "OBJECT_NOT_FOUND",
    "message": "Object 'AgentCube' does not exist in the active scene.",
    "details": {
      "requested_name": "AgentCube",
      "scene_objects": ["Camera", "Light"]
    }
  },
  "message": "Failed to retrieve object info: Object not found.",
  "request_id": "req-1729023456-001"
}
```

---

## 4. Main-Thread Execution Queue (`bpy.app.timers`)

Blender's Python API (`bpy`) requires all modifications to the Blender data model to occur on the main application thread. Calling `bpy.ops` or writing to `bpy.data` from a background socket thread will crash Blender or cause memory corruption.

### Queue Processing Flow
1. **Submission**: When `BridgeRequestHandler.do_POST` receives a valid command, it creates a `CommandTask`:
   - `command_name`: str
   - `params`: dict
   - `done_event`: `threading.Event`
   - `result_container`: dict (`status`, `data`, `error`)
2. **Enqueue**: The task is pushed to `task_queue.put(task)`.
3. **Timer Dispatcher**: A timer registered via `bpy.app.timers.register(process_queue_tick, first_interval=0.01)` wakes up periodically:
   - Drains pending tasks from `task_queue` (up to a batch limit to maintain UI responsiveness at 60 FPS).
   - Dispatches each task to the corresponding handler in `handlers/`.
   - Wraps handler execution in a broad `try/except Exception` block, capturing traceback if necessary.
   - Populates `task.result_container` and sets `task.done_event.set()`.
   - Returns `0.01` (10ms) to reschedule the timer while the bridge is running.
4. **Response Delivery**: The HTTP server thread, which was awaiting `task.done_event.wait(timeout=30.0)`, unblocks, serializes the response JSON, and sends it back to the MCP server.

---

## 5. Security Model & Sandboxing

1. **Localhost Bound**: Socket binds exclusively to `127.0.0.1`. Attempts to bind to external interfaces or `0.0.0.0` are strictly prohibited.
2. **Authentication**: Requests without a valid `Bearer <token>` receive HTTP 401 Unauthorized.
3. **No Arbitrary Execution**: Neither `eval()`, `exec()`, `importlib`, nor shell processes (`subprocess`, `os.system`) are permitted through tool calls. Only predefined whitelisted handlers can be invoked.
4. **Workspace Path Containment**:
   - `render_preview` and `save_project` only accept file paths that resolve strictly inside the designated workspace directory.
   - Path resolution uses `pathlib.Path.resolve()`. Any path escaping the root (e.g. `../../Windows/System32` or absolute drive letters outside the workspace) raises a `SECURITY_VIOLATION` error.
5. **Resource Limits**:
   - Max render dimensions: 4096 x 4096.
   - Max render samples: 512.
   - Command execution timeout: 30 seconds default.
6. **Audit Logging**: Every operation is logged with timestamp, command name, client IP, parameters, execution time, and outcome.
