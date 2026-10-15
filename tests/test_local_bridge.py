"""Integration tests for the local HTTP server, auth verification, and request routing."""

from __future__ import annotations

import threading
import time
import httpx
import pytest

from addon.blenderagent_bridge.queue_manager import queue_manager, TaskStatus
from addon.blenderagent_bridge.server import BlenderAgentServer


@pytest.fixture
def test_server(temp_workspace):
    """Spin up a dedicated test instance of BlenderAgentServer on an ephemeral port."""
    server = BlenderAgentServer()
    # Choose a high port for testing
    port = 9885
    token = "test_secret_token_123456789012"
    success, msg = server.start(port=port, token=token, workspace_dir=temp_workspace)
    assert success, f"Failed to start test server: {msg}"

    # Also start queue manager in simulation mode (mocking main thread ticks in a background thread)
    stop_sim = threading.Event()

    def mock_main_thread():
        while not stop_sim.is_set():
            # Process tasks
            queue_manager.process_queue_tick()
            time.sleep(0.01)

    t = threading.Thread(target=mock_main_thread, daemon=True)
    t.start()

    yield server, port, token

    stop_sim.set()
    server.stop()


def test_health_endpoint(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/health"
    with httpx.Client(timeout=2.0) as client:
        res = client.get(url)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "blenderagent-bridge"


def test_missing_auth_token_rejected(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/command"
    payload = {"command": "get_scene_info", "params": {}}
    with httpx.Client(timeout=2.0) as client:
        res = client.post(url, json=payload)
        assert res.status_code == 401
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "UNAUTHORIZED"


def test_invalid_auth_token_rejected(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/command"
    payload = {"command": "get_scene_info", "params": {}}
    headers = {"Authorization": "Bearer wrong_token_value"}
    with httpx.Client(timeout=2.0) as client:
        res = client.post(url, json=payload, headers=headers)
        assert res.status_code == 401
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "UNAUTHORIZED"


def test_malformed_json_rejected(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/command"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=2.0) as client:
        res = client.post(url, content=b"{not valid json", headers=headers)
        assert res.status_code == 400
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "INVALID_JSON"


def test_missing_command_field(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/command"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"params": {}}  # No command
    with httpx.Client(timeout=2.0) as client:
        res = client.post(url, json=payload, headers=headers)
        assert res.status_code == 400
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "INVALID_ARGUMENT"


def test_server_restart_and_cleanup(test_server, temp_workspace):
    server, port, token = test_server
    # Verify session file was written
    session_file = temp_workspace / ".blenderagent_session.json"
    assert session_file.exists()

    # Stop server
    success, msg = server.stop()
    assert success
    assert not server.is_running
    assert not session_file.exists()


def test_bridge_unavailable_when_offline(temp_workspace):
    from mcp_server.client import BlenderBridgeClient
    client = BlenderBridgeClient(port=9999, token="fake", workspace_dir=temp_workspace)
    resp = client.send_command("get_scene_info", {})
    assert resp.status == "error"
    assert resp.error is not None
    assert resp.error.code == "BRIDGE_UNAVAILABLE"


def test_unknown_command_returns_structured_error(test_server):
    from mcp_server.client import BlenderBridgeClient
    server, port, token = test_server
    client = BlenderBridgeClient(port=port, token=token, workspace_dir=server.workspace)
    resp = client.send_command("unknown_invalid_action", {})
    assert resp.status == "error"
    assert resp.error is not None
    assert resp.error.code == "INVALID_ARGUMENT"
    assert "supported_commands" in resp.error.details


def test_client_workspace_override_rejected(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/command"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    # Attacker tries to hijack workspace_dir
    payload = {
        "command": "save_project",
        "params": {
            "workspace_dir": "C:/Windows/System32",
            "filename": "hacked.blend",
        },
    }
    with httpx.Client(timeout=2.0) as client:
        res = client.post(url, json=payload, headers=headers)
        assert res.status_code == 403
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "SECURITY_VIOLATION"
        assert "workspace_dir" in data["error"]["message"]


def test_invalid_content_type_rejected(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/command"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain",
    }
    with httpx.Client(timeout=2.0) as client:
        res = client.post(url, content=b'{"command": "get_scene_info"}', headers=headers)
        assert res.status_code == 415
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "INVALID_CONTENT_TYPE"


def test_untrusted_host_header_rejected(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/status"
    headers = {"Host": "attacker.domain.com"}
    with httpx.Client(timeout=2.0) as client:
        res = client.get(url, headers=headers)
        assert res.status_code == 403
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "FORBIDDEN_HOST"


def test_untrusted_origin_header_rejected(test_server):
    server, port, token = test_server
    url = f"http://127.0.0.1:{port}/api/v1/status"
    headers = {"Origin": "http://evil-website.com"}
    with httpx.Client(timeout=2.0) as client:
        res = client.get(url, headers=headers)
        assert res.status_code == 403
        data = res.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == "FORBIDDEN_ORIGIN"


def test_task_status_endpoint(test_server):
    from addon.blenderagent_bridge.queue_manager import queue_manager, CommandTask
    server, port, token = test_server
    
    # Enqueue a dummy task directly to test status endpoint
    task = CommandTask("get_scene_info", {})
    queue_manager._tasks_by_id[task.task_id] = task

    url = f"http://127.0.0.1:{port}/api/v1/tasks/{task.task_id}"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=2.0) as client:
        res = client.get(url, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["data"]["task_id"] == task.task_id
        assert data["data"]["command"] == "get_scene_info"


def test_task_cancel_endpoint(test_server):
    from addon.blenderagent_bridge.queue_manager import queue_manager, CommandTask
    server, port, token = test_server

    task = CommandTask("create_primitive", {"type": "cube"})
    task.status = TaskStatus.RUNNING
    queue_manager._tasks_by_id[task.task_id] = task

    url = f"http://127.0.0.1:{port}/api/v1/tasks/{task.task_id}/cancel"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=2.0) as client:
        res = client.post(url, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["data"]["cancelled"] is True
        assert task.cancel_event.is_set()



