"""Main-thread execution queue, state machine, and cancellation manager for BlenderAgent Bridge."""

from __future__ import annotations

import collections
import copy
from enum import Enum
import hashlib
import json
import queue
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

try:
    import bpy
except ImportError:
    bpy = None

from .handlers import dispatch_command
from .security import (
    BlenderAgentError,
    ExecutionTimeoutError,
    audit_logger,
)


def _hash_payload(command: str, params: Dict[str, Any]) -> str:
    """Stable hash of command and parameters ignoring dynamic workspace_dir."""
    filtered = {k: v for k, v in params.items() if k != "workspace_dir"}
    try:
        raw = json.dumps({"cmd": command, "params": filtered}, sort_keys=True)
    except Exception:
        raw = str(filtered)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


class CommandTask:
    """Represents an operation to be executed on Blender's main thread."""

    def __init__(
        self,
        command_name: str,
        params: Dict[str, Any],
        timeout: float = 30.0,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ):
        self.task_id = request_id or str(uuid.uuid4())
        self.idempotency_key = idempotency_key
        self.command_name = command_name
        self.params = params
        self.timeout = max(0.01, float(timeout))
        self.created_at = time.time()
        self.expires_at = self.created_at + self.timeout
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

        self.status: TaskStatus = TaskStatus.QUEUED
        self.done_event = threading.Event()
        self.cancel_event = threading.Event()
        self.lock = threading.Lock()

        self.result_holder: Dict[str, Any] = {
            "task_id": self.task_id,
            "status": "pending",
            "data": None,
            "error": None,
            "message": "",
            "request_id": self.task_id,
        }

    def to_info_dict(self) -> Dict[str, Any]:
        """Return non-blocking task metadata."""
        with self.lock:
            elapsed = None
            if self.started_at and self.finished_at:
                elapsed = round(self.finished_at - self.started_at, 4)
            elif self.started_at:
                elapsed = round(time.time() - self.started_at, 4)

            return {
                "task_id": self.task_id,
                "command": self.command_name,
                "status": self.status.value,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed_seconds": elapsed,
                "timeout": self.timeout,
            }


