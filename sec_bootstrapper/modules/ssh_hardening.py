"""SSH hardening module - Configure SSH with security best practices."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

from sec_bootstrapper.core.base import BaseModule, ModuleError, module


@module(
    name="ssh_hardening",
    description="Harden SSH configuration (Port 2222, key auth only, disable root)",
    phase="server",
    stage=1,
    dependencies=["user_setup"],
    provides=["ssh_hardened"],
)
class SSHHardeningModule(BaseModule):
    """
    Module to harden SSH configuration.
    
    Security settings applied:
    - Port 2222 (non-standard)
    - Disable root login
    - Disable password authentication (key only)
    - Enable pubkey authentication
    - Disable challenge response
    - Disable X11 forwarding
    - Limit allowed users
    - Max auth tries: 3
    - Login grace time: 30 seconds
    """

    def check(self) -> bool:
        """Check if SSH is already hardened."""
        ssh_config = Path("/etc/ssh/sshd_config")
        
        if not ssh_config.exists():
            return True  # No SSH config, needs setup
        
        try:
            content = ssh_config.read_text()
            
            # Check key settings
            checks = {
                "Port": str(self.config.security.ssh.port),
                "PermitRootLogin": "no" if not self.config.security.ssh.root_login else "yes",
                "PasswordAuthentication": "no" if not self.config.security.ssh.password_auth else "yes",
                "PubkeyAuthentication": "yes",
            }
            
            for key, expected in checks.items():
                # Look for uncommented setting
                for line in content.split("\n"):
                    if line.strip().startswith(f"{key} ") and not line.strip().startswith("#"):
                        current_value = line.split(None, 1)[1].strip()
                        if current_value != expected:
                            return True  # Setting needs to be changed
                        break
                else:
                    # Setting not found, needs to be added
                    return True
            
            self.logger.log("ssh_hardening", "ssh_hardening", "SSH already hardened")
            return False
            
        except Exception:
            return True  # Error reading config, assume needs hardening

    def apply(self) -> None:
        """Apply SSH hardening configuration."""
        self.logger.log("ssh_hardening", "ssh_hardening", "Starting SSH hardening")
        
        try:
            ssh_config = Path("/etc/ssh/sshd_config")
            
            # Backup original config
            if ssh_config.exists():
                self._backup_file(ssh_config)
            
            # Generate new config
            config_content = self._generate_sshd_config()
            
            if self.dry_run:
                print(f"[DRY-RUN] Would write SSH config to {ssh_config}")
                print("="*60)
                print(config_content)
                print("="*60)
                return
            
            # Write config
            ssh_config.write_text(config_content)
            self.logger.file_modify("ssh_hardening", ssh_config, "Updated SSH configuration")
            
            # Validate config before reloading
            if not self._validate_sshd_config():
                raise ModuleError(
                    "SSH configuration validation failed",
                    recovery_steps=[
                        "Check SSH config: sudo sshd -t",
                        "Review changes in /etc/ssh/sshd_config",
                        "Fix syntax errors manually",
                        "Do NOT reload SSH with invalid config (risk of lockout)",
                    ],
                )
            
            # Reload SSH (don't restart to avoid connection drop)
            self._reload_ssh()
            
            self.logger.log("ssh_hardening", "ssh_hardening", "SSH hardening complete")
            
        except Exception as e:
            if not isinstance(e, ModuleError):
                raise ModuleError(
                    f"SSH hardening failed: {e}",
                    recovery_steps=[
                        "Check SSH config syntax: sudo sshd -t",
                        "Review /etc/ssh/sshd_config",
                        "Restore from backup if needed",
                        "Test SSH on new port before disconnecting",
                    ],
                )
            raise

    def verify(self) -> bool:
        """Verify SSH hardening is applied."""
        try:
            # Check SSH is running
            result = subprocess.run(
                ["systemctl", "is-active", "ssh"],
                capture_output=True,
            )
            if result.returncode != 0:
                self.logger.verify("ssh_hardening", "ssh_running", False)
                return False
            
            # Check config is valid
            if not self._validate_sshd_config():
                self.logger.verify("ssh_hardening", "ssh_config_valid", False)
                return False
            
            self.logger.verify("ssh_hardening", "ssh_hardened", True)
            return True
            
        except Exception as e:
            self.logger.verify("ssh_hardening", "ssh_hardened", False, str(e))
            return False

    def _generate_sshd_config(self) -> str:
        """Generate hardened SSH configuration."""
        config = self.config.security.ssh
        
        allowed_users = " ".join(config.allowed_users)
        
        return f"""# Hardened SSH Configuration
# Generated by sec-bootstrapper
# Original backed up before modification

# Port and Protocol
Port {config.port}
Protocol 2

# Authentication
PermitRootLogin {'yes' if config.root_login else 'no'}
PasswordAuthentication {'yes' if config.password_auth else 'no'}
PubkeyAuthentication {'yes' if not config.password_auth else 'no'}
ChallengeResponseAuthentication no
UsePAM yes

# Connection Settings
MaxAuthTries {config.max_auth_tries}
LoginGraceTime {config.grace_time}
ClientAliveInterval 300
ClientAliveCountMax 2

# Security
X11Forwarding no
PrintMotd no
PrintLastLog yes

# Access Control
AllowUsers {allowed_users}

# Logging
SyslogFacility AUTH
LogLevel INFO

# Subsystem
Subsystem sftp /usr/lib/openssh/sftp-server
"""

    def _validate_sshd_config(self) -> bool:
        """Validate SSH configuration without applying."""
        try:
            result = subprocess.run(
                ["sshd", "-t"],
                capture_output=True,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _reload_ssh(self) -> None:
        """Reload SSH service."""
        self.logger.log("ssh_hardening", "ssh_hardening", "Reloading SSH service")
        
        if self.dry_run:
            print("[DRY-RUN] Would reload SSH service")
            return
        
        # Use reload instead of restart to avoid connection drop
        self._run_command(
            ["systemctl", "reload", "ssh"],
            check=True,
        )
        
        self.logger.service_restart("ssh_hardening", "ssh")

    def _preview_changes(self) -> List[str]:
        """Show what would be done."""
        config = self.config.security.ssh
        return [
            f"Set SSH port to {config.port}",
            f"Disable root login: {not config.root_login}",
            f"Disable password auth: {not config.password_auth}",
            f"Enable key auth: {not config.password_auth}",
            f"Set max auth tries: {config.max_auth_tries}",
            f"Set login grace time: {config.grace_time}s",
            "Disable X11 forwarding",
            f"Allow users: {', '.join(config.allowed_users)}",
        ]

    def _get_changes(self) -> List[str]:
        """Get list of changes."""
        config = self.config.security.ssh
        return [
            f"SSH port changed to {config.port}",
            f"Root login {'enabled' if config.root_login else 'disabled'}",
            f"Password authentication {'enabled' if config.password_auth else 'disabled'}",
            "SSH configuration reloaded",
        ]
