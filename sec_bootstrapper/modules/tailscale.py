"""Tailscale module."""

from __future__ import annotations

import shutil
from typing import List

from sec_bootstrapper.core.base import ModuleError, module
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="tailscale",
    description="Install tailscale client",
    phase="server",
    stage=1,
    dependencies=["system_packages"],
    provides=["tailscale_installed"],
)
class TailscaleModule(PackageModule):
    packages = ["tailscale"]

    def check(self) -> bool:
        if not self.config.optional.tailscale or not self.config.tailscale.enabled:
            return False
        return shutil.which("tailscale") is None

    def apply(self) -> None:
        if not self.config.optional.tailscale or not self.config.tailscale.enabled:
            return

        try:
            self.install_missing()
        except Exception as exc:
            raise ModuleError(
                f"tailscale install failed: {exc}",
                recovery_steps=[
                    "Install tailscale repository package per distro docs",
                    "Re-run module after repository is configured",
                ],
            )

    def verify(self) -> bool:
        if not self.config.optional.tailscale or not self.config.tailscale.enabled:
            return True
        return shutil.which("tailscale") is not None

    def _preview_changes(self) -> List[str]:
        return ["Install tailscale package from configured repository"]
