"""JSONL manifest logging system."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Union


class LogAction(str, Enum):
    """Types of actions to log."""

    MODULE_START = "module_start"
    MODULE_END = "module_end"
    MODULE_ERROR = "module_error"
    MODULE_ROLLBACK = "module_rollback"
    APT_UPDATE = "apt_update"
    APT_UPGRADE = "apt_upgrade"
    APT_INSTALL = "apt_install"
    APT_REMOVE = "apt_remove"
    FILE_BACKUP = "file_backup"
    FILE_MODIFY = "file_modify"
    FILE_RESTORE = "file_restore"
    SERVICE_RESTART = "service_restart"
    CONFIG_CHANGE = "config_change"
    PACKAGE_BUILD = "package_build"
    VERIFY_SUCCESS = "verify_success"
    VERIFY_FAILURE = "verify_failure"


@dataclass
class LogEntry:
    """Single manifest log entry."""

    timestamp: str
    action: str
    module: str
    name: str
    detail: str
    metadata: Dict[str, Any]

    def to_json(self) -> str:
        """Convert to JSON string."""
        data = {
            "timestamp": self.timestamp,
            "action": self.action,
            "module": self.module,
            "name": self.name,
            "detail": self.detail,
            "metadata": self.metadata,
        }
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, line: str) -> LogEntry:
        """Parse from JSON string."""
        data = json.loads(line)
        return cls(
            timestamp=data["timestamp"],
            action=data["action"],
            module=data["module"],
            name=data["name"],
            detail=data["detail"],
            metadata=data.get("metadata", {}),
        )


class ManifestLogger:
    """JSONL manifest logger for tracking all hardening actions."""

    DEFAULT_LOG_FILE = Path(
        os.environ.get(
            "SEC_BOOTSTRAPPER_LOG_FILE",
            str(Path.home() / ".local" / "state" / "sec_bootstrapper" / "manifest.jsonl"),
        )
    )

    def __init__(self, log_file: Optional[Path] = None, skip_ensure_dir: bool = False):
        self.log_file = log_file or self.DEFAULT_LOG_FILE
        if not skip_ensure_dir:
            self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure log directory exists."""
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback = Path("/tmp/sec_bootstrapper/manifest.jsonl")
            fallback.parent.mkdir(parents=True, exist_ok=True)
            self.log_file = fallback

    def _escape_json(self, value: str) -> str:
        """Escape string for JSON."""
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def log(
        self,
        action: Union[LogAction, str],
        module: str,
        name: str,
        detail: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log an action to the manifest.

        Args:
            action: Type of action performed
            module: Module performing the action
            name: Name of the item affected
            detail: Additional details
            metadata: Optional metadata dictionary
        """
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            action=action.value if isinstance(action, LogAction) else action,
            module=module,
            name=name,
            detail=detail,
            metadata=metadata or {},
        )

        with open(self.log_file, "a") as f:
            f.write(entry.to_json() + "\n")

    def module_start(self, module: str) -> None:
        """Log module start."""
        self.log(LogAction.MODULE_START, module, module, "Module execution started")

    def module_end(self, module: str, success: bool, message: str = "") -> None:
        """Log module completion."""
        action = LogAction.MODULE_END if success else LogAction.MODULE_ERROR
        self.log(action, module, module, message, {"success": success})

    def apt_update(self, module: str) -> None:
        """Log apt update."""
        self.log(LogAction.APT_UPDATE, module, "system", "apt-get update")

    def apt_upgrade(self, module: str) -> None:
        """Log apt upgrade."""
        self.log(LogAction.APT_UPGRADE, module, "system", "apt-get full-upgrade -y")

    def apt_install(self, module: str, packages: list) -> None:
        """Log apt package installation."""
        for pkg in packages:
            self.log(LogAction.APT_INSTALL, module, pkg, f"installed via {module}")

    def apt_remove(self, module: str, packages: list) -> None:
        """Log apt package removal."""
        for pkg in packages:
            self.log(LogAction.APT_REMOVE, module, pkg, f"removed via {module}")

    def file_backup(self, module: str, original: Path, backup: Path) -> None:
        """Log file backup."""
        self.log(
            LogAction.FILE_BACKUP,
            module,
            str(original),
            f"backed up to {backup}",
            {"backup_path": str(backup)},
        )

    def file_modify(self, module: str, path: Path, description: str = "") -> None:
        """Log file modification."""
        self.log(LogAction.FILE_MODIFY, module, str(path), description)

    def file_restore(self, module: str, backup: Path, original: Path) -> None:
        """Log file restore."""
        self.log(
            LogAction.FILE_RESTORE,
            module,
            str(original),
            f"restored from {backup}",
        )

    def service_restart(self, module: str, service: str) -> None:
        """Log service restart."""
        self.log(LogAction.SERVICE_RESTART, module, service, f"systemctl restart {service}")

    def config_change(self, module: str, config_file: Path, changes: str) -> None:
        """Log configuration change."""
        self.log(LogAction.CONFIG_CHANGE, module, str(config_file), changes)

    def package_build(self, module: str, package: str, build_dir: Path) -> None:
        """Log package build from source."""
        self.log(
            LogAction.PACKAGE_BUILD,
            module,
            package,
            f"built from source in {build_dir}",
            {"build_dir": str(build_dir)},
        )

    def verify(self, module: str, item: str, success: bool, details: str = "") -> None:
        """Log verification result."""
        action = LogAction.VERIFY_SUCCESS if success else LogAction.VERIFY_FAILURE
        self.log(action, module, item, details, {"success": success})

    def read_entries(self) -> list:
        """Read all log entries."""
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(LogEntry.from_json(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def get_module_entries(self, module: str) -> list:
        """Get all entries for a specific module."""
        return [e for e in self.read_entries() if e.module == module]

    def get_last_run(self) -> Optional[datetime]:
        """Get timestamp of last logged action."""
        entries = self.read_entries()
        if not entries:
            return None
        return datetime.fromisoformat(entries[-1].timestamp)

    def clear(self) -> None:
        """Clear the log file (use with caution)."""
        if self.log_file.exists():
            self.log_file.unlink()
