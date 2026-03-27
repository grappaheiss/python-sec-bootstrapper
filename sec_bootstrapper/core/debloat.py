"""Debloat scanner for noisy/non-essential packages and services."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True)
class DebloatRule:
    """Rule describing a potentially unnecessary component."""

    key: str
    title: str
    rationale: str
    packages: Sequence[str]
    services: Sequence[str]


@dataclass(frozen=True)
class DebloatFinding:
    """Scanner output for one rule."""

    rule: DebloatRule
    installed_packages: List[str]
    enabled_services: List[str]
    active_services: List[str]

    @property
    def recommended(self) -> bool:
        return bool(self.installed_packages or self.enabled_services or self.active_services)


@dataclass(frozen=True)
class DebloatReport:
    """Full debloat scan report."""

    findings: List[DebloatFinding]
    apt_supported: bool
    systemctl_supported: bool

    @property
    def recommended_findings(self) -> List[DebloatFinding]:
        return [item for item in self.findings if item.recommended]

    @property
    def recommended_packages(self) -> List[str]:
        packages = {
            pkg
            for item in self.recommended_findings
            for pkg in item.installed_packages
        }
        return sorted(packages)

    @property
    def recommended_services(self) -> List[str]:
        services = {
            svc
            for item in self.recommended_findings
            for svc in (item.enabled_services + item.active_services)
        }
        return sorted(services)


DEFAULT_DEBLOAT_RULES: List[DebloatRule] = [
    DebloatRule(
        key="bluetooth",
        title="Bluetooth Stack",
        rationale="Disable if the host has no Bluetooth use-case.",
        packages=("bluez", "blueman"),
        services=("bluetooth.service",),
    ),
    DebloatRule(
        key="printing",
        title="Printing (CUPS)",
        rationale="Print daemons are unnecessary on most server or security hosts.",
        packages=("cups", "cups-daemon", "cups-browsed"),
        services=("cups.service", "cups-browsed.service"),
    ),
    DebloatRule(
        key="sound",
        title="Desktop Sound Stack",
        rationale="Audio services are usually not needed on hardened server profiles.",
        packages=("pulseaudio", "pipewire", "pipewire-audio"),
        services=("pulseaudio.service", "pipewire.service", "wireplumber.service"),
    ),
    DebloatRule(
        key="thunderbolt",
        title="Thunderbolt Service",
        rationale="Can be removed if no Thunderbolt peripherals are needed.",
        packages=("bolt",),
        services=("bolt.service",),
    ),
    DebloatRule(
        key="snmp",
        title="SNMP Service",
        rationale="SNMP increases exposed attack surface when not explicitly required.",
        packages=("snmpd", "snmp"),
        services=("snmpd.service",),
    ),
    DebloatRule(
        key="nfs",
        title="NFS Components",
        rationale="Remove NFS server/client stack unless file-sharing over NFS is required.",
        packages=("nfs-common", "nfs-kernel-server"),
        services=("nfs-server.service", "nfs-client.target"),
    ),
    DebloatRule(
        key="avahi",
        title="mDNS / Avahi Discovery",
        rationale="Zeroconf discovery is often unnecessary and noisy in secured environments.",
        packages=("avahi-daemon",),
        services=("avahi-daemon.service",),
    ),
    DebloatRule(
        key="rsyslog",
        title="Verbose Syslog Daemon",
        rationale="Consider trimming or replacing if centralized logging is handled elsewhere.",
        packages=("rsyslog",),
        services=("rsyslog.service",),
    ),
]


class DebloatScanner:
    """Scans package/service state and returns debloat recommendations."""

    def __init__(self, rules: Sequence[DebloatRule] | None = None):
        self.rules = list(rules or DEFAULT_DEBLOAT_RULES)

    def scan(self) -> DebloatReport:
        installed = self._installed_packages()
        systemctl_supported = shutil.which("systemctl") is not None
        findings: List[DebloatFinding] = []

        for rule in self.rules:
            installed_pkgs = sorted(pkg for pkg in rule.packages if pkg in installed)
            enabled: List[str] = []
            active: List[str] = []
            for service in rule.services:
                if not systemctl_supported:
                    continue
                if self._is_service_enabled(service):
                    enabled.append(service)
                if self._is_service_active(service):
                    active.append(service)
            findings.append(
                DebloatFinding(
                    rule=rule,
                    installed_packages=installed_pkgs,
                    enabled_services=sorted(enabled),
                    active_services=sorted(active),
                )
            )

        return DebloatReport(
            findings=findings,
            apt_supported=bool(installed),
            systemctl_supported=systemctl_supported,
        )

    def _installed_packages(self) -> set[str]:
        if shutil.which("dpkg-query") is None:
            return set()
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${binary:Package}\n"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    @staticmethod
    def _is_service_enabled(service: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", service],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False
        state = result.stdout.strip().lower()
        return state == "enabled"

    @staticmethod
    def _is_service_active(service: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False
        state = result.stdout.strip().lower()
        return state == "active"