class ExecutionQueueManager:
    """Thread-safe queue manager executing operations strictly on Blender's main thread."""

    def __init__(self, max_queue_size: int = 50, history_size: int = 100):
        self._queue: queue.Queue[CommandTask] = queue.Queue(maxsize=max_queue_size)
        self._is_timer_running = False
        self._lock = threading.Lock()
        self._tasks_history: collections.deque[CommandTask] = collections.deque(maxlen=history_size)
        self._tasks_by_id: Dict[str, CommandTask] = {}
        self._idempotency_cache: Dict[str, Dict[str, Any]] = {}
        self._in_flight_idempotency: Dict[str, CommandTask] = {}
        self._cache_max_size = 200
        self._cache_ttl_seconds = 600.0  # 10 minutes

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_timer_running

    @property
    def active_count(self) -> int:
        """Count of tasks currently queued or running."""
        with self._lock:
            return sum(
                1 for t in self._tasks_by_id.values()
                if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)
            )

    def process_queue_tick(self) -> Optional[float]:
        """Timer callback invoked strictly on Blender's main thread.

        Drains up to 10 tasks per tick, respecting timeouts and cancellation.
        """
        max_batch = 10
        processed = 0

        while processed < max_batch:
            try:
                task = self._queue.get_nowait()
            except queue.Empty:
                break

            processed += 1
            cmd_name = task.command_name
            now = time.time()

            # 1. Check if task expired or was cancelled while waiting in queue
            with task.lock:
                if task.cancel_event.is_set():
                    task.status = TaskStatus.CANCELLED
                    task.finished_at = now
                    task.result_holder["status"] = "error"
                    task.result_holder["error"] = {
                        "code": "TASK_CANCELLED",
                        "message": f"Task '{task.task_id}' was cancelled before execution started.",
                    }
                    task.result_holder["message"] = "Task cancelled while queued."
                    task.done_event.set()
                    self._queue.task_done()
                    audit_logger.log(cmd_name, "CANCELLED", f"Pre-execution cancel: {task.task_id}")
                    continue

                if now >= task.expires_at:
                    task.status = TaskStatus.TIMED_OUT
                    task.finished_at = now
                    task.result_holder["status"] = "error"
                    task.result_holder["error"] = {
                        "code": "EXECUTION_TIMEOUT",
                        "message": f"Task '{task.task_id}' expired ({now - task.created_at:.2f}s) while queued before execution.",
                        "details": {"wait_time_seconds": now - task.created_at, "timeout_seconds": task.timeout},
                    }
                    task.result_holder["message"] = "Task timed out in queue."
                    task.done_event.set()
                    self._queue.task_done()
                    audit_logger.log(cmd_name, "EXPIRED", f"Queue wait expired: {task.task_id}")
                    continue

                # 2. Mark task as RUNNING
                task.status = TaskStatus.RUNNING
                task.started_at = now

            # 3. Synchronous execution on Blender main thread
            ctx = getattr(bpy, "context", None) if bpy else None

            try:
                result_data = dispatch_command(cmd_name, task.params, ctx)

                with task.lock:
                    if task.cancel_event.is_set():
                        # Completed but caller requested cancellation in transit
                        task.status = TaskStatus.INTERRUPTED
                        task.result_holder["status"] = "error"
                        task.result_holder["error"] = {
                            "code": "TASK_INTERRUPTED",
                            "message": f"Command executed but was cancelled or timed out by client.",
                        }
                        task.result_holder["message"] = "Execution completed after cancel/timeout."
                    else:
                        task.status = TaskStatus.COMPLETED
                        task.result_holder["status"] = "success"
                        task.result_holder["data"] = result_data
                        task.result_holder["error"] = None
                        task.result_holder["message"] = f"Command '{cmd_name}' completed successfully."

                audit_logger.log(cmd_name, "SUCCESS" if task.status == TaskStatus.COMPLETED else "INTERRUPTED", f"OK: {cmd_name}")

            except BlenderAgentError as bae:
                with task.lock:
                    task.status = TaskStatus.FAILED
                    task.result_holder["status"] = "error"
                    task.result_holder["data"] = None
                    task.result_holder["error"] = bae.to_dict()
                    task.result_holder["message"] = bae.message
                audit_logger.log(cmd_name, "ERROR", f"[{bae.code}] {bae.message}")

            except Exception as exc:
                with task.lock:
                    task.status = TaskStatus.FAILED
                    task.result_holder["status"] = "error"
                    task.result_holder["data"] = None
                    task.result_holder["error"] = {
                        "code": "INTERNAL_ERROR",
                        "message": str(exc),
                        "details": {"exception_type": type(exc).__name__},
                    }
                    task.result_holder["message"] = f"Unexpected error during '{cmd_name}': {exc}"
                audit_logger.log(cmd_name, "ERROR", f"Internal: {type(exc).__name__}")

            finally:
                task.finished_at = time.time()
                task.done_event.set()
                self._queue.task_done()

        with self._lock:
            if self._is_timer_running:
                return 0.01  # Reschedule in 10ms
            return None

    def start(self) -> None:
        """Register queue consumer with bpy.app.timers."""
        with self._lock:
            if not self._is_timer_running:
                self._is_timer_running = True
                if bpy and hasattr(bpy, "app") and hasattr(bpy.app, "timers"):
                    if not bpy.app.timers.is_registered(self.process_queue_tick):
                        bpy.app.timers.register(self.process_queue_tick, first_interval=0.01, persistent=True)

    def stop(self) -> None:
        """Unregister timer, cleanly drain/cancel all pending tasks, and clear caches."""
        with self._lock:
            self._is_timer_running = False
            self._idempotency_cache.clear()
            self._in_flight_idempotency.clear()

        if bpy and hasattr(bpy, "app") and hasattr(bpy.app, "timers"):
            if bpy.app.timers.is_registered(self.process_queue_tick):
                try:
                    bpy.app.timers.unregister(self.process_queue_tick)
                except Exception:
                    pass

        # Drain any remaining tasks
        while not self._queue.empty():
            try:
                task = self._queue.get_nowait()
                with task.lock:
                    task.status = TaskStatus.CANCELLED
                    task.result_holder["status"] = "error"
                    task.result_holder["error"] = {
                        "code": "BRIDGE_STOPPED",
                        "message": "BlenderAgent Bridge was stopped before command could be processed.",
                    }
                    task.done_event.set()
                self._queue.task_done()
            except queue.Empty:
                break

    def get_task(self, task_id: str) -> Optional[CommandTask]:
        """Retrieve task by ID."""
        with self._lock:
            return self._tasks_by_id.get(task_id)

    def cancel_task(self, task_id: str) -> Tuple[bool, str]:
        """Request cooperative cancellation of a task."""
        task = self.get_task(task_id)
        if not task:
            return False, f"Task '{task_id}' not found."

        with task.lock:
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT):
                return False, f"Task '{task_id}' is already finished with status '{task.status.value}'."

            task.cancel_event.set()
            if task.status == TaskStatus.QUEUED:
                task.status = TaskStatus.CANCELLED
                task.result_holder["status"] = "error"
                task.result_holder["error"] = {
                    "code": "TASK_CANCELLED",
                    "message": f"Task '{task_id}' was cancelled by request.",
                }
                task.done_event.set()
                return True, f"Queued task '{task_id}' cancelled immediately."
            else:
                task.status = TaskStatus.CANCEL_REQUESTED
                return True, f"Running task '{task_id}' marked for cancellation. Note: synchronous in-flight Blender operations cannot be preempted immediately."

    def submit_task(
        self,
        command_name: str,
        params: Dict[str, Any],
        timeout: float = 30.0,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enqueue task and wait for completion or timeout with atomic idempotency and in-flight deduplication."""
        payload_hash = _hash_payload(command_name, params) if idempotency_key else None
        now = time.time()

        with self._lock:
            if not self._is_timer_running:
                return {
                    "status": "error",
                    "data": None,
                    "error": {
                        "code": "BRIDGE_UNAVAILABLE",
                        "message": "BlenderAgent Bridge execution timer is not active.",
                    },
                    "message": "Bridge is not running.",
                    "request_id": request_id,
                }

            # 1. Check completed idempotency cache (BA-004, C2)
            if idempotency_key and idempotency_key in self._idempotency_cache:
                entry = self._idempotency_cache[idempotency_key]
                if isinstance(entry, dict) and "result" in entry:
                    if now - entry.get("timestamp", 0) <= self._cache_ttl_seconds:
                        if entry.get("command") == command_name and entry.get("payload_hash") == payload_hash:
                            cached = copy.deepcopy(entry["result"])
                            cached["cached_idempotent"] = True
                            if request_id:
                                cached["request_id"] = request_id
                            return cached
                        else:
                            return {
                                "status": "error",
                                "data": None,
                                "error": {
                                    "code": "IDEMPOTENCY_CONFLICT",
                                    "message": f"Idempotency key '{idempotency_key}' was previously used for a different command or payload.",
                                },
                                "message": "Idempotency key conflict: mismatched payload.",
                                "request_id": request_id,
                            }
                    else:
                        del self._idempotency_cache[idempotency_key]
                elif isinstance(entry, dict) and "status" in entry:
                    cached = copy.deepcopy(entry)
                    cached["cached_idempotent"] = True
                    if request_id:
                        cached["request_id"] = request_id
                    return cached

            # 2. Check in-flight deduplication (BA-003, C1, C2)
            if idempotency_key and idempotency_key in self._in_flight_idempotency:
                entry = self._in_flight_idempotency[idempotency_key]
                if isinstance(entry, tuple) and len(entry) >= 3:
                    candidate_task, candidate_cmd, candidate_hash = entry[0], entry[1], entry[2]
                elif isinstance(entry, dict):
                    candidate_task = entry.get("task")
                    candidate_cmd = entry.get("command")
                    candidate_hash = entry.get("payload_hash")
                else:
                    candidate_task, candidate_cmd, candidate_hash = None, None, None

                if candidate_cmd == command_name and candidate_hash == payload_hash and candidate_task:
                    target_in_flight = candidate_task
                else:
                    return {
                        "status": "error",
                        "data": None,
                        "error": {
                            "code": "IDEMPOTENCY_CONFLICT",
                            "message": f"Idempotency key '{idempotency_key}' is already in flight for a different operation or payload.",
                        },
                        "message": "Idempotency key conflict: concurrent operation with different payload.",
                        "request_id": request_id,
                    }
            else:
                target_in_flight = None

            if target_in_flight is None:
                # 3. Create fresh task and register atomically under the SAME lock (C1)
                task = CommandTask(
                    command_name=command_name,
                    params=params,
                    timeout=timeout,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                )

                # Memory bounds on _tasks_by_id (BA-014)
                if len(self._tasks_by_id) >= 200:
                    history_ids = {t.task_id for t in self._tasks_history}
                    to_remove = [
                        tid for tid, t in self._tasks_by_id.items()
                        if tid not in history_ids and t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT)
                    ]
                    for tid in to_remove[:50]:
                        self._tasks_by_id.pop(tid, None)

                self._tasks_by_id[task.task_id] = task
                self._tasks_history.append(task)
                if idempotency_key:
                    self._in_flight_idempotency[idempotency_key] = (task, command_name, payload_hash)

                try:
                    self._queue.put_nowait(task)
                except queue.Full:
                    if idempotency_key:
                        self._in_flight_idempotency.pop(idempotency_key, None)
                    task.status = TaskStatus.FAILED
                    task.result_holder["status"] = "error"
                    task.result_holder["error"] = {
                        "code": "QUEUE_FULL",
                        "message": "Execution queue is at maximum capacity. Try again shortly.",
                        "details": {"max_capacity": self._queue.maxsize},
                    }
                    task.done_event.set()
                    audit_logger.log(command_name, "QUEUE_FULL", "Execution queue saturated")
                    return task.result_holder

        # Wait outside lock for in-flight task
        if target_in_flight is not None:
            target_in_flight.done_event.wait(timeout=timeout)
            with target_in_flight.lock:
                result = copy.deepcopy(target_in_flight.result_holder)
            result["cached_idempotent"] = True
            if request_id:
                result["request_id"] = request_id
            return result

        try:
            # Await completion on calling HTTP worker thread
            completed = task.done_event.wait(timeout=timeout)

            if not completed:
                with task.lock:
                    task.cancel_event.set()
                    is_queued = (task.status == TaskStatus.QUEUED)
                    task.status = TaskStatus.TIMED_OUT
                    task.result_holder["status"] = "error"
                    if is_queued:
                        task.result_holder["error"] = {
                            "code": "EXECUTION_TIMEOUT",
                            "message": f"Command '{command_name}' expired in queue after {timeout}s before starting.",
                            "details": {"phase": "queued", "timeout_seconds": timeout},
                        }
                    else:
                        task.result_holder["error"] = {
                            "code": "EXECUTION_TIMEOUT",
                            "message": f"Command '{command_name}' timed out after {timeout}s while executing.",
                            "details": {
                                "phase": "running",
                                "timeout_seconds": timeout,
                                "state": "blender_operation_in_flight",
                                "note": "Operation was in-flight on Blender's main thread and cannot be forcibly preempted asynchronously.",
                            },
                        }
                    task.result_holder["message"] = "Operation timed out."

                audit_logger.log(command_name, "TIMEOUT", f"Timed out after {timeout}s ({task.status.value})")

            return copy.deepcopy(task.result_holder)

        finally:
            with self._lock:
                if idempotency_key:
                    self._in_flight_idempotency.pop(idempotency_key, None)
                    # Cache result canonically if finished
                    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                        if len(self._idempotency_cache) >= self._cache_max_size:
                            oldest_key = min(
                                self._idempotency_cache.keys(),
                                key=lambda k: self._idempotency_cache[k].get("timestamp", 0),
                            )
                            self._idempotency_cache.pop(oldest_key, None)

                        self._idempotency_cache[idempotency_key] = {
                            "result": copy.deepcopy(task.result_holder),
                            "command": command_name,
                            "payload_hash": payload_hash,
                            "timestamp": time.time(),
                        }


# Global queue manager singleton
queue_manager = ExecutionQueueManager()
