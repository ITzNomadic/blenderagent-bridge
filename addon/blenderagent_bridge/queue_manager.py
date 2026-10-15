"""Main-thread execution queue and bpy.app.timers consumer for thread safety."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, Optional
import bpy

from .handlers import dispatch_command
from .security import (
    BlenderAgentError,
    ExecutionTimeoutError,
    audit_logger,
)


class CommandTask:
    """A task representing a command to be executed strictly on Blender's main thread."""

    def __init__(self, command_name: str, params: Dict[str, Any], request_id: Optional[str] = None):
        self.command_name = command_name
        self.params = params
        self.request_id = request_id
        self.created_at = time.time()
        self.done_event = threading.Event()
        self.result_holder: Dict[str, Any] = {
            "status": "pending",
            "data": None,
            "error": None,
            "message": "",
            "request_id": request_id,
        }


class ExecutionQueueManager:
    """Manages thread-safe task queuing and main-thread execution via bpy.app.timers."""

    def __init__(self):
        self._queue: queue.Queue[CommandTask] = queue.Queue()
        self._is_timer_running = False
        self._lock = threading.Lock()

    def process_queue_tick(self) -> Optional[float]:
        """Timer callback executed strictly on Blender's main thread.

        Returns interval in seconds (0.01s = 10ms) to reschedule, or None to stop.
        """
        # Drain up to 10 tasks per tick to avoid starving Blender's UI
        max_batch = 10
        processed = 0

        while processed < max_batch:
            try:
                task = self._queue.get_nowait()
            except queue.Empty:
                break

            processed += 1
            cmd_name = task.command_name

            try:
                # Dispatch handler safely in the main thread context
                result_data = dispatch_command(cmd_name, task.params, bpy.context)
                task.result_holder["status"] = "success"
                task.result_holder["data"] = result_data
                task.result_holder["error"] = None
                task.result_holder["message"] = f"Command '{cmd_name}' completed successfully."
                audit_logger.log(cmd_name, "SUCCESS", f"OK: {cmd_name}")

            except BlenderAgentError as bae:
                task.result_holder["status"] = "error"
                task.result_holder["data"] = None
                task.result_holder["error"] = bae.to_dict()
                task.result_holder["message"] = bae.message
                audit_logger.log(cmd_name, "ERROR", f"[{bae.code}] {bae.message}")

            except Exception as exc:
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
                task.done_event.set()
                self._queue.task_done()

        with self._lock:
            if self._is_timer_running:
                return 0.01  # Reschedule in 10ms
            return None

    def start(self) -> None:
        """Register the queue consumer timer with bpy.app.timers."""
        with self._lock:
            if not self._is_timer_running:
                self._is_timer_running = True
                if not bpy.app.timers.is_registered(self.process_queue_tick):
                    bpy.app.timers.register(self.process_queue_tick, first_interval=0.01, persistent=True)

    def stop(self) -> None:
        """Unregister the timer and drain any uncompleted tasks."""
        with self._lock:
            self._is_timer_running = False

        if bpy.app.timers.is_registered(self.process_queue_tick):
            try:
                bpy.app.timers.unregister(self.process_queue_tick)
            except Exception:
                pass

        # Drain and notify any pending tasks
        while not self._queue.empty():
            try:
                task = self._queue.get_nowait()
                task.result_holder["status"] = "error"
                task.result_holder["error"] = {
                    "code": "BRIDGE_STOPPED",
                    "message": "BlenderAgent Bridge was stopped before command could be processed.",
                }
                task.done_event.set()
                self._queue.task_done()
            except queue.Empty:
                break

    def submit_task(self, command_name: str, params: Dict[str, Any], timeout: float = 30.0, request_id: Optional[str] = None) -> Dict[str, Any]:
        """Enqueue task from HTTP worker thread and block until finished or timed out."""
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

        task = CommandTask(command_name, params, request_id=request_id)
        self._queue.put(task)

        completed = task.done_event.wait(timeout=timeout)
        if not completed:
            audit_logger.log(command_name, "TIMEOUT", f"Execution exceeded {timeout}s timeout")
            return {
                "status": "error",
                "data": None,
                "error": {
                    "code": "EXECUTION_TIMEOUT",
                    "message": f"Command '{command_name}' timed out after {timeout} seconds.",
                    "details": {"timeout_seconds": timeout},
                },
                "message": "Command execution timed out on Blender main thread.",
                "request_id": request_id,
            }

        return task.result_holder


# Global queue manager singleton
queue_manager = ExecutionQueueManager()
