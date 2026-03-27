"""ClamAV module."""

from __future__ import annotations

from sec_bootstrapper.core.base import module
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="clamav",
    description="Install ClamAV antivirus packages",
    phase="server",
    stage=1,
    dependencies=["system_packages"],
    provides=["clamav_installed"],
)
class ClamAVModule(PackageModule):
    packages = ["clamav"]
