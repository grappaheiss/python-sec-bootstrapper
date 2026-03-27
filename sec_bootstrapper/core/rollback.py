"""Rollback and state management for hardening modules."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class BackupEntry:
    """Single backup entry."""

    module_name: str
    original_path: Path
    backup_path: Path
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ModuleState:
    """State snapshot for a module."""

    module_name: str
    backups: List[BackupEntry] = field(default_factory=list)
    files_modified: List[Path] = field(default_factory=list)
    services_restarted: List[str] = field(default_factory=list)
    packages_installed: List[str] = field(default_factory=list)
    packages_removed: List[str] = field(default_factory=list)


class RollbackManager:
    """Manages backups and rollback operations."""

    BACKUP_DIR = Path(
        os.environ.get(
            "SEC_BOOTSTRAPPER_BACKUP_DIR",
            str(Path.home() / ".local" / "state" / "sec_bootstrapper" / "backups"),
        )
    )
    STATE_FILE = Path(
        os.environ.get(
            "SEC_BOOTSTRAPPER_STATE_FILE",
            str(Path.home() / ".local" / "state" / "sec_bootstrapper" / "state.json"),
        )
    )

    def __init__(self, backup_dir: Optional[Path] = None, state_file: Optional[Path] = None):
        self.backup_dir = backup_dir or self.BACKUP_DIR
        self.state_file = state_file or self.STATE_FILE
        self._states: Dict[str, ModuleState] = {}
        self._ensure_dirs()
        self._load_state()

    def _ensure_dirs(self) -> None:
        """Ensure backup directories exist."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            fallback_root = Path("/tmp/sec_bootstrapper")
            self.backup_dir = fallback_root / "backups"
            self.state_file = fallback_root / "state.json"
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def backup_file(self, module_name: str, path: Path) -> Path:
        """
        Create a backup of a file before modification.

        Args:
            module_name: Name of the module making changes
            path: Path to file to backup

        Returns:
            Path to backup file
        """
        if not path.exists():
            raise FileNotFoundError(f"Cannot backup non-existent file: {path}")

        # Create timestamped backup
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{timestamp}_{module_name}_{path.name}"
        backup_path = self.backup_dir / backup_filename

        # Copy file to backup
        shutil.copy2(path, backup_path)

        # Track in state
        if module_name not in self._states:
            self._states[module_name] = ModuleState(module_name=module_name)
        
        entry = BackupEntry(
            module_name=module_name,
            original_path=path,
            backup_path=backup_path,
        )
        self._states[module_name].backups.append(entry)
        self._save_state()

        return backup_path

    def restore_file(self, backup_path: Path, original_path: Optional[Path] = None) -> bool:
        """
        Restore a file from backup.

        Args:
            backup_path: Path to backup file
            original_path: Where to restore (if None, use stored path)

        Returns:
            True if successful
        """
        if not backup_path.exists():
            return False

        # Find original path from state if not provided
        if original_path is None:
            for state in self._states.values():
                for entry in state.backups:
                    if entry.backup_path == backup_path:
                        original_path = entry.original_path
                        break

        if original_path is None:
            return False

        # Ensure parent directory exists
        original_path.parent.mkdir(parents=True, exist_ok=True)

        # Restore file
        shutil.copy2(backup_path, original_path)
        return True

    def rollback_module(self, module_name: str) -> bool:
        """
        Rollback all changes for a module.

        Args:
            module_name: Name of module to rollback

        Returns:
            True if rollback successful
        """
        if module_name not in self._states:
            return True  # Nothing to rollback

        state = self._states[module_name]
        success = True

        # Restore files in reverse order (last modified first)
        for entry in reversed(state.backups):
            if not self.restore_file(entry.backup_path, entry.original_path):
                success = False

        # Mark as rolled back
        if success:
            del self._states[module_name]
            self._save_state()

        return success

    def track_file_modified(self, module_name: str, path: Path) -> None:
        """Track that a module modified a file."""
        if module_name not in self._states:
            self._states[module_name] = ModuleState(module_name=module_name)
        self._states[module_name].files_modified.append(path)
        self._save_state()

    def track_service_restarted(self, module_name: str, service: str) -> None:
        """Track that a module restarted a service."""
        if module_name not in self._states:
            self._states[module_name] = ModuleState(module_name=module_name)
        self._states[module_name].services_restarted.append(service)
        self._save_state()

    def track_packages_installed(self, module_name: str, packages: List[str]) -> None:
        """Track packages installed by a module."""
        if module_name not in self._states:
            self._states[module_name] = ModuleState(module_name=module_name)
        self._states[module_name].packages_installed.extend(packages)
        self._save_state()

    def track_packages_removed(self, module_name: str, packages: List[str]) -> None:
        """Track packages removed by a module."""
        if module_name not in self._states:
            self._states[module_name] = ModuleState(module_name=module_name)
        self._states[module_name].packages_removed.extend(packages)
        self._save_state()

    def get_backups_for_module(self, module_name: str) -> List[str]:
        """Get list of backup paths for a module."""
        if module_name not in self._states:
            return []
        return [str(b.backup_path) for b in self._states[module_name].backups]

    def _save_state(self) -> None:
        """Persist state to disk."""
        data = {}
        for name, state in self._states.items():
            data[name] = {
                "backups": [
                    {
                        "original": str(b.original_path),
                        "backup": str(b.backup_path),
                        "created": b.created_at.isoformat(),
                    }
                    for b in state.backups
                ],
                "files_modified": [str(p) for p in state.files_modified],
                "services_restarted": state.services_restarted,
                "packages_installed": state.packages_installed,
                "packages_removed": state.packages_removed,
            }
        
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_state(self) -> None:
        """Load state from disk."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file) as f:
                data = json.load(f)
            
            for name, state_data in data.items():
                state = ModuleState(module_name=name)
                for b in state_data.get("backups", []):
                    entry = BackupEntry(
                        module_name=name,
                        original_path=Path(b["original"]),
                        backup_path=Path(b["backup"]),
                        created_at=datetime.fromisoformat(b["created"]),
                    )
                    state.backups.append(entry)
                state.files_modified = [Path(p) for p in state_data.get("files_modified", [])]
                state.services_restarted = state_data.get("services_restarted", [])
                state.packages_installed = state_data.get("packages_installed", [])
                state.packages_removed = state_data.get("packages_removed", [])
                self._states[name] = state
        except Exception:
            pass

    def clear_state(self) -> None:
        """Clear all state (use with caution)."""
        self._states.clear()
        if self.state_file.exists():
            self.state_file.unlink()
