"""Phase-1 local machine SSH key preparation and handoff guidance."""

from __future__ import annotations

from pathlib import Path
from typing import List

from sec_bootstrapper.core.base import BaseModule, module


@module(
    name="local_key_prep",
    description="Generate local SSH bootstrap keypairs and provide key-copy transition guidance",
    phase="local_prep",
    stage=1,
    dependencies=[],
    provides=["ssh_key_ready", "phase_transition_guidance"],
)
class LocalKeyPrepModule(BaseModule):
    """Build local SSH identity and print explicit transition commands."""

    def check(self) -> bool:
        return any(
            not (Path.home() / ".ssh" / f"{spec.name}.pub").exists()
            for spec in self.config.security.ssh.bootstrap_keys
        )

    def apply(self) -> None:
        ssh_dir = Path.home() / ".ssh"

        if self.dry_run:
            return

        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        for spec in self.config.security.ssh.bootstrap_keys:
            priv = ssh_dir / spec.name
            if priv.exists():
                continue

            cmd = [
                "ssh-keygen",
                "-t",
                spec.key_type,
                "-f",
                str(priv),
                "-N",
                "",
                "-C",
                spec.comment or f"sec-bootstrapper-{spec.name}",
            ]
            if spec.key_type == "rsa":
                cmd.extend(["-b", str(spec.bits or 4096)])
            self._run_command(cmd)

    def verify(self) -> bool:
        for spec in self.config.security.ssh.bootstrap_keys:
            priv_key = Path.home() / ".ssh" / spec.name
            pub_key = Path.home() / ".ssh" / f"{spec.name}.pub"
            if not (priv_key.exists() and pub_key.exists()):
                return False
        return True

    def _preview_changes(self) -> List[str]:
        if not self.config.security.ssh.bootstrap_keys:
            return ["No bootstrap SSH keys configured; nothing to generate"]
        target = self.config.target
        key_names = [spec.name for spec in self.config.security.ssh.bootstrap_keys]
        key_names_csv = ", ".join(key_names)
        key_list = " ".join(key_names)
        remote = f"{target.user}@{target.host}"
        return [
            f"Step 1/6: Ensure 4 keypairs exist in ~/.ssh: {key_names_csv}",
            f"Step 2/6: Show public keys so you can verify them: for k in {key_list}; do echo \"=== $k.pub ===\"; cat ~/.ssh/$k.pub; done",
            f"Step 3/6: Add all public keys to remote authorized_keys: for k in {key_list}; do ssh-copy-id -i ~/.ssh/$k.pub -p {target.port} {remote}; done",
            f"Step 4/6: Pin remote host key locally (avoid MITM prompt): ssh-keyscan -p {target.port} {target.host} >> ~/.ssh/known_hosts",
            "Step 5/6: Add this block to local ~/.ssh/config (mirror script defaults for this host):",
            "Host t022-primary",
            f"    HostName {target.host}",
            f"    User {target.user}",
            f"    Port {target.port}",
            "    IdentityFile ~/.ssh/id_ed25519_bootstrap_1",
            "    IdentitiesOnly yes",
            "    StrictHostKeyChecking yes",
            "    UserKnownHostsFile ~/.ssh/known_hosts",
            "Step 6/6: Test login exactly: ssh t022-primary 'hostname && whoami'",
            "After login succeeds, run Stage 1 server phase.",
        ]

    def _get_changes(self) -> List[str]:
        if not self.config.security.ssh.bootstrap_keys:
            return ["No bootstrap SSH keys configured"]
        target = self.config.target
        key_names = [spec.name for spec in self.config.security.ssh.bootstrap_keys]
        key_list = " ".join(key_names)
        key_names_csv = ", ".join(key_names)
        primary_key = key_names[0]
        remote = f"{target.user}@{target.host}"
        return [
            f"Step 1/7: Keypairs ready in ~/.ssh ({len(key_names)} total): {key_names_csv}",
            f"Step 2/7: Review each public key: for k in {key_list}; do echo \"=== $k.pub ===\"; cat ~/.ssh/$k.pub; done",
            (
                "Step 3/7: Quick single-key setup (primary key): "
                f"ssh-copy-id -i ~/.ssh/{primary_key}.pub -p {target.port} {remote}"
            ),
            (
                "Step 4/7: Install all keys on remote authorized_keys: "
                f"for k in {key_list}; do ssh-copy-id -i ~/.ssh/$k.pub -p {target.port} {remote}; done"
            ),
            (
                "Step 5/7: Pin remote host key in local known_hosts: "
                f"ssh-keyscan -p {target.port} {target.host} >> ~/.ssh/known_hosts"
            ),
            "Step 6/7: Add this host block to local ~/.ssh/config:",
            "Host t022-primary",
            f"    HostName {target.host}",
            f"    User {target.user}",
            f"    Port {target.port}",
            f"    IdentityFile ~/.ssh/{primary_key}",
            "    IdentitiesOnly yes",
            "    StrictHostKeyChecking yes",
            "    UserKnownHostsFile ~/.ssh/known_hosts",
            "Step 7/7: Validate login and then run stage1 server phase: ssh t022-primary 'hostname && whoami'",
        ]
