"""Portable /tools cache with manifest-driven integrity/version checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml


@dataclass
class ToolSpec:
    """Single tool artifact definition."""

    name: str
    version: str
    sha256: str
    file: str
    url: str
    version_cmd: str = "{path} --version"


class ToolCacheError(Exception):
    """Tool cache related errors."""


class ToolCacheManager:
    """Resolves tool binaries from cache and downloads only when needed."""

    def __init__(
        self,
        manifest_file: Path,
        cache_root: Path = Path("/tools"),
        fallback_root: Optional[Path] = None,
        allow_download: bool = True,
    ):
        self.manifest_file = manifest_file
        self.cache_root = cache_root
        self.fallback_root = fallback_root or Path.home() / ".cache" / "sec_bootstrapper" / "tools"
        self.allow_download = allow_download
        self.fallback_root.mkdir(parents=True, exist_ok=True)
        self._manifest = self._load_manifest()

    def resolve(self, name: str) -> Path:
        """Return path to a verified tool binary, downloading only if stale/missing."""
        if name not in self._manifest:
            raise ToolCacheError(f"Tool not in manifest: {name}")

        spec = self._manifest[name]
        for root in [self.cache_root, self.fallback_root]:
            candidate = root / spec.file
            if self._is_valid(candidate, spec):
                return candidate

        if not self.allow_download:
            raise ToolCacheError(f"Tool {name} missing or stale and downloads are disabled")

        target = self.fallback_root / spec.file
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(spec.url, target)
        if not self._is_valid(target, spec):
            raise ToolCacheError(f"Downloaded tool failed validation: {name}")
        return target

    def report(self) -> Dict[str, str]:
        """Summarize where each manifest tool resolves from."""
        report: Dict[str, str] = {}
        for name in self._manifest:
            try:
                path = self.resolve(name)
                source = "cache" if str(path).startswith(str(self.cache_root)) else "downloaded"
                report[name] = f"{source}:{path}"
            except Exception as exc:
                report[name] = f"error:{exc}"
        return report

    def _load_manifest(self) -> Dict[str, ToolSpec]:
        if not self.manifest_file.exists():
            return {}

        with open(self.manifest_file) as f:
            raw = yaml.safe_load(f) or {}

        tools = {}
        for name, payload in raw.get("tools", {}).items():
            tools[name] = ToolSpec(
                name=name,
                version=str(payload["version"]),
                sha256=payload["sha256"],
                file=payload["file"],
                url=payload.get("url", ""),
                version_cmd=payload.get("version_cmd", "{path} --version"),
            )
        return tools

    def _is_valid(self, path: Path, spec: ToolSpec) -> bool:
        if not path.exists() or not path.is_file():
            return False

        if spec.sha256 and self._sha256(path) != spec.sha256:
            return False

        if spec.version:
            return self._version_matches(path, spec)

        return True

    def _version_matches(self, path: Path, spec: ToolSpec) -> bool:
        if not spec.version_cmd:
            return True

        cmd = spec.version_cmd.format(path=path)
        try:
            result = subprocess.run(
                ["/bin/bash", "-lc", cmd],
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            return spec.version in output
        except Exception:
            return False

    @staticmethod
    def _sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


def write_tool_cache_report(report_path: Path, report: Dict[str, str]) -> None:
    """Persist tool cache report as JSON."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
