"""Shared helpers for package-oriented modules."""

from __future__ import annotations

from typing import Iterable, List

from sec_bootstrapper.core.base import BaseModule, ModuleError
from sec_bootstrapper.core.distro import get_package_manager


class PackageModule(BaseModule):
    """Base for modules that ensure package presence."""

    packages: List[str] = []

    def missing_packages(self) -> List[str]:
        manager = get_package_manager()
        return [pkg for pkg in self.packages if not manager.is_installed(pkg)]

    def check(self) -> bool:
        return bool(self.missing_packages())

    def apply(self) -> None:
        if self.dry_run:
            return
        self.install_missing()

    def install_missing(self) -> None:
        missing = self.missing_packages()
        if not missing:
            return

        manager = get_package_manager()
        if not manager.update():
            error_detail = getattr(manager, "last_error", "").strip()
            message = f"{self.name}: failed to refresh package metadata"
            if error_detail:
                message = f"{message}: {error_detail}"
            raise ModuleError(message)
        if not manager.install(missing):
            error_detail = getattr(manager, "last_error", "").strip()
            message = f"{self.name}: failed to install {', '.join(missing)}"
            if error_detail:
                message = f"{message}: {error_detail}"
            raise ModuleError(message)

        self.logger.apt_update(self.name)
        self.logger.apt_install(self.name, missing)
        self.rollback.track_packages_installed(self.name, missing)

    def verify(self) -> bool:
        return not self.missing_packages()

    def _preview_changes(self) -> List[str]:
        missing = self.missing_packages()
        if not missing:
            return ["No package changes required"]
        return [f"Install packages: {', '.join(missing)}"]

    def _get_changes(self) -> List[str]:
        missing = self.missing_packages()
        if not missing:
            return ["No package changes required"]
        return [f"Installed packages: {', '.join(missing)}"]
