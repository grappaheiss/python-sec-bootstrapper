"""Stage-1 Docker runtime prerequisite module."""

from __future__ import annotations

import shutil
from typing import List

from sec_bootstrapper.core.base import BaseModule, ModuleError, module
from sec_bootstrapper.core.distro import DistroFamily, get_package_manager


@module(
    name="docker_prereq",
    description="Ensure Docker runtime prerequisites are present during Stage 1",
    phase="server",
    stage=1,
    dependencies=["system_packages"],
    provides=["docker_runtime_ready"],
)
class DockerPrereqModule(BaseModule):
    """Ensures Docker CLI is available before later Docker hardening/validation stages."""

    def check(self) -> bool:
        if not self.config.optional.docker or not self.config.docker.enabled:
            return False
        return shutil.which("docker") is None

    def apply(self) -> None:
        if not self.config.optional.docker or not self.config.docker.enabled:
            return

        if self.dry_run or shutil.which("docker") is not None:
            return

        manager = get_package_manager()
        if not manager.update():
            raise ModuleError("docker_prereq: failed to refresh package metadata")

        candidates = self._candidate_packages(manager.distro.family)
        for package_set in candidates:
            if not manager.install(package_set):
                continue

            installed = [pkg for pkg in package_set if manager.is_installed(pkg)]
            if installed:
                self.logger.apt_update(self.name)
                self.logger.apt_install(self.name, installed)
                self.rollback.track_packages_installed(self.name, installed)

            if shutil.which("docker") is not None:
                return

        raise ModuleError("docker_prereq: failed to install docker runtime prerequisites")

    def verify(self) -> bool:
        if not self.config.optional.docker or not self.config.docker.enabled:
            return True
        return shutil.which("docker") is not None

    def _preview_changes(self) -> List[str]:
        return [
            "Install Docker runtime prerequisite packages if Docker CLI is missing",
            "Verify `docker` binary is available for Stage 2/3",
        ]

    @staticmethod
    def _candidate_packages(family: DistroFamily) -> List[List[str]]:
        if family == DistroFamily.DEBIAN:
            return [
                ["docker.io", "docker-compose-plugin"],
                ["docker.io"],
            ]
        if family == DistroFamily.REDHAT:
            return [
                ["docker", "docker-compose-plugin"],
                ["docker"],
            ]
        return [["docker"]]
