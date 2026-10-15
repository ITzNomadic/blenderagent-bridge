# BlenderAgent Bridge — Security Architecture & Guidelines

## 1. Threat Model & Design Principles

BlenderAgent Bridge provides AI agents with high-level 3D automation tools. Because AI agents can generate unpredictable outputs or encounter adversarial prompts, the bridge is designed around the principle of **Zero-Trust Tooling**:

1. **No Code Execution**:
   - `eval()`, `exec()`, `__import__`, `os.system`, `subprocess` are completely prohibited.
   - The bridge does not offer a "run_python_script" tool.
   - All actions are strictly whitelisted and mapped to deterministic parameter validation functions.

2. **Network Isolation**:
   - The local bridge listens exclusively on `127.0.0.1` (IPv4 loopback).
   - Remote interfaces (`0.0.0.0`, LAN, WAN) are not supported.
   - The bridge does not make outbound internet connections.

3. **Session Authentication**:
   - A 32-character hexadecimal cryptographically secure bearer token (`secrets.token_hex(16)`) is generated whenever the bridge starts.
   - Any request missing or presenting an incorrect `Authorization: Bearer <token>` header is rejected with HTTP 401 Unauthorized.
   - The token can be refreshed or revoked instantly via the Blender UI panel.

4. **Workspace Directory Containment**:
   - File system write and read operations (`save_project`, `render_preview`) are confined strictly to an authorized `workspace` directory.
   - Canonical path resolution (`pathlib.Path.resolve()`) is enforced on all paths.
   - Relative path navigation (`../`, `..\`) or absolute paths pointing outside the workspace trigger an immediate `SECURITY_VIOLATION` error.

5. **Destructive Action Prevention**:
   - Existing `.blend` files cannot be overwritten unless `overwrite=true` is explicitly provided by the caller.
   - Total scene deletion (`bpy.ops.wm.read_factory_settings` or bulk purge) is disallowed.

6. **Resource Consumption Limits**:
   - Render dimensions are clamped: Width $\in [64, 4096]$, Height $\in [64, 4096]$.
   - Render samples are capped: Samples $\in [1, 512]$.
   - Command timeouts: All requests abort if the Blender main thread does not respond within 30 seconds.

7. **Audit & Traceability**:
   - Every incoming command is recorded in an in-memory ring-buffer audit log and displayed concisely in the Blender 3D Viewport UI.
   - Failed authorization attempts and security violations are logged with timestamps.
