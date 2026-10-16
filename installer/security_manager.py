"""Cryptographic token management and Windows-native DPAPI / ACL security for BlenderAgent Bridge."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import pathlib
import secrets
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple

from .constants import DEFAULT_WORKSPACE_DIR, LIVE_SESSION_FILE_PATH, SESSION_FILE_PATH


# Windows DPAPI structures
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def generate_secure_token() -> str:
    """Generate a high-entropy 256-bit cryptographic Bearer token (32 hex chars)."""
    return secrets.token_hex(16)


def dpapi_protect(plaintext: bytes, description: str = "BlenderAgentBridge-Token") -> Optional[bytes]:
    """Encrypt binary data using Windows Data Protection API (DPAPI - Current User scope)."""
    if sys.platform != "win32":
        return None

    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_blob = DATA_BLOB()
        in_blob.cbData = len(plaintext)
        in_blob.pbData = ctypes.cast(ctypes.create_string_buffer(plaintext), ctypes.POINTER(ctypes.c_byte))

        out_blob = DATA_BLOB()

        success = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            ctypes.c_wchar_p(description),
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )

        if not success:
            return None

        cipher_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        kernel32.LocalFree(out_blob.pbData)
        return cipher_bytes
    except Exception:
        return None


def dpapi_unprotect(ciphertext: bytes) -> Optional[bytes]:
    """Decrypt binary data using Windows Data Protection API (DPAPI - Current User scope)."""
    if sys.platform != "win32":
        return None

    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_blob = DATA_BLOB()
        in_blob.cbData = len(ciphertext)
        in_blob.pbData = ctypes.cast(ctypes.create_string_buffer(ciphertext), ctypes.POINTER(ctypes.c_byte))

        out_blob = DATA_BLOB()

        success = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        )

        if not success:
            return None

        plain_bytes = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        kernel32.LocalFree(out_blob.pbData)
        return plain_bytes
    except Exception:
        return None


def set_windows_private_acls(target_path: pathlib.Path) -> bool:
    """Restrict file permissions to the current Windows user only using icacls."""
    if sys.platform != "win32" or not target_path.exists():
        return False

    username = os.environ.get("USERNAME")
    if not username:
        return False

    try:
        # 1. Disable inheritance and remove inherited permissions
        # 2. Grant full control explicitly to the current user
        cmd = [
            "icacls",
            str(target_path),
            "/inheritance:r",
            "/grant:r",
            f"{username}:(F)",
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return res.returncode == 0
    except Exception:
        return False


def save_session_credentials(
    workspace_dir: pathlib.Path,
    port: int = 9876,
    token: Optional[str] = None,
) -> Tuple[pathlib.Path, str]:
    """Persist session metadata and token securely in the authorized workspace."""
    workspace_dir = pathlib.Path(workspace_dir).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    session_file = workspace_dir / ".blenderagent_session.json"
    if token is None and session_file.exists():
        existing = load_session_credentials(workspace_dir)
        if existing and existing.get("token") and len(existing["token"]) == 32:
            session_token = existing["token"]
        else:
            session_token = generate_secure_token()
    else:
        session_token = token or generate_secure_token()

    # Encrypt token with DPAPI if available
    token_bytes = session_token.encode("utf-8")
    dpapi_blob = dpapi_protect(token_bytes)
    dpapi_b64 = None
    if dpapi_blob:
        import base64
        dpapi_b64 = base64.b64encode(dpapi_blob).decode("ascii")

    payload: Dict[str, Any] = {
        "version": "0.2.0",
        "port": int(port),
        "token": session_token,
        "token_dpapi": dpapi_b64,
        "workspace": str(workspace_dir).replace("\\", "/"),
        "created_at": time.time(),
        "created_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Write atomically to workspace
    tmp_file = session_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    tmp_file.replace(session_file)

    # Restrict ACLs
    set_windows_private_acls(session_file)

    return session_file, session_token


def load_session_credentials(workspace_dir: Optional[pathlib.Path] = None) -> Optional[Dict[str, Any]]:
    """Retrieve and verify session metadata and token from the global session file or workspace."""
    session_file = None
    if workspace_dir:
        candidate = pathlib.Path(workspace_dir).resolve() / ".blenderagent_session.json"
        if candidate.exists():
            session_file = candidate

    if not session_file and LIVE_SESSION_FILE_PATH.exists():
        session_file = LIVE_SESSION_FILE_PATH

    if not session_file or not session_file.exists():
        return None

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        token = data.get("token")
        dpapi_b64 = data.get("token_dpapi")

        # Attempt DPAPI recovery if available
        if dpapi_b64:
            import base64
            try:
                raw_cipher = base64.b64decode(dpapi_b64)
                decrypted = dpapi_unprotect(raw_cipher)
                if decrypted:
                    token = decrypted.decode("utf-8")
            except Exception:
                pass

        if not token:
            return None

        return {
            "port": int(data.get("port", 9876)),
            "token": token,
            "workspace": pathlib.Path(data.get("workspace", workspace_dir)),
            "created_at": data.get("created_at"),
        }
    except Exception:
        return None
