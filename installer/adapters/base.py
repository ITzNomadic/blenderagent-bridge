"""Base contract and data structures for AI client MCP adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import pathlib
from typing import Any, Dict, List, Optional


class AdapterStatus(str, Enum):
    NOT_FOUND = "not_found"
    COMPATIBLE = "compatible"
    ALREADY_INSTALLED = "already_installed"
    CONFIGURED = "configured"
    RESTART_REQUIRED = "restart_required"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class AdapterPlan:
    """Action plan prior to applying client configuration modifications."""
    client_name: str
    target_config_file: pathlib.Path
    backup_file: Optional[pathlib.Path]
    action_description: str
    will_modify: bool
    requires_client_restart: bool = True


@dataclass
class AdapterResult:
    """Outcome of an adapter operation."""
    success: bool
    status: AdapterStatus
    message: str
    target_file: Optional[pathlib.Path] = None
    backup_file: Optional[pathlib.Path] = None
    error_code: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class ClientAdapter(ABC):
    """Abstract base class establishing the contract for AI client integrations."""

    @property
    @abstractmethod
    def client_name(self) -> str:
        """Human-readable identifier for the client (e.g. 'Google Antigravity')."""
        pass

    @abstractmethod
    def detect(self) -> AdapterStatus:
        """Inspect system for presence and current registration state."""
        pass

    @abstractmethod
    def plan_install(self, launcher_path: pathlib.Path) -> AdapterPlan:
        """Create a dry-run plan describing changes to be performed."""
        pass

    @abstractmethod
    def backup_config(self) -> Optional[pathlib.Path]:
        """Create an immutable, timestamped backup of the target configuration file."""
        pass

    @abstractmethod
    def install_registration(
        self,
        launcher_path: pathlib.Path,
        workspace_dir: pathlib.Path,
        port: int = 9876,
    ) -> AdapterResult:
        """Safely register the MCP server in the client's configuration."""
        pass

    @abstractmethod
    def verify_registration(self, launcher_path: pathlib.Path) -> bool:
        """Verify that the configuration file contains the correct launcher command."""
        pass

    @abstractmethod
    def verify_runtime(self) -> bool:
        """Check if the client runtime is active and communicating with the server."""
        pass

    @abstractmethod
    def repair(self, launcher_path: pathlib.Path, workspace_dir: pathlib.Path) -> AdapterResult:
        """Reconstruct or heal damaged client registration without affecting foreign servers."""
        pass

    @abstractmethod
    def uninstall_registration(self) -> AdapterResult:
        """Safely remove blenderagent-bridge entry while preserving all other servers."""
        pass
