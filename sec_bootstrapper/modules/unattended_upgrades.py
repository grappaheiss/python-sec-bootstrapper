"""Automatic security update module."""

from __future__ import annotations

from pathlib import Path
from typing import List

from sec_bootstrapper.core.base import module
from sec_bootstrapper.core.distro import DistroDetector, DistroFamily
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="unattended_upgrades",
    description="Enable unattended upgrades / dnf-automatic",
    phase="server",
    stage=1,
    dependencies=["system_baseline"],
    provides=["auto_updates_enabled"],
)
class UnattendedUpgradesModule(PackageModule):
    packages = ["unattended-upgrades"]

    def check(self) -> bool:
        if not self.config.security.auto_updates.enabled:
            return False
        distro = DistroDetector.detect()
        if distro.family == DistroFamily.REDHAT:
            return not Path("/etc/dnf/automatic.conf").exists()
        return not Path("/etc/apt/apt.conf.d/20auto-upgrades").exists()

    def apply(self) -> None:
        if not self.config.security.auto_updates.enabled:
            return

        distro = DistroDetector.detect()
        if distro.family == DistroFamily.REDHAT:
            self.packages = ["dnf-automatic"]
            self.install_missing()
            if not self.dry_run:
                self._run_command(["systemctl", "enable", "--now", "dnf-automatic.timer"], check=False)
            return

        self.packages = ["unattended-upgrades"]
        self.install_missing()
        conf_path = Path("/etc/apt/apt.conf.d/20auto-upgrades")
        content = (
            'APT::Periodic::Update-Package-Lists "1";\n'
            'APT::Periodic::Unattended-Upgrade "1";\n'
        )
        if self.dry_run:
            return

        if conf_path.exists():
            self._backup_file(conf_path)
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(content)
        self.logger.file_modify(self.name, conf_path, "enabled unattended upgrades")

    def verify(self) -> bool:
        if not self.config.security.auto_updates.enabled:
            return True
        distro = DistroDetector.detect()
        if distro.family == DistroFamily.REDHAT:
            return Path("/etc/dnf/automatic.conf").exists()
        path = Path("/etc/apt/apt.conf.d/20auto-upgrades")
        return path.exists() and 'Unattended-Upgrade "1"' in path.read_text()

    def _preview_changes(self) -> List[str]:
        return ["Enable distro-appropriate automatic security updates"]
