"""Security utilities, path containment validation, and session management for BlenderAgent Bridge."""

from __future__ import annotations

import collections
import json
import os
import pathlib
import secrets
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class BlenderAgentError(Exception):
    """Base error for all BlenderAgent Bridge exceptions."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class SecurityViolationError(BlenderAgentError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("SECURITY_VIOLATION", message, details)


class ObjectNotFoundError(BlenderAgentError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("OBJECT_NOT_FOUND", message, details)


class InvalidArgumentError(BlenderAgentError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("INVALID_ARGUMENT", message, details)


class FileAlreadyExistsError(BlenderAgentError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("ALREADY_EXISTS", message, details)


class ExecutionTimeoutError(BlenderAgentError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("EXECUTION_TIMEOUT", message, details)


def generate_session_token() -> str:
    """Generate a cryptographically secure 32-character hexadecimal token."""
    return secrets.token_hex(16)


def validate_workspace_path(
    workspace_dir: str | pathlib.Path,
    target_path_str: str | pathlib.Path,
    allow_create_dir: bool = True,
) -> pathlib.Path:
    """Validate that target_path_str resides strictly within workspace_dir.

    Resolves symbolic links and relative segments ('..').
    Raises SecurityViolationError if the path escapes workspace boundaries.
    """
    if not workspace_dir:
        raise SecurityViolationError("Workspace directory is not configured.")

    base = pathlib.Path(workspace_dir).resolve()

    # Reject null bytes or empty strings
    raw_str = str(target_path_str).strip()
    if not raw_str or "\x00" in raw_str:
        raise InvalidArgumentError("Invalid or empty file path.")

    # Target path handling
    candidate = pathlib.Path(raw_str)
    if candidate.is_absolute():
        target = candidate.resolve()
    else:
        target = (base / candidate).resolve()

    # Verify containment
    try:
        target.relative_to(base)
    except ValueError:
        raise SecurityViolationError(
            f"Path traversal detected: '{raw_str}' resolves outside workspace '{base}'."
        )

    if allow_create_dir:
        target.parent.mkdir(parents=True, exist_ok=True)

    return target


def write_session_file(token: str, port: int, workspace_dir: str | pathlib.Path) -> pathlib.Path:
    """Write session metadata to .blenderagent_session.json in workspace."""
    base = pathlib.Path(workspace_dir).resolve()
    session_file = base / ".blenderagent_session.json"
    data = {
        "token": token,
        "port": port,
        "workspace": str(base),
        "created_at": time.time(),
        "host": "127.0.0.1",
    }
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return session_file


def remove_session_file(workspace_dir: str | pathlib.Path) -> None:
    """Remove session file on shutdown."""
    try:
        base = pathlib.Path(workspace_dir).resolve()
        session_file = base / ".blenderagent_session.json"
        if session_file.exists():
            session_file.unlink()
    except Exception:
        pass


class AuditLogger:
    """Thread-safe in-memory ring buffer recording operational events."""

    def __init__(self, maxlen: int = 50):
        self._records = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._counter = 0

    def log(self, command: str, status: str, summary: str, client_ip: str = "127.0.0.1") -> None:
        with self._lock:
            self._counter += 1
            timestamp = time.strftime("%H:%M:%S")
            self._records.appendleft({
                "id": self._counter,
                "time": timestamp,
                "command": command,
                "status": status,
                "summary": summary,
                "client_ip": client_ip,
            })

    def get_recent(self, count: int = 5) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._records)[:count]

    @property
    def total_count(self) -> int:
        with self._lock:
            return self._counter

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._counter = 0


# Global audit logger instance
audit_logger = AuditLogger()
