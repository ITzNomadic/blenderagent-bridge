# Technical Audit Report — BlenderAgent Bridge v0.1.0 to v0.1.1 Overhaul

**Audit Date:** 2026-10-15  
**Auditor:** High-Level Software Engineering & QA Team  
**Baseline Version:** v0.1.0  
**Target Version:** v0.1.1  
**Blender Target:** Blender 5.2.2 LTS (Build hash: `d13f752e3b9c`)  

---

## 1. Executive Summary

An exhaustive audit of the `blenderagent-bridge` codebase was performed across packaging, security, HTTP transport, main-thread queue concurrency, numeric data validation, Blender 5.2 compatibility, and automated tests.

While the foundational architecture (decoupled MCP server + local HTTP bridge + main-thread timer queue) is sound and verified against real Blender 5.2, **critical defects (P0) and hardening requirements (P1)** were confirmed that must be resolved prior to v0.1.1 release:

| ID | Category | Severity | Summary |
|---|---|---|---|
| **BUG-01** | Packaging | **P0 (Critical)** | `pip install -e .` fails with `Multiple top-level packages discovered in a flat-layout: ['addon', 'workspace', 'mcp_server']`. Deprecated license table warning. |
| **BUG-02** | Security | **P0 (Critical)** | `workspace_dir` injection vulnerability in HTTP command payload (`server.py` and `handlers/render_save.py`) allows clients to override the server's authorized root and escape workspace containment. |
| **BUG-03** | Security / Auth | **P0 (Critical)** | Session token stored in persistent `bpy.types.Scene.blenderagent_token`, causing tokens to be permanently written into binary `.blend` files. |
| **BUG-04** | Concurrency / Queue | **P0 (Critical)** | `EXECUTION_TIMEOUT` returns error to client while task remains queued in memory; Blender executes expired tasks post-timeout. No cooperative cancellation or task state machine. |
| **BUG-05** | Data Validation | **P1 (High)** | Pydantic models accept non-finite floats (`NaN`, `+inf`, `-inf`), leading to matrix corruption or float exceptions in Blender. |
| **BUG-06** | Testing / Portability | **P1 (High)** | `test_security.py` tests Windows-only paths (`C:/Windows/...`) which fail or resolve inside workspace on Linux. `test_e2e_blender.py` uses hardcoded path without dynamic fallback. |
| **BUG-07** | Network Security | **P1 (High)** | Missing `Host` header validation and `Origin` validation leaves localhost HTTP server exposed to potential browser DNS rebinding or CSRF from malicious local web pages. |
| **BUG-08** | Blender 3D Logic | **P1 (High)** | Object name collisions automatically trigger Blender renaming (e.g. `AgentCube.001`) without explicitly informing agent of the renaming event. |
| **BUG-09** | Concurrency / Queue | **P1 (High)** | Missing queue capacity bounds (`maxsize`); flood of requests can exhaust memory. |

---

## 2. Detailed Technical Findings

### 2.1 BUG-01: Setuptools Flat-Layout Package Discovery (P0)
- **Root Cause:** `pyproject.toml` lacked explicit `[tool.setuptools.packages.find]` directives. Setuptools auto-discovered `addon`, `workspace`, and `mcp_server` as top-level distribution packages.
- **Resolution Plan:**
  - Configure `[tool.setuptools.packages.find]` with `where = ["."]`, `include = ["mcp_server*"]`, and `exclude = ["addon*", "workspace*", "tests*", "scripts*"]`.
  - Fix deprecated `license = { text = "MIT" }` to modern SPDX `license = "MIT"`.
  - Verify wheel build via `python -m build` and clean installation.

### 2.2 BUG-02: Workspace Root Override Vulnerability (P0)
- **Root Cause:** `server.py` line 148: `if "workspace_dir" not in params: params["workspace_dir"] = str(self.workspace_dir)`. If a request payload provided `"workspace_dir": "C:/Windows"`, the server honored the client value.
- **Resolution Plan:**
  - Server must unconditionally enforce its own trusted workspace root: `params["workspace_dir"] = str(self.workspace_dir)` (completely overwriting or discarding any client-provided value).
  - Centralize `validate_workspace_path` to guarantee strict resolution against the immutable server root.
  - Implement comprehensive attack tests with `../../`, mixed slashes, junction points, and shared prefixes.

### 2.3 BUG-03: Session Token Persistence in `.blend` Files (P0)
- **Root Cause:** `bpy.types.Scene.blenderagent_token` stores the session token as a scene property, which Blender serializes into saved `.blend` files.
- **Resolution Plan:**
  - Store token in non-persistent `bpy.types.WindowManager.blenderagent_token` (WindowManager properties are runtime-only and never saved to `.blend` files).
  - Alternatively store in Python server singleton with read-only UI property wrapper.

### 2.4 BUG-04: Queue Concurrency, Timeouts, and Cancellation (P0)
- **Root Cause:** When `task.done_event.wait(timeout)` expires, the task remains in `_task_queue`. When `process_queue_tick` dequeues it later, it still executes in Blender!
- **Resolution Plan:**
  - Introduce formal task lifecycle states: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`.
  - Include `expires_at` timestamp on every task. When `process_queue_tick` drains a task whose `expires_at < now`, it marks it `TIMED_OUT` and discards it without touching Blender data.
  - Add task cancellation endpoint / method `cancel_task(task_id)` and status inspection endpoint `GET /api/v1/tasks/{task_id}`.
  - Bound the queue size (e.g. max 50 pending tasks); return `QUEUE_FULL` (HTTP 429 / 503) if saturated.

### 2.5 BUG-05: Non-Finite Numeric Validation (P1)
- **Root Cause:** Standard Pydantic `float` accepts `NaN` and `Inf` unless constrained.
- **Resolution Plan:**
  - Enforce `math.isfinite(val)` checks across all vector validators (`location`, `rotation`, `scale`, `color`, `dimensions`).
  - Add explicit negative test cases for `NaN`, `+inf`, `-inf`.

---

## 3. Execution Roadmap

1. **Phase 1**: Fix packaging (`pyproject.toml`), verify `pip install -e .`, build wheel, test in isolated venv.
2. **Phase 2**: Harden workspace containment, eliminate `workspace_dir` injection, write attack tests.
3. **Phase 3**: Harden HTTP transport, move token out of `bpy.types.Scene`, add `Origin`/`Host` guards.
4. **Phase 4**: Overhaul queue manager with state machine, `expires_at` checks, cancellation, and concurrency tests.
5. **Phase 5**: Numeric validation hardening (`isfinite`), name collision handling.
6. **Phase 6**: MCP server reliability, distinct error classifications.
7. **Phase 7 & 8**: Blender 5.2 compatibility checks, portable cross-platform test suite, GitHub Actions CI workflow.
8. **Phase 9**: Live E2E demo run with multi-object workflow (cube + cylinder).
9. **Phase 10**: Advance architecture preparation for `get_mesh_info` and `capture_viewport`.
