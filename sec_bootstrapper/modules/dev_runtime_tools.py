"""Install developer/runtime toolchain."""

from __future__ import annotations

import shutil
from typing import List

from pathlib import Path

from sec_bootstrapper.core.base import ModuleError, module
from sec_bootstrapper.core.distro import DistroDetector, DistroFamily
from sec_bootstrapper.core.distro import get_package_manager
from sec_bootstrapper.core.tool_cache import ToolCacheManager
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="dev_runtime_tools",
    description="Install python/pip/venv, npm, git, and gost",
    phase="server",
    stage=1,
    dependencies=["system_baseline"],
    provides=["runtime_tools"],
)
class DevRuntimeToolsModule(PackageModule):
    packages = []
    _gost_name = "gost"

    def _tool_packages(self) -> List[str]:
        distro = DistroDetector.detect()
        if distro.family == DistroFamily.REDHAT:
            return ["python3", "python3-pip", "nodejs", "npm", "git", "gost"]
        return ["python3", "python3-pip", "python3-venv", "nodejs", "npm", "git", "gost"]

    def _has_gost(self) -> bool:
        return shutil.which(self._gost_name) is not None

    def _tool_cache(self) -> ToolCacheManager:
        return ToolCacheManager(
            manifest_file=Path(self.config.tool_cache.manifest_file),
            cache_root=Path(self.config.tool_cache.cache_root),
            fallback_root=Path(self.config.tool_cache.fallback_root),
            allow_download=self.config.tool_cache.allow_download,
        )

    def _ensure_gost(self) -> None:
        if self._has_gost():
            return

        # First try cache-managed binary resolution.
        try:
            cached = self._tool_cache().resolve(self._gost_name)
            if self.dry_run:
                return
            self._run_command(["install", "-m", "0755", str(cached), "/usr/local/bin/gost"])
            self.logger.log(self.name, self.name, f"Installed gost from cache: {cached}")
            return
        except Exception:
            # Fall back to package manager path below.
            pass

        if self.dry_run:
            return

        manager = get_package_manager()
        if not manager.install(["gost"]):
            raise ModuleError(
                f"{self.name}: failed to install gost from package manager and no valid cache artifact found"
            )
        self.logger.apt_install(self.name, ["gost"])
        self.rollback.track_packages_installed(self.name, ["gost"])

    def check(self) -> bool:
        self.packages = self._tool_packages()
        return bool(self.missing_packages()) or (not self._has_gost())

    def apply(self) -> None:
        self.packages = self._tool_packages()
        self.install_missing()
        self._ensure_gost()

    def verify(self) -> bool:
        self.packages = self._tool_packages()
        return (not self.missing_packages()) and self._has_gost()

    def _preview_changes(self) -> List[str]:
        self.packages = self._tool_packages()
        missing = self.missing_packages()
        changes: List[str] = []
        if missing:
            changes.append(f"Install runtime toolchain packages: {', '.join(missing)}")
        if not self._has_gost():
            changes.append("Ensure gost available (package manager first, /tools cache fallback)")
        if changes:
            return changes
        if not missing:
            return ["runtime toolchain already present"]
        return ["runtime toolchain already present"]
