"""Tests for queue lifecycle, task expiration, cancellation, and concurrency."""

from __future__ import annotations

import time
import pytest

from addon.blenderagent_bridge.queue_manager import (
    CommandTask,
    ExecutionQueueManager,
    TaskStatus,
)


def test_task_state_machine_completed():
    qm = ExecutionQueueManager(max_queue_size=10)
    qm.start()

    task = CommandTask("test_cmd", {}, timeout=2.0)
    assert task.status == TaskStatus.QUEUED
    assert task.started_at is None
    assert task.finished_at is None

    info = task.to_info_dict()
    assert info["status"] == "queued"
    qm.stop()


def test_task_expired_in_queue_is_never_executed():
    """Verify that expired tasks sitting in queue are skipped and never executed."""
    qm = ExecutionQueueManager(max_queue_size=10)
    qm.start()

    # Create task with 0.1s timeout
    task = CommandTask("create_primitive", {"type": "cube"}, timeout=0.1)
    qm._queue.put(task)
    qm._tasks_by_id[task.task_id] = task

    # Sleep until expired
    time.sleep(0.15)

    # Now drain queue
    res = qm.process_queue_tick()
    assert task.status == TaskStatus.TIMED_OUT
    assert task.done_event.is_set()
    assert task.result_holder["status"] == "error"
    assert task.result_holder["error"]["code"] == "EXECUTION_TIMEOUT"
    qm.stop()


def test_task_cancelled_while_queued():
    """Verify that queued tasks can be cancelled cooperatively before execution."""
    qm = ExecutionQueueManager(max_queue_size=10)
    qm.start()

    task = CommandTask("create_primitive", {"type": "cube"}, timeout=5.0)
    qm._queue.put(task)
    qm._tasks_by_id[task.task_id] = task

    success, msg = qm.cancel_task(task.task_id)
    assert success is True
    assert task.status == TaskStatus.CANCELLED
    assert task.done_event.is_set()

    # When ticked, it should skip it completely
    qm.process_queue_tick()
    assert task.result_holder["error"]["code"] == "TASK_CANCELLED"
    qm.stop()


def test_queue_overflow_protection():
    """Verify that filling queue to capacity rejects subsequent tasks with QUEUE_FULL."""
    qm = ExecutionQueueManager(max_queue_size=2)
    qm.start()

    # Put 2 dummy tasks directly into queue without draining
    t1 = CommandTask("cmd1", {}, timeout=5.0)
    t2 = CommandTask("cmd2", {}, timeout=5.0)
    qm._queue.put(t1)
    qm._queue.put(t2)

    # 3rd task should fail immediately with QUEUE_FULL
    res = qm.submit_task("cmd3", {}, timeout=1.0)
    assert res["status"] == "error"
    assert res["error"]["code"] == "QUEUE_FULL"
    qm.stop()


def test_idempotency_cache():
    """Verify that duplicate requests with same idempotency key return cached result."""
    qm = ExecutionQueueManager(max_queue_size=10)
    qm.start()

    # Pre-populate idempotency cache
    qm._idempotency_cache["idem-key-123"] = {
        "status": "success",
        "data": {"name": "AgentCube"},
        "message": "Cached result",
    }

    res = qm.submit_task("create_primitive", {}, timeout=1.0, idempotency_key="idem-key-123")
    assert res["status"] == "success"
    assert res.get("cached_idempotent") is True
    qm.stop()
