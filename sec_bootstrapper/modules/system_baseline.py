"""System baseline module - apt update and upgrade."""

from __future__ import annotations

import subprocess
from typing import List

from sec_bootstrapper.core.base import BaseModule, ModuleError, module
from sec_bootstrapper.core.distro import DistroDetector, DistroFamily, get_package_manager


@module(
    name="system_baseline",
    description="Update package lists and upgrade installed packages",
    phase="server",
    stage=1,
    dependencies=[],
    provides=["updated_packages"],
)
class SystemBaselineModule(BaseModule):
    """
    Module to update package lists and upgrade all installed packages.
    
    This should be the first module run to ensure all subsequent
    installations have access to the latest packages.
    """

    def check(self) -> bool:
        """Check if update is needed by comparing package lists."""
        # Always update to ensure latest packages
        # In a real implementation, we might check apt cache age
        return True

    def apply(self) -> None:
        """Apply system updates."""
        self.logger.log("system_baseline", "system_baseline", "Starting system baseline update")
        
        try:
            # Get appropriate package manager for current distro
            pkg_manager = get_package_manager()
            
            # Update package lists
            self.logger.log("system_baseline", "system_baseline", "Updating package lists")
            if not self.dry_run:
                result = pkg_manager.update()
                if not result:
                    error_detail = getattr(pkg_manager, "last_error", "").strip()
                    message = "Failed to update package lists"
                    if error_detail:
                        message = f"{message}: {error_detail}"
                    raise ModuleError(
                        message,
                        recovery_steps=[
                            "Check internet connectivity",
                            "Run 'apt-get update' manually to see errors",
                            "Check /etc/apt/sources.list for invalid entries",
                        ],
                    )
            
            self.logger.apt_update("system_baseline")
            
            # Upgrade installed packages
            self.logger.log("system_baseline", "system_baseline", "Upgrading installed packages")
            if not self.dry_run:
                result = pkg_manager.upgrade()
                if not result:
                    error_detail = getattr(pkg_manager, "last_error", "").strip()
                    message = "Failed to upgrade packages"
                    if error_detail:
                        message = f"{message}: {error_detail}"
                    raise ModuleError(
                        message,
                        recovery_steps=[
                            "Check for broken packages with 'dpkg --audit'",
                            "Run 'apt --fix-broken install'",
                            "Check disk space with 'df -h'",
                        ],
                    )
            
            self.logger.apt_upgrade("system_baseline")
            
        except Exception as e:
            if not isinstance(e, ModuleError):
                raise ModuleError(
                    f"System baseline update failed: {e}",
                    recovery_steps=[
                        "Check system logs: journalctl -xe",
                        "Verify network connectivity",
                        "Check apt configuration",
                    ],
                )
            raise

    def verify(self) -> bool:
        """Verify that packages are up to date."""
        try:
            distro = DistroDetector.detect()
            if distro.family == DistroFamily.REDHAT:
                result = subprocess.run(
                    ["dnf", "check-update"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                # dnf returns 100 when updates are available.
                is_up_to_date = result.returncode in (0,)
            else:
                result = subprocess.run(
                    ["apt", "list", "--upgradable"],
                    capture_output=True,
                    text=True,
                )
                upgradable = [
                    line for line in result.stdout.split("\n") if line and not line.startswith("Listing")
                ]
                is_up_to_date = len(upgradable) == 0

            if not is_up_to_date:
                self.logger.verify(
                    "system_baseline",
                    "packages_up_to_date",
                    False,
                    "updates still available",
                )
                return False
            
            self.logger.verify(
                "system_baseline",
                "packages_up_to_date",
                True,
                "All packages are up to date",
            )
            return True
            
        except Exception as e:
            self.logger.verify(
                "system_baseline",
                "packages_up_to_date",
                False,
                f"Verification failed: {e}",
            )
            return False

    def _preview_changes(self) -> List[str]:
        """Show what would be done in dry-run mode."""
        return [
            "Update package lists",
            "Upgrade all installed packages",
        ]

    def _get_changes(self) -> List[str]:
        """Get list of changes made."""
        return [
            "Package lists updated",
            "Installed packages upgraded",
        ]
