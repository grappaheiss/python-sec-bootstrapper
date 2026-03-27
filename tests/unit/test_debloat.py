"""Unit tests for debloat scanner."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from sec_bootstrapper.core.debloat import DebloatRule, DebloatScanner


def _mock_completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class TestDebloatScanner:
    """Debloat scanner behavior."""

    def test_scan_marks_rule_recommended_when_package_installed(self, mocker):
        rules = [
            DebloatRule(
                key="printing",
                title="Printing (CUPS)",
                rationale="test",
                packages=("cups",),
                services=("cups.service",),
            )
        ]
        scanner = DebloatScanner(rules=rules)

        mocker.patch("sec_bootstrapper.core.debloat.shutil.which", side_effect=lambda cmd: "/bin/x" if cmd in {"dpkg-query", "systemctl"} else None)

        def fake_run(cmd, check=False, capture_output=True, text=True):  # noqa: ARG001
            if cmd[:2] == ["dpkg-query", "-W"]:
                return _mock_completed("cups\nbash\n")
            if cmd[:2] == ["systemctl", "is-enabled"]:
                return _mock_completed("disabled\n", returncode=1)
            if cmd[:2] == ["systemctl", "is-active"]:
                return _mock_completed("inactive\n", returncode=3)
            raise AssertionError(f"unexpected command: {cmd}")

        mocker.patch("sec_bootstrapper.core.debloat.subprocess.run", side_effect=fake_run)

        report = scanner.scan()
        assert report.apt_supported is True
        assert report.systemctl_supported is True
        assert len(report.recommended_findings) == 1
        finding = report.recommended_findings[0]
        assert finding.rule.key == "printing"
        assert finding.installed_packages == ["cups"]

    def test_scan_returns_not_recommended_when_absent(self, mocker):
        rules = [
            DebloatRule(
                key="thunderbolt",
                title="Thunderbolt Service",
                rationale="test",
                packages=("bolt",),
                services=("bolt.service",),
            )
        ]
        scanner = DebloatScanner(rules=rules)

        mocker.patch("sec_bootstrapper.core.debloat.shutil.which", return_value="/bin/x")

        def fake_run(cmd, check=False, capture_output=True, text=True):  # noqa: ARG001
            if cmd[:2] == ["dpkg-query", "-W"]:
                return _mock_completed("bash\ncoreutils\n")
            if cmd[:2] == ["systemctl", "is-enabled"]:
                return _mock_completed("disabled\n", returncode=1)
            if cmd[:2] == ["systemctl", "is-active"]:
                return _mock_completed("inactive\n", returncode=3)
            raise AssertionError(f"unexpected command: {cmd}")

        mocker.patch("sec_bootstrapper.core.debloat.subprocess.run", side_effect=fake_run)
        report = scanner.scan()

        assert len(report.findings) == 1
        assert report.findings[0].recommended is False
        assert report.recommended_findings == []

    def test_scan_handles_missing_dpkg_query(self, mocker):
        scanner = DebloatScanner(
            rules=[
                DebloatRule(
                    key="snmp",
                    title="SNMP",
                    rationale="test",
                    packages=("snmpd",),
                    services=("snmpd.service",),
                )
            ]
        )

        def which_mock(cmd: str):
            if cmd == "dpkg-query":
                return None
            if cmd == "systemctl":
                return "/bin/systemctl"
            return None

        mocker.patch("sec_bootstrapper.core.debloat.shutil.which", side_effect=which_mock)
        mocker.patch(
            "sec_bootstrapper.core.debloat.subprocess.run",
            return_value=_mock_completed("inactive\n", returncode=3),
        )

        report = scanner.scan()
        assert report.apt_supported is False
        assert report.systemctl_supported is True
