"""Abstract base class for hardening modules."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypeVar

from sec_bootstrapper.core.manifest import ManifestLogger

if TYPE_CHECKING:
    from sec_bootstrapper.core.config import Config
    from sec_bootstrapper.core.rollback import RollbackManager


class ModuleStatus(str, Enum):
    """Module execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


@dataclass
class ModuleResult:
    """Result of module execution."""

    module_name: str
    status: ModuleStatus
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    backups: List[str] = field(default_factory=list)
    changes: List[str] = field(default_factory=list)
    error: Optional[Exception] = None
    recovery_steps: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.started_at is None:
            self.started_at = datetime.utcnow()

    @property
    def duration(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


T = TypeVar("T", bound="BaseModule")


class BaseModule(ABC):
    """Abstract base class for all hardening modules."""

    name: str = ""
    description: str = ""
    phase: str = "server"  # "local_prep" or "server"
    stage: int = 1
    dependencies: List[str] = []
    provides: List[str] = []

    def __init__(
        self,
        config: Config,
        rollback_manager: RollbackManager,
        dry_run: bool = False,
        logger: Optional[ManifestLogger] = None,
    ):
        self.config = config
        self.rollback = rollback_manager
        self.dry_run = dry_run
        self._status = ModuleStatus.PENDING
        self._result: Optional[ModuleResult] = None
        self.logger = logger or ManifestLogger()

    @abstractmethod
    def check(self) -> bool:
        """
        Check if module needs to be applied.

        Returns:
            True if changes are needed, False if already configured
        """
        pass

    @abstractmethod
    def apply(self) -> None:
        """
        Apply the hardening configuration.

        Raises:
            ModuleError: If application fails (triggers rollback)
        """
        pass

    @abstractmethod
    def verify(self) -> bool:
        """
        Verify that hardening was applied successfully.

        Returns:
            True if verification passes
        """
        pass

    def rollback_changes(self) -> None:
        """
        Rollback changes made by this module.

        Called automatically if apply() fails.
        """
        self.rollback.rollback_module(self.name)

    def run(self) -> ModuleResult:
        """
        Execute the full module lifecycle.

        Returns:
            ModuleResult with status and details
        """
        self._status = ModuleStatus.RUNNING
        result = ModuleResult(module_name=self.name, status=ModuleStatus.RUNNING)

        try:
            self.logger.module_start(self.name)
            # Check if needed
            if not self.check():
                result.status = ModuleStatus.SKIPPED
                result.message = "Already configured, no changes needed"
                return self._complete(result)

            # Apply changes
            if self.dry_run:
                result.message = "Dry run - would apply changes"
                result.changes = self._preview_changes()
            else:
                self.apply()
                result.changes = self._get_changes()
                result.backups = self.rollback.get_backups_for_module(self.name)

            # Verify
            if not self.dry_run and not self.verify():
                raise ModuleError(
                    f"{self.name}: Verification failed after apply",
                    recovery_steps=["Check logs in /var/log/sec_bootstrapper/"],
                )

            result.status = ModuleStatus.SUCCESS
            if not self.dry_run:
                result.message = "Applied successfully"

        except Exception as e:
            result.status = ModuleStatus.FAILED
            result.error = e
            result.message = str(e)
            if isinstance(e, ModuleError):
                result.recovery_steps = e.recovery_steps

            if not self.dry_run:
                # Attempt rollback
                try:
                    self.rollback_changes()
                    result.status = ModuleStatus.ROLLED_BACK
                    result.message += " (rolled back)"
                    self.logger.log("module_rollback", self.name, self.name, result.message)
                except Exception as rollback_error:
                    result.message += f" (rollback failed: {rollback_error})"
                    result.recovery_steps = self._get_recovery_steps()

        return self._complete(result)

    def _complete(self, result: ModuleResult) -> ModuleResult:
        """Finalize result and store it."""
        result.completed_at = datetime.utcnow()
        self._result = result
        self._status = ModuleStatus(result.status)
        self.logger.module_end(self.name, result.status == ModuleStatus.SUCCESS, result.message)
        return result

    def _preview_changes(self) -> List[str]:
        """Return list of changes that would be made (for dry-run)."""
        return ["Dry-run mode - preview not implemented"]

    def _get_changes(self) -> List[str]:
        """Return list of actual changes made."""
        return []

    def _get_recovery_steps(self) -> List[str]:
        """Return manual recovery steps for failed rollback."""
        return [
            f"Check module logs: /var/log/sec_bootstrapper/{self.name}.log",
            f"Review backups in: /var/backups/sec_bootstrapper/",
            "Consult documentation for manual recovery procedures",
        ]

    def _run_command(
        self,
        cmd: List[str],
        check: bool = True,
        capture_output: bool = True,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess:
        """
        Execute a system command.

        Args:
            cmd: Command and arguments as list
            check: Raise exception on non-zero exit
            capture_output: Capture stdout/stderr
            **kwargs: Additional arguments for subprocess.run

        Returns:
            CompletedProcess instance
        """
        if self.dry_run:
            print(f"[DRY-RUN] Would execute: {' '.join(cmd)}")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")

        return subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            **kwargs,
        )

    def _backup_file(self, path: Path) -> Path:
        """Create backup of file before modification."""
        return self.rollback.backup_file(self.name, path)

    @property
    def status(self) -> ModuleStatus:
        """Current module status."""
        return self._status

    @property
    def result(self) -> Optional[ModuleResult]:
        """Execution result."""
        return self._result


class ModuleError(Exception):
    """Exception raised when module application fails."""

    def __init__(
        self,
        message: str,
        recovery_steps: Optional[List[str]] = None,
    ):
        super().__init__(message)
        self.recovery_steps = recovery_steps or []


class ModuleRegistry:
    """Registry for discovering and managing modules."""

    _modules: Dict[str, type[BaseModule]] = {}

    @classmethod
    def register(cls, module_class: type[T]) -> type[T]:
        """Register a module class."""
        cls._modules[module_class.name] = module_class
        return module_class

    @classmethod
    def get(cls, name: str) -> Optional[type[BaseModule]]:
        """Get module class by name."""
        return cls._modules.get(name)

    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered module names."""
        return list(cls._modules.keys())

    @classmethod
    def get_by_phase(cls, phase: str) -> List[type[BaseModule]]:
        """Get all modules for a specific phase."""
        return [m for m in cls._modules.values() if m.phase == phase]

    @classmethod
    def get_by_stage(cls, stage: int, phase: Optional[str] = None) -> List[type[BaseModule]]:
        """Get all modules for a specific stage, optionally filtered by phase."""
        modules = [m for m in cls._modules.values() if m.stage == stage]
        if phase is not None:
            modules = [m for m in modules if m.phase == phase]
        return modules


def module(
    name: str,
    description: str = "",
    phase: str = "server",
    stage: int = 1,
    dependencies: Optional[List[str]] = None,
    provides: Optional[List[str]] = None,
):
    """Decorator to register a module class."""

    def decorator(cls: type[T]) -> type[T]:
        cls.name = name
        cls.description = description
        cls.phase = phase
        cls.stage = stage
        cls.dependencies = dependencies or []
        cls.provides = provides or []
        return ModuleRegistry.register(cls)

    return decorator
