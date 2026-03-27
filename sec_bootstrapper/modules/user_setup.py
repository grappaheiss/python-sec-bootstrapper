"""User setup module - Create non-root user with SSH key workflow."""

from __future__ import annotations

import getpass
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from sec_bootstrapper.core.base import BaseModule, ModuleError, module


@module(
    name="user_setup",
    description="Create non-root user with sudo privileges and SSH key setup",
    phase="server",
    stage=1,
    dependencies=["system_baseline"],
    provides=["nonroot_user", "sudo_access"],
)
class UserSetupModule(BaseModule):
    """
    Module to create a non-root user for operations.
    
    Features:
    - Creates user with home directory
    - Adds user to sudo group
    - Prompts for password (secure input)
    - Sets up SSH directory
    """

    def check(self) -> bool:
        """Check if user already exists."""
        username = self.config.security.ssh.allowed_users[0] if self.config.security.ssh.allowed_users else "chad"
        
        try:
            subprocess.run(
                ["id", username],
                check=True,
                capture_output=True,
            )
            # User exists - check if setup is complete
            user_home = Path(f"/home/{username}")
            ssh_dir = user_home / ".ssh"

            try:
                if user_home.exists() and ssh_dir.exists():
                    self.logger.log(
                        "user_setup",
                        "user_setup",
                        f"User {username} already exists with SSH directory",
                    )
                    return False
            except PermissionError:
                # In restricted test/runtime contexts we may not be able to stat
                # another user's SSH directory; treat as already configured.
                self.logger.log(
                    "user_setup",
                    "user_setup",
                    f"User {username} exists but SSH directory access is restricted",
                )
                return False
            
            return True  # User exists but needs SSH setup
        except subprocess.CalledProcessError:
            return True  # User doesn't exist

    def apply(self) -> None:
        """Create user and configure SSH."""
        username = self.config.security.ssh.allowed_users[0] if self.config.security.ssh.allowed_users else "chad"
        
        self.logger.log("user_setup", "user_setup", f"Starting user setup for {username}")
        
        try:
            # Check if running as root
            if os.geteuid() != 0:
                raise ModuleError(
                    "User setup must be run as root",
                    recovery_steps=["Run with sudo or as root user"],
                )
            
            # Create user if doesn't exist
            if not self._user_exists(username):
                self._create_user(username)
            
            # Add to sudo group
            self._add_to_sudo(username)
            
            # Set password
            self._set_password(username)
            
            # Create SSH directory
            self._create_ssh_directory(username)
            
            self.logger.log("user_setup", "user_setup", f"User {username} configured successfully")
            
        except Exception as e:
            if not isinstance(e, ModuleError):
                raise ModuleError(
                    f"User setup failed: {e}",
                    recovery_steps=[
                        f"Check if user {username} was partially created",
                        f"Run 'id {username}' to verify",
                        f"Check /var/log/auth.log for errors",
                    ],
                )
            raise

    def verify(self) -> bool:
        """Verify user setup is complete."""
        username = self.config.security.ssh.allowed_users[0] if self.config.security.ssh.allowed_users else "chad"
        
        try:
            # Check user exists
            result = subprocess.run(
                ["id", username],
                capture_output=True,
            )
            if result.returncode != 0:
                self.logger.verify("user_setup", f"user_{username}_exists", False)
                return False
            
            # Check sudo membership
            result = subprocess.run(
                ["groups", username],
                capture_output=True,
                text=True,
            )
            if "sudo" not in result.stdout:
                self.logger.verify("user_setup", f"user_{username}_sudo", False)
                return False
            
            # Check SSH directory exists
            user_home = Path(f"/home/{username}")
            ssh_dir = user_home / ".ssh"
            if not ssh_dir.exists():
                self.logger.verify("user_setup", f"user_{username}_ssh_dir", False)
                return False
            
            self.logger.verify("user_setup", f"user_{username}_setup", True)
            return True
            
        except Exception as e:
            self.logger.verify("user_setup", f"user_{username}_setup", False, str(e))
            return False

    def _user_exists(self, username: str) -> bool:
        """Check if user exists."""
        try:
            subprocess.run(
                ["id", username],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _create_user(self, username: str) -> None:
        """Create user with home directory."""
        self.logger.log("user_setup", "user_setup", f"Creating user {username}")
        
        if self.dry_run:
            print(f"[DRY-RUN] Would create user: {username}")
            return
        
        result = self._run_command(
            ["useradd", "-m", "-s", "/bin/bash", username],
            check=True,
        )
        
        self.logger.log("user_setup", "user_setup", f"Created user {username}")

    def _add_to_sudo(self, username: str) -> None:
        """Add user to sudo group."""
        self.logger.log("user_setup", "user_setup", f"Adding {username} to sudo group")
        
        if self.dry_run:
            print(f"[DRY-RUN] Would add {username} to sudo group")
            return
        
        self._run_command(
            ["usermod", "-aG", "sudo", username],
            check=True,
        )
        
        self.logger.log("user_setup", "user_setup", f"Added {username} to sudo group")

    def _set_password(self, username: str) -> None:
        """Set user password."""
        if self.dry_run:
            print(f"[DRY-RUN] Would prompt for password")
            return
        
        # Prompt for password (secure input)
        print(f"\n{'='*60}")
        print(f"Setting password for user: {username}")
        print(f"{'='*60}")
        
        try:
            password = self.config.metadata.get("user_setup_password")
            if not password:
                password = getpass.getpass(f"Enter password for {username}: ")
                confirm = getpass.getpass(f"Confirm password for {username}: ")

                if password != confirm:
                    raise ModuleError(
                        "Passwords do not match",
                        recovery_steps=["Run the module again to set password"],
                    )
            
            if len(password) < 12:
                print("⚠️  Warning: Password is less than 12 characters (recommended minimum)")
            
            # Set password using chpasswd
            proc = subprocess.Popen(
                ["chpasswd"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            proc.communicate(input=f"{username}:{password}\n".encode())
            
            if proc.returncode != 0:
                raise ModuleError("Failed to set password")
            
            print(f"✓ Password set for {username}")
            self.logger.log("user_setup", "user_setup", f"Password set for {username}")
            self.config.metadata.pop("user_setup_password", None)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Password setup cancelled")
            raise ModuleError(
                "Password setup cancelled by user",
                recovery_steps=["Run 'passwd {username}' manually to set password"],
            )

    def _create_ssh_directory(self, username: str) -> None:
        """Create SSH directory for user."""
        user_home = Path(f"/home/{username}")
        ssh_dir = user_home / ".ssh"
        
        self.logger.log("user_setup", "user_setup", f"Creating SSH directory for {username}")
        
        if self.dry_run:
            print(f"[DRY-RUN] Would create {ssh_dir}")
            return
        
        # Create directory
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        
        # Fix ownership
        self._run_command(
            ["chown", "-R", f"{username}:{username}", str(user_home)],
            check=True,
        )
        
        self.logger.log("user_setup", "user_setup", f"Created SSH directory for {username}")

    def _preview_changes(self) -> List[str]:
        """Show what would be done in dry-run mode."""
        username = self.config.security.ssh.allowed_users[0] if self.config.security.ssh.allowed_users else "chad"
        return [
            f"Create user: {username}",
            f"Add {username} to sudo group",
            f"Set password for {username}",
            f"Create /home/{username}/.ssh directory",
        ]

    def _get_changes(self) -> List[str]:
        """Get list of changes made."""
        username = self.config.security.ssh.allowed_users[0] if self.config.security.ssh.allowed_users else "chad"
        return [
            f"Created user: {username}",
            f"Added {username} to sudo group",
            f"Set password for {username}",
            f"Created SSH directory at /home/{username}/.ssh",
        ]
