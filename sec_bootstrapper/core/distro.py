"""Distribution detection and package manager abstraction."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from packaging.version import Version


class DistroFamily(Enum):
    """Linux distribution families."""

    DEBIAN = "debian"
    REDHAT = "redhat"
    ARCH = "arch"
    UNKNOWN = "unknown"


@dataclass
class DistroInfo:
    """Distribution information."""

    name: str
    family: DistroFamily
    version: Optional[Version] = None
    codename: str = ""
    id_like: List[str] = field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        """Check if this distro/version is supported."""
        if self.family == DistroFamily.DEBIAN:
            if self.name == "ubuntu":
                return self.version is not None and self.version >= Version("22.04")
            elif self.name in ["debian", "parrot"]:
                return self.version is not None and self.version >= Version("12")
        elif self.family == DistroFamily.REDHAT:
            if self.name == "fedora":
                return self.version is not None and self.version >= Version("38")
        return False


class DistroDetector:
    """Detect Linux distribution and version."""

    @staticmethod
    def detect() -> DistroInfo:
        """Detect current Linux distribution."""
        os_release_path = Path("/etc/os-release")
        
        if not os_release_path.exists():
            return DistroInfo(
                name="unknown",
                family=DistroFamily.UNKNOWN,
                version=None,
            )

        data = DistroDetector._parse_os_release(os_release_path)
        
        name = data.get("ID", "unknown").lower()
        version_str = data.get("VERSION_ID", "").strip('"')
        codename = data.get("VERSION_CODENAME", "").lower()
        id_like = data.get("ID_LIKE", "").lower().split()
        
        # Determine family
        family = DistroDetector._determine_family(name, id_like)
        
        # Parse version
        version = None
        if version_str:
            try:
                version = Version(version_str)
            except Exception:
                pass
        
        return DistroInfo(
            name=name,
            family=family,
            version=version,
            codename=codename,
            id_like=id_like,
        )

    @staticmethod
    def _parse_os_release(path: Path) -> dict:
        """Parse /etc/os-release file."""
        data = {}
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line:
                        key, value = line.split("=", 1)
                        data[key] = value.strip('"')
        except Exception:
            pass
        return data

    @staticmethod
    def _determine_family(name: str, id_like: List[str]) -> DistroFamily:
        """Determine distribution family."""
        debian_family = ["debian", "ubuntu", "linuxmint", "pop", "elementary", "parrot"]
        redhat_family = ["fedora", "rhel", "centos", "rocky", "almalinux"]
        
        if name in debian_family or any(d in debian_family for d in id_like):
            return DistroFamily.DEBIAN
        elif name in redhat_family or any(d in redhat_family for d in id_like):
            return DistroFamily.REDHAT
        elif name in ["arch", "manjaro"] or "arch" in id_like:
            return DistroFamily.ARCH
        
        return DistroFamily.UNKNOWN


class PackageManager:
    """Abstract package manager interface."""

    def __init__(self, distro: DistroInfo):
        self.distro = distro
        self.last_error: str = ""

    @staticmethod
    def _normalize_output(value: object) -> str:
        """Normalize command output payload for human-readable error messages."""
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    def _set_subprocess_error(self, exc: Exception) -> None:
        """Store a concise subprocess error summary for caller diagnostics."""
        if not hasattr(exc, "returncode"):
            self.last_error = str(exc)
            return

        cmd = getattr(exc, "cmd", None)
        cmd_text = " ".join(str(part) for part in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        returncode = getattr(exc, "returncode", "unknown")
        stderr = self._normalize_output(getattr(exc, "stderr", ""))
        stdout = self._normalize_output(getattr(exc, "stdout", ""))
        detail = stderr.strip() or stdout.strip() or str(exc)

        lines = [line.strip() for line in detail.splitlines() if line.strip()]
        tail = " | ".join(lines[-6:]) if lines else detail
        self.last_error = f"{cmd_text} exited with {returncode}: {tail}".strip()

    def update(self) -> bool:
        """Update package lists."""
        raise NotImplementedError

    def upgrade(self) -> bool:
        """Upgrade installed packages."""
        raise NotImplementedError

    def install(self, packages: List[str]) -> bool:
        """Install packages."""
        raise NotImplementedError

    def remove(self, packages: List[str]) -> bool:
        """Remove packages."""
        raise NotImplementedError

    def is_installed(self, package: str) -> bool:
        """Check if package is installed."""
        raise NotImplementedError


class AptPackageManager(PackageManager):
    """APT package manager for Debian-based distros."""

    @staticmethod
    def _apt_env() -> dict:
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        env["APT_LISTCHANGES_FRONTEND"] = "none"
        env["NEEDRESTART_MODE"] = "a"
        return env

    @classmethod
    def _apt_base_args(cls) -> List[str]:
        return [
            "-o",
            "DPkg::Lock::Timeout=120",
            "-o",
            "Dpkg::Options::=--force-confdef",
            "-o",
            "Dpkg::Options::=--force-confold",
        ]

    def update(self) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["apt-get"] + self._apt_base_args() + ["update"],
                check=True,
                capture_output=True,
                env=self._apt_env(),
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def upgrade(self) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["apt-get"] + self._apt_base_args() + ["full-upgrade", "-y"],
                check=True,
                capture_output=True,
                env=self._apt_env(),
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def install(self, packages: List[str]) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["apt-get"] + self._apt_base_args() + ["install", "-y"] + packages,
                check=True,
                capture_output=True,
                env=self._apt_env(),
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def remove(self, packages: List[str]) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["apt-get"] + self._apt_base_args() + ["remove", "-y"] + packages,
                check=True,
                capture_output=True,
                env=self._apt_env(),
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def is_installed(self, package: str) -> bool:
        import subprocess
        try:
            result = subprocess.run(
                ["dpkg", "-l", package],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and "ii" in result.stdout
        except Exception:
            return False


class DnfPackageManager(PackageManager):
    """DNF package manager for Fedora/RHEL-based distros."""

    def update(self) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["dnf", "check-update"],
                check=False,  # check-update returns 100 if updates available
                capture_output=True,
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def upgrade(self) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["dnf", "upgrade", "-y"],
                check=True,
                capture_output=True,
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def install(self, packages: List[str]) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["dnf", "install", "-y"] + packages,
                check=True,
                capture_output=True,
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def remove(self, packages: List[str]) -> bool:
        import subprocess
        try:
            subprocess.run(
                ["dnf", "remove", "-y"] + packages,
                check=True,
                capture_output=True,
            )
            self.last_error = ""
            return True
        except subprocess.CalledProcessError as exc:
            self._set_subprocess_error(exc)
            return False
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def is_installed(self, package: str) -> bool:
        import subprocess
        try:
            result = subprocess.run(
                ["rpm", "-q", package],
                capture_output=True,
            )
            return result.returncode == 0
        except Exception:
            return False


def get_package_manager(distro: Optional[DistroInfo] = None) -> PackageManager:
    """Get appropriate package manager for the system."""
    if distro is None:
        distro = DistroDetector.detect()
    
    if distro.family == DistroFamily.DEBIAN:
        return AptPackageManager(distro)
    elif distro.family == DistroFamily.REDHAT:
        return DnfPackageManager(distro)
    else:
        raise NotImplementedError(f"No package manager for {distro.name}")
