"""Main-thread execution queue, state machine, and cancellation manager for BlenderAgent Bridge."""

from __future__ import annotations

import collections
from enum import Enum
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

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_timer_running

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

                    # Cache result for idempotency if applicable
                    if task.idempotency_key and task.status == TaskStatus.COMPLETED:
                        with self._lock:
                            self._idempotency_cache[task.idempotency_key] = dict(task.result_holder)

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
        """Unregister timer and cleanly drain/cancel all pending tasks."""
        with self._lock:
            self._is_timer_running = False

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
                return True, f"Running task '{task_id}' marked for cancellation."

    def submit_task(
        self,
        command_name: str,
        params: Dict[str, Any],
        timeout: float = 30.0,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enqueue task and wait for completion or timeout."""
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

            # Check idempotency cache
            if idempotency_key and idempotency_key in self._idempotency_cache:
                cached = dict(self._idempotency_cache[idempotency_key])
                cached["cached_idempotent"] = True
                return cached

        task = CommandTask(
            command_name=command_name,
            params=params,
            timeout=timeout,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )

        with self._lock:
            self._tasks_by_id[task.task_id] = task
            self._tasks_history.append(task)

        # Enqueue with overflow protection
        try:
            self._queue.put_nowait(task)
        except queue.Full:
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

        # Await completion on calling HTTP worker thread
        completed = task.done_event.wait(timeout=timeout)

        if not completed:
            with task.lock:
                task.cancel_event.set()
                if task.status == TaskStatus.QUEUED:
                    task.status = TaskStatus.TIMED_OUT
                    task.result_holder["status"] = "error"
                    task.result_holder["error"] = {
                        "code": "EXECUTION_TIMEOUT",
                        "message": f"Command '{command_name}' expired in queue after {timeout}s before starting.",
                        "details": {"phase": "queued", "timeout_seconds": timeout},
                    }
                else:
                    task.status = TaskStatus.TIMED_OUT
                    task.result_holder["status"] = "error"
                    task.result_holder["error"] = {
                        "code": "EXECUTION_TIMEOUT",
                        "message": f"Command '{command_name}' timed out after {timeout}s while executing.",
                        "details": {"phase": "running", "timeout_seconds": timeout},
                    }
                task.result_holder["message"] = "Operation timed out."

            audit_logger.log(command_name, "TIMEOUT", f"Timed out after {timeout}s ({task.status.value})")

        return task.result_holder


# Global queue manager singleton
queue_manager = ExecutionQueueManager()
