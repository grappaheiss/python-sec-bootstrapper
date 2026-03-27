"""Firejail module."""

from __future__ import annotations

from sec_bootstrapper.core.base import module
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="firejail",
    description="Install firejail sandbox tool",
    phase="server",
    stage=1,
    dependencies=["system_packages"],
    provides=["firejail_installed"],
)
class FirejailModule(PackageModule):
    packages = ["firejail"]
