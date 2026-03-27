"""System hardening module for timezone and entropy daemon."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from sec_bootstrapper.core.base import module
from sec_bootstrapper.core.distro import DistroDetector, DistroFamily
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="system_hardening",
    description="Set timezone and ensure entropy daemon",
    phase="server",
    stage=1,
    dependencies=["system_baseline"],
    provides=["system_hardened"],
)
class SystemHardeningModule(PackageModule):
    packages = []
    _selected_entropy_package: str | None = None

    def _package_available(self, package: str) -> bool:
        distro = DistroDetector.detect()
        try:
            if distro.family == DistroFamily.DEBIAN:
                result = subprocess.run(
                    ["apt-cache", "policy", package],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return "Candidate: (none)" not in result.stdout
            if distro.family == DistroFamily.REDHAT:
                result = subprocess.run(
                    ["dnf", "list", package],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return result.returncode == 0
        except Exception:
            return False
        return False

    def _entropy_packages(self) -> List[str]:
        distro = DistroDetector.detect()
        if distro.family == DistroFamily.REDHAT:
            candidates = ["haveged", "rng-tools"]
        else:
            candidates = ["haveged", "rng-tools5", "rng-tools"]
        return [pkg for pkg in candidates if self._package_available(pkg)]

    def check(self) -> bool:
        if not self.config.system.entropy_daemon:
            return False
        for pkg in self._entropy_packages():
            if pkg:
                self.packages = [pkg]
                if self.missing_packages():
                    return True
        return False

    def apply(self) -> None:
        if self.config.system.entropy_daemon:
            entropy_packages = self._entropy_packages()
            if entropy_packages:
                # Resolve package manager once and try all candidates in order.
                from sec_bootstrapper.core.distro import get_package_manager

                manager = get_package_manager()
                installed = False
                for pkg in entropy_packages:
                    if manager.is_installed(pkg):
                        self._selected_entropy_package = pkg
                        installed = True
                        break
                    if manager.install([pkg]):
                        self._selected_entropy_package = pkg
                        self.logger.apt_install("system_hardening", [pkg])
                        self.rollback.track_packages_installed("system_hardening", [pkg])
                        installed = True
                        break
                if not installed:
                    self.logger.log(
                        "system_hardening",
                        self.name,
                        f"Entropy packages unavailable/failed: {', '.join(entropy_packages)}; continuing without entropy package",
                    )
            else:
                self.logger.log(
                    "system_hardening",
                    self.name,
                    "No supported entropy package available in current repositories; skipping package install",
                )

        if self.dry_run:
            return

        self._run_command(["timedatectl", "set-timezone", self.config.system.timezone], check=False)
        for service in ["haveged", "rngd"]:
            self._run_command(["systemctl", "enable", "--now", service], check=False)

    def verify(self) -> bool:
        if self.config.system.entropy_daemon:
            if self._selected_entropy_package is None:
                return True
            self.packages = [self._selected_entropy_package]
            if self.missing_packages():
                return False
        return True

    def _preview_changes(self) -> List[str]:
        return [
            f"Set timezone to {self.config.system.timezone}",
            "Install/enable entropy service",
        ]
