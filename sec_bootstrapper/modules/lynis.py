"""Lynis module."""

from __future__ import annotations

import subprocess

from sec_bootstrapper.core.base import module
from sec_bootstrapper.core.distro import DistroDetector, DistroFamily
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="lynis",
    description="Install Lynis auditing tool",
    phase="server",
    stage=1,
    dependencies=["system_packages"],
    provides=["lynis_installed"],
)
class LynisModule(PackageModule):
    packages = ["lynis"]

    def _package_available(self) -> bool:
        distro = DistroDetector.detect()
        try:
            if distro.family == DistroFamily.DEBIAN:
                result = subprocess.run(
                    ["apt-cache", "policy", "lynis"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return "Candidate: (none)" not in result.stdout
            if distro.family == DistroFamily.REDHAT:
                result = subprocess.run(
                    ["dnf", "list", "lynis"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return result.returncode == 0
        except Exception:
            return False
        return False

    def check(self) -> bool:
        if not self._package_available():
            return False
        return super().check()

    def apply(self) -> None:
        if not self._package_available():
            self.logger.log(
                "lynis",
                self.name,
                "lynis package unavailable in current repositories; skipping",
            )
            return
        super().apply()

    def verify(self) -> bool:
        if not self._package_available():
            return True
        return super().verify()
