"""Fail2ban hardening module."""

from __future__ import annotations

from pathlib import Path
from typing import List

from sec_bootstrapper.core.base import ModuleError, module
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="fail2ban",
    description="Install and configure fail2ban sshd jail",
    phase="server",
    stage=1,
    dependencies=["firewall"],
    provides=["fail2ban_enabled"],
)
class Fail2BanModule(PackageModule):
    packages = ["fail2ban"]

    def check(self) -> bool:
        if not self.config.security.fail2ban.enabled:
            return False
        jail_local = Path("/etc/fail2ban/jail.local")
        if not jail_local.exists():
            return True
        return f"port = {self.config.security.fail2ban.port}" not in jail_local.read_text()

    def apply(self) -> None:
        if not self.config.security.fail2ban.enabled:
            return

        self.install_missing()
        cfg = self.config.security.fail2ban
        jail_local = Path("/etc/fail2ban/jail.local")
        content = (
            "[sshd]\n"
            "enabled = true\n"
            f"port = {cfg.port}\n"
            f"maxretry = {cfg.maxretry}\n"
            f"findtime = {cfg.findtime}\n"
            f"bantime = {cfg.bantime}\n"
        )

        if self.dry_run:
            return

        if jail_local.exists():
            self._backup_file(jail_local)
        jail_local.parent.mkdir(parents=True, exist_ok=True)
        jail_local.write_text(content)
        self.logger.file_modify(self.name, jail_local, "wrote fail2ban jail.local")

        result = self._run_command(["systemctl", "enable", "--now", "fail2ban"], check=False)
        if result.returncode != 0:
            raise ModuleError("failed to enable fail2ban service")

    def verify(self) -> bool:
        if not self.config.security.fail2ban.enabled:
            return True
        jail_local = Path("/etc/fail2ban/jail.local")
        return jail_local.exists() and f"port = {self.config.security.fail2ban.port}" in jail_local.read_text()

    def _preview_changes(self) -> List[str]:
        return [
            "Install fail2ban if missing",
            "Write /etc/fail2ban/jail.local with sshd jail settings",
            "Enable fail2ban service",
        ]
