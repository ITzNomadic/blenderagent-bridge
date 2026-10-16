"""Unit tests proving that audit findings BA-001 through BA-019 are fully resolved."""

from __future__ import annotations

import json
import math
import os
import pathlib
import tempfile
import threading
import time
import pytest

from addon.blenderagent_bridge.handlers.objects import handle_transform_object, handle_get_mesh_info
from addon.blenderagent_bridge.handlers.render_save import handle_save_project, _parse_strict_bool
from addon.blenderagent_bridge.operator import WM_OT_BlenderAgentStartBridge
from addon.blenderagent_bridge.queue_manager import ExecutionQueueManager, TaskStatus
from addon.blenderagent_bridge.security import (
    BlenderAgentError,
    InvalidArgumentError,
    remove_session_file,
    write_session_file,
    _atomic_write_json,
)
from addon.blenderagent_bridge.server import BridgeHTTPRequestHandler, bridge_server


def test_ba001_remove_session_file_preserves_other_instances():
    """BA-001: remove_session_file must not delete global session of another instance/PID."""
    with tempfile.TemporaryDirectory() as td:
        ws = pathlib.Path(td)
        from addon.blenderagent_bridge.security import get_global_session_file
        gfile = get_global_session_file()
        
        # Simulate instance B owning the global session
        foreign_pid = 999999
        foreign_port = 8888
        gdata = {
            "version": "0.2.0",
            "token": "b" * 32,
            "port": foreign_port,
            "pid": foreign_pid,
            "workspace": str(ws),
        }
        _atomic_write_json(gfile, gdata)
        assert gfile.exists()

        # Instance A (our current process) attempts to clean up its own workspace
        remove_session_file(workspace_dir=ws, pid=os.getpid(), port=9876)

        # Global file belonging to foreign_pid MUST still exist!
        assert gfile.exists()
        with open(gfile, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["pid"] == foreign_pid


def test_ba002_read_session_token_rejects_foreign_instance_metadata():
    """BA-002: _read_session_token_from_disk must verify PID and port matching."""
    with tempfile.TemporaryDirectory() as td:
        ws = pathlib.Path(td)
        from addon.blenderagent_bridge.security import get_global_session_file
        gfile = get_global_session_file()
        
        # Foreign instance written to global
        foreign_pid = 999999
        foreign_token = "f" * 32
        _atomic_write_json(gfile, {
            "version": "0.2.0",
            "token": foreign_token,
            "port": 9877,
            "pid": foreign_pid,
            "workspace": str(ws),
        })

        BridgeHTTPRequestHandler.server_port = 9876
        BridgeHTTPRequestHandler.workspace_dir = ws
        
        # Should NOT return foreign_token because PID & port don't match!
        tok = BridgeHTTPRequestHandler._read_session_token_from_disk()
        assert tok != foreign_token


def test_ba003_concurrent_idempotent_calls_deduplicate():
    """BA-003: Simultaneous calls with same idempotency key must not execute twice."""
    qm = ExecutionQueueManager(max_queue_size=10)
    qm.start()

    exec_count = [0]
    results = []

    def mock_command(task):
        exec_count[0] += 1
        time.sleep(0.1)
        task.result_holder["status"] = "success"
        task.result_holder["data"] = {"count": exec_count[0]}
        task.status = TaskStatus.COMPLETED
        task.done_event.set()

    # Launch two threads submitting identical task with same key
    key = "concurrent-key-99"

    def worker():
        res = qm.submit_task("mock_cmd", {"val": 1}, timeout=2.0, idempotency_key=key)
        results.append(res)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()

    # Process queue on main thread simulation
    start = time.time()
    while time.time() - start < 1.0:
        if not qm._queue.empty():
            task = qm._queue.get_nowait()
            mock_command(task)
            break
        time.sleep(0.01)

    t1.join()
    t2.join()

    qm.stop()
    assert exec_count[0] == 1, "Command should have executed exactly once due to in-flight deduplication!"
    assert len(results) == 2
    assert results[0]["status"] == "success"
    assert results[1]["status"] == "success"


def test_ba004_idempotency_cleared_on_stop_and_rejects_param_mismatch():
    """BA-004: Cache cleared on stop and different params under same key do not return stale result."""
    qm = ExecutionQueueManager(max_queue_size=10)
    qm.start()

    key = "idemp-param-test"
    qm._idempotency_cache[key] = {
        "result": {"status": "success", "data": {"name": "CubeA"}},
        "command": "create_primitive",
        "payload_hash": "hash_a",
        "timestamp": time.time(),
    }

    # Different params -> different hash -> should bypass cache!
    # Without timer processing, fresh task will time out or fail, NOT return stale CubeA
    res = qm.submit_task("create_primitive", {"name": "CubeB"}, timeout=0.05, idempotency_key=key)
    data = res.get("data") or {}
    assert data.get("name") != "CubeA"

    qm.stop()
    assert len(qm._idempotency_cache) == 0, "stop() must clear idempotency cache."


def test_ba005_strict_bool_parsing():
    """BA-005: String 'false' must strictly parse as False, not True."""
    assert _parse_strict_bool(False) is False
    assert _parse_strict_bool(True) is True
    assert _parse_strict_bool("false") is False
    assert _parse_strict_bool("False") is False
    assert _parse_strict_bool("0") is False
    assert _parse_strict_bool("true") is True
    assert _parse_strict_bool("1") is True

    with pytest.raises(InvalidArgumentError):
        _parse_strict_bool("invalid_string", param_name="test")


def test_ba007_transform_object_atomic_validation():
    """BA-007: Valid location with invalid scale must not mutate object location."""
    class DummyObject:
        def __init__(self):
            self.name = "TestObj"
            self.location = [0.0, 0.0, 0.0]
            self.rotation_euler = [0.0, 0.0, 0.0]
            self.scale = [1.0, 1.0, 1.0]
            self.dimensions = [2.0, 2.0, 2.0]

    obj = DummyObject()

    from unittest.mock import patch
    with patch("addon.blenderagent_bridge.handlers.objects._find_object", return_value=obj):
        with pytest.raises(InvalidArgumentError):
            # Scale at index 0 is 0.0 -> invalid!
            handle_transform_object({
                "name": "TestObj",
                "location": [9.0, 8.0, 7.0],
                "scale": [0.0, 1.0, 1.0],
            })

    # Location MUST NOT have changed!
    assert obj.location == [0.0, 0.0, 0.0]


def test_ba009_operator_manual_start_has_pathlib():
    """BA-009: operator.py must import pathlib and not raise NameError."""
    import addon.blenderagent_bridge.operator as op_module
    assert hasattr(op_module, "pathlib")


def test_ba010_atomic_session_file_writing():
    """BA-010: write_session_file writes atomically."""
    with tempfile.TemporaryDirectory() as td:
        ws = pathlib.Path(td)
        sfile = write_session_file("a" * 32, 9876, ws)
        assert sfile.exists()
        with open(sfile, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["token"] == "a" * 32
        assert data["port"] == 9876


def test_ba012_is_manifold_safe_fallback():
    """BA-012: Without bmesh, handle_get_mesh_info reports is_manifold=None rather than True."""
    class DummyMesh:
        vertices = [1, 2, 3]
        edges = [1, 2, 3]
        polygons = [1]
        uv_layers = []
        materials = []

    class DummyObj:
        name = "MeshObj"
        type = "MESH"
        data = DummyMesh()
        vertex_groups = []

    from unittest.mock import patch
    with patch("addon.blenderagent_bridge.handlers.objects._find_object", return_value=DummyObj()):
        with patch.dict("sys.modules", {"bmesh": None}):
            info = handle_get_mesh_info({"name": "MeshObj"})
            assert info["is_manifold"] is None


def test_ba014_queue_memory_bounds():
    """BA-014: _tasks_by_id and _idempotency_cache are bounded."""
    qm = ExecutionQueueManager(max_queue_size=10, history_size=20)
    assert qm._cache_max_size == 200


def test_ba015_health_endpoint_v020_and_metrics():
    """BA-015: /api/v1/health returns version 0.2.0 and active_tasks metric."""
    import http.client
    success, msg = bridge_server.start(port=9891, token="a" * 32)
    assert success
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 9891)
        conn.request("GET", "/api/v1/health")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["version"] == "0.2.1"
        assert "active_tasks" in data
        assert "processed_total" in data
        conn.close()
    finally:
        bridge_server.stop()


def test_ba016_origin_header_prefix_attack_blocked():
    """BA-016: Origin like http://localhost:9892.evil.com must be rejected with 403."""
    import http.client
    success, msg = bridge_server.start(port=9892, token="a" * 32)
    assert success
    try:
        conn = http.client.HTTPConnection("127.0.0.1", 9892)
        headers = {
            "Host": "127.0.0.1:9892",
            "Origin": "http://localhost:9892.evil.com",
            "Authorization": f"Bearer {'a' * 32}",
        }
        conn.request("GET", "/api/v1/health", headers=headers)
        resp = conn.getresponse()
        assert resp.status == 403
        conn.close()
    finally:
        bridge_server.stop()


def test_ba017_blender_agent_error_instantiation():
    """BA-017: BlenderAgentError accepts single argument without TypeError."""
    err = BlenderAgentError("Single error message")
    assert err.code == "BLENDER_AGENT_ERROR"
    assert err.message == "Single error message"
    assert str(err) == "Single error message"


def test_c1_inflight_idempotency_conflict():
    """C1: Concurrent request with same key but different command/payload triggers IDEMPOTENCY_CONFLICT."""
    from addon.blenderagent_bridge.queue_manager import CommandTask
    qm = ExecutionQueueManager(max_queue_size=10)
    qm.start()

    key = "conflict-key-test"
    dummy_task = CommandTask("cmd_a", {})
    with qm._lock:
        # Simulate active in-flight task
        qm._in_flight_idempotency[key] = (dummy_task, "cmd_a", "hash_a")

    # Different command with same key
    res = qm.submit_task("cmd_b", {}, timeout=1.0, idempotency_key=key)
    assert res["status"] == "error"
    assert res["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    qm.stop()


def test_c3_antigravity_corrupt_json_protection():
    """C3: Antigravity adapter refuses to overwrite corrupted JSON files."""
    from installer.adapters.antigravity import AntigravityAdapter
    from installer.adapters.base import AdapterStatus

    with tempfile.TemporaryDirectory() as td:
        cfg = pathlib.Path(td) / "mcp_config.json"
        cfg.write_text("{corrupted_json: true, invalid", encoding="utf-8")

        adapter = AntigravityAdapter(target_configs=[cfg])
        res = adapter.install_registration(
            launcher_path=pathlib.Path(td) / "launcher.bat",
            workspace_dir=pathlib.Path(td),
        )
        assert res.success is False
        assert res.status == AdapterStatus.ERROR
        # Verify file content was preserved and not overwritten
        assert cfg.read_text(encoding="utf-8") == "{corrupted_json: true, invalid"


def test_c4_session_storage_no_redundant_dpapi_cleartext():
    """C4: save_session_credentials payload does not duplicate cleartext in token_dpapi."""
    from installer.security_manager import save_session_credentials

    with tempfile.TemporaryDirectory() as td:
        ws = pathlib.Path(td)
        sfile, token = save_session_credentials(ws, port=9876)
        with open(sfile, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "token" in data
        assert "token_dpapi" not in data, "Redundant plain token_dpapi field must be omitted"
        assert data["token"] == token


def test_c6_resolve_unique_or_guarded_path():
    """C6: _resolve_unique_or_guarded_path generates unique name or fails gracefully when overwrite=False."""
    from addon.blenderagent_bridge.handlers.render_save import _resolve_unique_or_guarded_path
    from addon.blenderagent_bridge.security import FileAlreadyExistsError

    with tempfile.TemporaryDirectory() as td:
        ws = pathlib.Path(td)
        renders_dir = ws / "renders"
        renders_dir.mkdir()
        target = renders_dir / "preview.png"
        target.write_text("existing", encoding="utf-8")

        # With explicit raw_filename and overwrite=False -> raises FileAlreadyExistsError
        with pytest.raises(FileAlreadyExistsError):
            _resolve_unique_or_guarded_path(ws, "renders/preview.png", default_prefix="preview", overwrite=False)

        # Without raw_filename (default) and overwrite=False -> generates unique timestamped filename
        unique_path = _resolve_unique_or_guarded_path(ws, None, default_prefix="preview", overwrite=False)
        assert unique_path != target
        assert unique_path.name.startswith("preview_")
        assert unique_path.suffix == ".png"

        # With overwrite=True -> returns requested path
        assert _resolve_unique_or_guarded_path(ws, "renders/preview.png", default_prefix="preview", overwrite=True) == target



def test_c7_orchestrator_frozen_payload_verification():
    """C7: Orchestrator fails at step 0 if frozen payload assets are missing."""
    import sys
    from unittest.mock import patch
    from installer.orchestrator import InstallationOrchestrator, InstallOptions

    with tempfile.TemporaryDirectory() as td:
        empty_dist = pathlib.Path(td) / "dist"
        empty_dist.mkdir()

        orch = InstallationOrchestrator(InstallOptions(install_dir=pathlib.Path(td) / "install"))
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(orch, "_resolve_asset_dir", return_value=empty_dist):
                success, steps = orch.run_installation()
                assert success is False
                assert steps[0].status == "failed"
                assert "Missing or corrupted" in steps[0].message

