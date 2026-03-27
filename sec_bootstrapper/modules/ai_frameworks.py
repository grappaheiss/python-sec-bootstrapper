"""AI framework installer modules plus argparse-based selector."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List

from sec_bootstrapper.core.base import BaseModule, module


@dataclass
class AISelection:
    frameworks: List[str]
    vscode_extensions: List[str]


def parse_ai_selection(args: List[str]) -> AISelection:
    """Parse framework selection using argparse flags."""
    parser = argparse.ArgumentParser(prog="sec-bootstrapper install-ai", add_help=False)
    parser.add_argument("--openclaw", action="store_true")
    parser.add_argument("--opencode", action="store_true")
    parser.add_argument("--claude", action="store_true")
    parser.add_argument("--vscode", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--extensions", default="")

    ns, _ = parser.parse_known_args(args)

    frameworks: List[str] = []
    if ns.all:
        frameworks = ["openclaw", "opencode", "claude", "vscode"]
    else:
        if ns.openclaw:
            frameworks.append("openclaw")
        if ns.opencode:
            frameworks.append("opencode")
        if ns.claude:
            frameworks.append("claude")
        if ns.vscode:
            frameworks.append("vscode")

    if not frameworks:
        configured = getattr(ns, "install", None)
        if configured and configured != "none":
            frameworks.append(configured)

    extensions = [x.strip() for x in ns.extensions.split(",") if x.strip()]
    return AISelection(frameworks=frameworks, vscode_extensions=extensions)


class AIFrameworkModule(BaseModule):
    """Base module for AI framework installers."""

    marker_name: str = ""

    def _marker_path(self) -> Path:
        return Path.home() / ".local" / "share" / "sec_bootstrapper" / "ai" / self.marker_name

    def check(self) -> bool:
        return not self._marker_path().exists()

    def apply(self) -> None:
        if self.dry_run:
            return
        marker = self._marker_path()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("installed\n")

    def verify(self) -> bool:
        return self._marker_path().exists() or self.dry_run

    def _preview_changes(self) -> List[str]:
        return [f"Install AI framework module: {self.name}"]


@module(
    name="openclaw",
    description="Install OpenClaw framework",
    phase="server",
    stage=3,
    dependencies=["docker_baseline"],
    provides=["openclaw_ready"],
)
class OpenClawModule(AIFrameworkModule):
    marker_name = "openclaw"


@module(
    name="opencode",
    description="Install Opencode framework",
    phase="server",
    stage=3,
    dependencies=["docker_baseline"],
    provides=["opencode_ready"],
)
class OpencodeModule(AIFrameworkModule):
    marker_name = "opencode"


@module(
    name="claude",
    description="Install Claude framework (Docker-only bridge)",
    phase="server",
    stage=3,
    dependencies=["docker_baseline"],
    provides=["claude_ready"],
)
class ClaudeModule(AIFrameworkModule):
    marker_name = "claude"


@module(
    name="vscode",
    description="Install OpenVSCode framework (Docker-only bridge)",
    phase="server",
    stage=3,
    dependencies=["docker_baseline"],
    provides=["vscode_ready"],
)
class VSCodeModule(AIFrameworkModule):
    marker_name = "vscode"
