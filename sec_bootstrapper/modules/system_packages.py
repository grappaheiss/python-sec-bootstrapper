"""System packages module - Install essential security packages."""

from __future__ import annotations

import subprocess
from typing import List

from sec_bootstrapper.core.base import BaseModule, ModuleError, module
from sec_bootstrapper.core.distro import get_package_manager


@module(
    name="system_packages",
    description="Install essential security packages (curl, wget, ufw, fail2ban, ca-certificates, gnupg)",
    phase="server",
    stage=1,
    dependencies=["system_baseline"],
    provides=["essential_packages"],
)
class SystemPackagesModule(BaseModule):
    """
    Module to install essential security packages.
    
    Packages installed:
    - curl: HTTP client
    - wget: HTTP/FTP download utility
    - ufw: Uncomplicated Firewall
    - fail2ban: Intrusion prevention
    - ca-certificates: SSL certificates
    - gnupg: GPG encryption/signing
    """

    PACKAGES = ["curl", "wget", "ufw", "fail2ban", "ca-certificates", "gnupg"]
    OPTIONAL_PACKAGES = {"ufw"}

    @staticmethod
    def _ufw_present() -> bool:
        return subprocess.run(["which", "ufw"], capture_output=True).returncode == 0

    def check(self) -> bool:
        """Check if packages are installed."""
        pkg_manager = get_package_manager()
        
        for pkg in self.PACKAGES:
            if pkg == "ufw" and self._ufw_present():
                continue
            if not pkg_manager.is_installed(pkg):
                self.logger.log(
                    "system_packages",
                    "system_packages",
                    f"Package {pkg} not installed",
                )
                return True
        
        self.logger.log("system_packages", "system_packages", "All packages installed")
        return False

    def apply(self) -> None:
        """Install essential packages."""
        self.logger.log("system_packages", "system_packages", "Installing essential packages")
        
        try:
            # Update package lists first
            self.logger.log("system_packages", "system_packages", "Updating package lists")
            
            if not self.dry_run:
                pkg_manager = get_package_manager()
                if not pkg_manager.update():
                    raise ModuleError("Failed to update package lists")
            
            self.logger.apt_update("system_packages")
            
            # Install packages
            packages_to_install = []
            pkg_manager = get_package_manager()
            
            for pkg in self.PACKAGES:
                if pkg == "ufw" and self._ufw_present():
                    continue
                if not pkg_manager.is_installed(pkg):
                    packages_to_install.append(pkg)
            
            if packages_to_install:
                self.logger.log(
                    "system_packages",
                    "system_packages",
                    f"Installing: {', '.join(packages_to_install)}",
                )
                
                installed = []
                failed_required = []
                failed_optional = []

                if not self.dry_run:
                    for pkg in packages_to_install:
                        if pkg_manager.install([pkg]):
                            installed.append(pkg)
                            continue
                        if pkg in self.OPTIONAL_PACKAGES:
                            failed_optional.append(pkg)
                        else:
                            failed_required.append(pkg)

                    if failed_optional:
                        self.logger.log(
                            "system_packages",
                            "system_packages",
                            f"Optional packages unavailable/failed and skipped: {', '.join(failed_optional)}",
                        )

                    if failed_required:
                        raise ModuleError(
                            f"Failed to install required packages: {failed_required}",
                            recovery_steps=[
                                "Check package names are correct",
                                "Run 'apt-get update' manually",
                                "Check /var/log/apt/history.log for errors",
                            ],
                        )
                else:
                    installed = list(packages_to_install)
                
                if installed:
                    self.logger.apt_install("system_packages", installed)
                    self.rollback.track_packages_installed("system_packages", installed)
            
            self.logger.log("system_packages", "system_packages", "Essential packages installed")
            
        except Exception as e:
            if not isinstance(e, ModuleError):
                raise ModuleError(
                    f"System packages installation failed: {e}",
                    recovery_steps=[
                        "Check internet connectivity",
                        "Verify package repositories are accessible",
                        "Run 'apt-get update' and 'apt-get install' manually",
                    ],
                )
            raise

    def verify(self) -> bool:
        """Verify packages are installed."""
        pkg_manager = get_package_manager()
        
        for pkg in self.PACKAGES:
            if pkg == "ufw" and self._ufw_present():
                continue
            if not pkg_manager.is_installed(pkg):
                if pkg in self.OPTIONAL_PACKAGES:
                    continue
                self.logger.verify("system_packages", pkg, False)
                return False
        
        self.logger.verify("system_packages", "essential_packages", True)
        return True

    def _preview_changes(self) -> List[str]:
        """Show what would be installed."""
        pkg_manager = get_package_manager()
        to_install = [pkg for pkg in self.PACKAGES if not pkg_manager.is_installed(pkg)]
        
        if to_install:
            return [f"Install packages: {', '.join(to_install)}"]
        return ["All packages already installed"]

    def _get_changes(self) -> List[str]:
        """Get list of changes."""
        return [f"Installed packages: {', '.join(self.PACKAGES)}"]
