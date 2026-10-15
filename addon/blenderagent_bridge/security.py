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


WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def validate_workspace_path(
    workspace_dir: str | pathlib.Path,
    target_path_str: str | pathlib.Path,
    allow_create_dir: bool = True,
) -> pathlib.Path:
    """Validate that target_path_str resides strictly within authorized workspace_dir.

    Hardened against:
    - Path traversal attacks (../, ..\\)
    - Absolute external path escapes
    - Windows Alternate Data Streams (ADS colons)
    - Windows reserved device names (CON, PRN, AUX, NUL, COM*, LPT*)
    - Illegal filesystem characters (*, ?, <, >, |, ")
    - Shared prefix collision attacks (e.g., workspace_evil vs workspace)
    - Symlink / junction breakout attacks
    """
    if not workspace_dir:
        raise SecurityViolationError("Workspace directory is not configured.")

    base = pathlib.Path(workspace_dir).resolve()

    raw_str = str(target_path_str).strip()
    if not raw_str or "\x00" in raw_str:
        raise InvalidArgumentError("Invalid or empty file path.")

    # Check for illegal characters (*, ?, <, >, |, ") in filename
    clean_check = raw_str.replace("\\", "/").split("/")
    for segment in clean_check:
        segment = segment.strip()
        if not segment:
            continue
        # Check colon in non-drive-letter segment (ADS attack)
        if ":" in segment:
            # Only drive letter on Windows (e.g. 'C:') is valid at index 0
            if clean_check.index(segment) != 0 or len(segment) != 2:
                raise SecurityViolationError(f"Prohibited stream or colon in path segment: '{segment}'.")

        # Check Windows reserved device names
        stem = segment.split(".")[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise SecurityViolationError(f"Prohibited reserved system device name in path: '{segment}'.")

        # Check wildcards or pipe
        if any(c in segment for c in ('*', '?', '<', '>', '|', '"')):
            raise InvalidArgumentError(f"Prohibited filesystem characters in path: '{segment}'.")

    # Canonicalize target path
    candidate = pathlib.Path(raw_str)
    if candidate.is_absolute():
        target = candidate.resolve()
    else:
        target = (base / candidate).resolve()

    # Enforce strict hierarchy containment
    try:
        is_contained = target.is_relative_to(base)
    except AttributeError:
        # Fallback for Python < 3.9
        try:
            target.relative_to(base)
            is_contained = True
        except ValueError:
            is_contained = False

    if not is_contained:
        raise SecurityViolationError(
            f"Path traversal detected: '{raw_str}' resolves to '{target}', outside workspace '{base}'."
        )

    # Prevent target from being the workspace directory itself
    if target == base:
        raise SecurityViolationError("Target file path cannot be the workspace root directory itself.")

    if allow_create_dir:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Verify created parent is still within workspace
        if not target.parent.resolve().is_relative_to(base):
            raise SecurityViolationError("Directory traversal detected during path parent creation.")

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
