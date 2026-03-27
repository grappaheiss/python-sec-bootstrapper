"""Firewall module - Configure UFW with security hardening."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from sec_bootstrapper.core.base import BaseModule, ModuleError, module


@module(
    name="firewall",
    description="Configure UFW firewall with security rules and IPv6 disable",
    phase="server",
    stage=1,
    dependencies=["ssh_hardening"],
    provides=["firewall_configured"],
)
class FirewallModule(BaseModule):
    """
    Module to configure UFW firewall.
    
    Security settings:
    - Default deny incoming
    - Default allow outgoing
    - Allow SSH on configured port
    - Disable IPv6 (optional)
    """

    def check(self) -> bool:
        """Check if UFW needs configuration."""
        try:
            # Check if UFW is installed
            result = subprocess.run(
                ["which", "ufw"],
                capture_output=True,
            )
            if result.returncode != 0:
                return True  # UFW not installed
            
            # Check if UFW is enabled
            result = subprocess.run(
                ["ufw", "status"],
                capture_output=True,
                text=True,
            )
            
            if "Status: active" not in result.stdout:
                return True  # UFW not enabled
            
            # Check if SSH port is allowed
            ssh_port = self.config.security.ssh.port
            if str(ssh_port) not in result.stdout and str(ssh_port) + "/tcp" not in result.stdout:
                return True  # SSH port not configured
            
            # Check IPv6 setting
            if not self.config.security.firewall.ipv6:
                ufw_default = Path("/etc/default/ufw")
                if ufw_default.exists():
                    content = ufw_default.read_text()
                    if "IPV6=yes" in content:
                        return True  # IPv6 still enabled
            
            self.logger.log("firewall", "firewall", "Firewall already configured")
            return False
            
        except Exception:
            return True  # Error checking, assume needs config

    def apply(self) -> None:
        """Apply firewall configuration."""
        self.logger.log("firewall", "firewall", "Starting firewall configuration")
        
        try:
            # Install UFW if not present
            self._ensure_ufw_installed()
            
            # Configure defaults
            self._configure_defaults()
            
            # Allow SSH
            self._allow_ssh()
            
            # Disable IPv6 if configured
            self._configure_ipv6()
            
            # Enable firewall
            self._enable_firewall()
            
            self.logger.log("firewall", "firewall", "Firewall configuration complete")
            
        except Exception as e:
            if not isinstance(e, ModuleError):
                raise ModuleError(
                    f"Firewall configuration failed: {e}",
                    recovery_steps=[
                        "Check UFW status: sudo ufw status verbose",
                        "View UFW logs: sudo cat /var/log/ufw.log",
                        "Reset UFW if needed: sudo ufw reset",
                        "Warning: Reset will disable firewall, ensure SSH access first",
                    ],
                )
            raise

    def verify(self) -> bool:
        """Verify firewall is configured correctly."""
        try:
            # Check UFW is active
            result = subprocess.run(
                ["ufw", "status"],
                capture_output=True,
                text=True,
            )
            
            if "Status: active" not in result.stdout:
                self.logger.verify("firewall", "ufw_active", False)
                return False
            
            # Check SSH port is allowed
            ssh_port = self.config.security.ssh.port
            if str(ssh_port) not in result.stdout:
                self.logger.verify("firewall", "ssh_allowed", False)
                return False
            
            self.logger.verify("firewall", "firewall_configured", True)
            return True
            
        except Exception as e:
            self.logger.verify("firewall", "firewall_configured", False, str(e))
            return False

    def _ensure_ufw_installed(self) -> None:
        """Ensure UFW is installed."""
        result = subprocess.run(
            ["which", "ufw"],
            capture_output=True,
        )
        
        if result.returncode == 0:
            return  # Already installed
        
        self.logger.log("firewall", "firewall", "Installing UFW")
        
        if self.dry_run:
            print("[DRY-RUN] Would install UFW")
            return
        
        # Install UFW using package manager
        pkg_manager = get_package_manager()
        if not pkg_manager.install(["ufw"]):
            raise ModuleError("Failed to install UFW")
        
        self.logger.apt_install("firewall", ["ufw"])

    def _configure_defaults(self) -> None:
        """Configure UFW default policies."""
        self.logger.log("firewall", "firewall", "Configuring UFW defaults")
        
        if self.dry_run:
            print("[DRY-RUN] Would configure UFW defaults")
            return
        
        incoming = self.config.security.firewall.incoming_policy
        outgoing = self.config.security.firewall.outgoing_policy
        
        # Set defaults
        self._run_command(["ufw", "default", f"{incoming}", "incoming"], check=True)
        self._run_command(["ufw", "default", f"{outgoing}", "outgoing"], check=True)
        
        self.logger.config_change("firewall", Path("/etc/default/ufw"), f"Set defaults: {incoming}/{outgoing}")

    def _allow_ssh(self) -> None:
        """Allow SSH through firewall."""
        ssh_port = self.config.security.ssh.port
        
        self.logger.log("firewall", "firewall", f"Allowing SSH on port {ssh_port}")
        
        if self.dry_run:
            print(f"[DRY-RUN] Would allow SSH on port {ssh_port}")
            return
        
        self._run_command(
            ["ufw", "allow", f"{ssh_port}/tcp"],
            check=True,
        )
        
        self.logger.config_change(
            "firewall",
            Path("/etc/default/ufw"),
            f"Allowed SSH port {ssh_port}/tcp",
        )

    def _configure_ipv6(self) -> None:
        """Configure IPv6 settings."""
        if self.config.security.firewall.ipv6:
            return  # IPv6 enabled, nothing to do
        
        self.logger.log("firewall", "firewall", "Disabling IPv6")
        
        ufw_default = Path("/etc/default/ufw")
        
        if self.dry_run:
            print(f"[DRY-RUN] Would disable IPv6 in {ufw_default}")
            return
        
        # Backup
        self._backup_file(ufw_default)
        
        # Disable IPv6 in UFW
        content = ufw_default.read_text()
        content = content.replace("IPV6=yes", "IPV6=no")
        ufw_default.write_text(content)
        
        # Also disable in sysctl
        sysctl_conf = Path("/etc/sysctl.conf")
        ipv6_settings = """
