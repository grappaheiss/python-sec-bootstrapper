"""Stage-2 Docker daemon hardening module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from sec_bootstrapper.core.base import ModuleError, module
from sec_bootstrapper.modules.common import PackageModule


@module(
    name="docker_baseline",
    description="Apply hardened Docker daemon baseline",
    phase="server",
    stage=2,
    dependencies=["system_packages"],
    provides=["docker_hardened"],
)
class DockerBaselineModule(PackageModule):
    packages = ["docker.io"]

    def check(self) -> bool:
        if not self.config.optional.docker or not self.config.docker.enabled:
            return False

        daemon = Path("/etc/docker/daemon.json")
        if not daemon.exists():
            return True

        try:
            data = json.loads(daemon.read_text() or "{}")
        except Exception:
            return True

        expected = self._daemon_policy()
        for key, value in expected.items():
            if data.get(key) != value:
                return True
        return False

    def apply(self) -> None:
        if not self.config.optional.docker or not self.config.docker.enabled:
            return

        self.install_missing()
        daemon = Path("/etc/docker/daemon.json")
        policy = self._daemon_policy()

        if self.dry_run:
            return

        if daemon.exists():
            self._backup_file(daemon)
            current = json.loads(daemon.read_text() or "{}")
        else:
            current = {}

        current.update(policy)
        daemon.parent.mkdir(parents=True, exist_ok=True)
        daemon.write_text(json.dumps(current, indent=2) + "\n")
        self.logger.file_modify(self.name, daemon, "applied hardened daemon baseline")

        result = self._run_command(["systemctl", "restart", "docker"], check=False)
        if result.returncode != 0:
            raise ModuleError("docker daemon restart failed after hardening")

    def verify(self) -> bool:
        if not self.config.optional.docker or not self.config.docker.enabled:
            return True

        daemon = Path("/etc/docker/daemon.json")
        if not daemon.exists():
            return False

        try:
            data = json.loads(daemon.read_text() or "{}")
        except Exception:
            return False

        expected = self._daemon_policy()
        return all(data.get(key) == value for key, value in expected.items())

    def _daemon_policy(self) -> Dict[str, object]:
        return {
            "icc": False,
            "live-restore": True,
            "no-new-privileges": True,
            "log-driver": "json-file",
            "log-opts": {
                "max-size": "10m",
                "max-file": "3",
            },
            "userns-remap": "default" if self.config.docker.userns_remap else "",
        }

    def _preview_changes(self) -> List[str]:
        return [
            "Install docker engine package if missing",
            "Merge hardened policy into /etc/docker/daemon.json",
            "Restart docker daemon",
        ]
