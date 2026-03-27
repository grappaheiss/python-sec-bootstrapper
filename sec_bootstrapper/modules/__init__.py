"""Hardening modules package and registration imports."""

from sec_bootstrapper.modules.ai_frameworks import (
    ClaudeModule,
    OpenClawModule,
    OpencodeModule,
    VSCodeModule,
)
from sec_bootstrapper.modules.clamav import ClamAVModule
from sec_bootstrapper.modules.dev_runtime_tools import DevRuntimeToolsModule
from sec_bootstrapper.modules.docker_ai_validation import DockerAIValidationModule
from sec_bootstrapper.modules.docker_baseline import DockerBaselineModule
from sec_bootstrapper.modules.docker_prereq import DockerPrereqModule
from sec_bootstrapper.modules.fail2ban import Fail2BanModule
from sec_bootstrapper.modules.firejail import FirejailModule
from sec_bootstrapper.modules.firewall import FirewallModule
from sec_bootstrapper.modules.local_key_prep import LocalKeyPrepModule
from sec_bootstrapper.modules.lynis import LynisModule
from sec_bootstrapper.modules.rkhunter import RkhunterModule
from sec_bootstrapper.modules.ssh_hardening import SSHHardeningModule
from sec_bootstrapper.modules.system_baseline import SystemBaselineModule
from sec_bootstrapper.modules.system_hardening import SystemHardeningModule
from sec_bootstrapper.modules.system_packages import SystemPackagesModule
from sec_bootstrapper.modules.tailscale import TailscaleModule
from sec_bootstrapper.modules.unattended_upgrades import UnattendedUpgradesModule
from sec_bootstrapper.modules.user_setup import UserSetupModule

__all__ = [
    "SystemBaselineModule",
    "SystemPackagesModule",
    "UserSetupModule",
    "SSHHardeningModule",
    "FirewallModule",
    "Fail2BanModule",
    "UnattendedUpgradesModule",
    "SystemHardeningModule",
    "TailscaleModule",
    "DevRuntimeToolsModule",
    "DockerPrereqModule",
    "FirejailModule",
    "ClamAVModule",
    "RkhunterModule",
    "LynisModule",
    "DockerBaselineModule",
    "DockerAIValidationModule",
    "LocalKeyPrepModule",
    "OpenClawModule",
    "OpencodeModule",
    "ClaudeModule",
    "VSCodeModule",
]