# Disable IPv6
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
"""
        
        with open(sysctl_conf, "a") as f:
            f.write(ipv6_settings)
        
        # Apply sysctl settings
        self._run_command(["sysctl", "-p"], check=False)
        
        self.logger.config_change("firewall", ufw_default, "Disabled IPv6")

    def _enable_firewall(self) -> None:
        """Enable UFW firewall."""
        self.logger.log("firewall", "firewall", "Enabling UFW")
        
        if self.dry_run:
            print("[DRY-RUN] Would enable UFW")
            return
        
        # Enable with --force to skip confirmation
        result = self._run_command(
            ["ufw", "--force", "enable"],
            check=False,
        )
        
        if result.returncode != 0:
            raise ModuleError("Failed to enable UFW")
        
        self.logger.service_restart("firewall", "ufw")

    def _preview_changes(self) -> List[str]:
        """Show what would be done."""
        return [
            "Install UFW (if not present)",
            f"Set default policy: {self.config.security.firewall.incoming_policy} incoming",
            f"Set default policy: {self.config.security.firewall.outgoing_policy} outgoing",
            f"Allow SSH on port {self.config.security.ssh.port}",
            f"IPv6: {'enabled' if self.config.security.firewall.ipv6 else 'disabled'}",
            "Enable UFW firewall",
        ]

    def _get_changes(self) -> List[str]:
        """Get list of changes."""
        return [
            "UFW firewall enabled",
            f"SSH allowed on port {self.config.security.ssh.port}",
            f"Default policy: {self.config.security.firewall.incoming_policy} incoming",
            f"IPv6 {'enabled' if self.config.security.firewall.ipv6 else 'disabled'}",
        ]


# Import at end to avoid circular import
from sec_bootstrapper.core.distro import get_package_manager
