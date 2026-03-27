"""Stage-3 Dockerized Ollama + Opencode validation module."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from sec_bootstrapper.core.base import ModuleError, module
from sec_bootstrapper.core.base import BaseModule


@module(
    name="docker_ai_validation",
    description="Validate secure compose and opencode -> ollama:11434 connectivity",
    phase="server",
    stage=3,
    dependencies=["docker_baseline"],
    provides=["docker_ai_stack_validated"],
)
class DockerAIValidationModule(BaseModule):
    """Runs non-destructive validation commands against secure compose template."""

    def check(self) -> bool:
        if not self.config.modules.docker_ai_validation:
            return False
        return True

    def apply(self) -> None:
        compose_file = Path("artifacts/docker/compose.secure-ollama-opencode.yml")
        if not compose_file.exists():
            raise ModuleError(f"missing compose template: {compose_file}")

        if self.dry_run:
            return

        if shutil.which("docker") is None:
            raise ModuleError("docker CLI is not available")

        self._prepare_images(compose_file.parent)

        # Validate compose structure only; does not start workload here.
        cmd = self._compose_config_command(compose_file)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ModuleError(
                f"compose validation failed: {result.stderr.strip() or result.stdout.strip()}",
                recovery_steps=["run compose config manually and inspect template/image accessibility"],
            )

    def verify(self) -> bool:
        return Path("artifacts/docker/SECURE_DOCKER_TEST_IMPL.md").exists()

    def _preview_changes(self) -> List[str]:
        return [
            "Resolve Docker images from cache-first workflow (/tools/dockerimages)",
            "Refresh stale image cache entries per TTL policy",
            "Validate secure Docker compose file",
            "Record operator proof target: opencode -> ollama:11434",
        ]

    def _get_changes(self) -> List[str]:
        return [
            "Image cache policy executed (cache/load/pull/save as needed)",
            "Validated secure compose definition",
            "Ready for runtime stack validation per SECURE_DOCKER_TEST_IMPL.md",
        ]

    def _compose_config_command(self, compose_file: Path) -> List[str]:
        """Build compose config command with v2 preferred and v1 fallback."""
        env_file = compose_file.parent / ".env"
        if self._has_docker_compose_v2():
            cmd = ["docker", "compose"]
            if env_file.exists():
                cmd.extend(["--env-file", str(env_file)])
            cmd.extend(["-f", str(compose_file), "config"])
            return cmd

        docker_compose = shutil.which("docker-compose")
        if docker_compose is None:
            raise ModuleError("docker compose v2 plugin and docker-compose v1 are both unavailable")

        # Compose v1 rejects top-level `name:` key; strip for compatibility.
        compat_file = compose_file.parent / "compose.secure-ollama-opencode.v1.yml"
        if not compat_file.exists():
            lines = compose_file.read_text().splitlines()
            compat_file.write_text("\n".join(line for line in lines if not line.startswith("name:")) + "\n")
        cmd = [docker_compose]
        if env_file.exists():
            cmd.extend(["--env-file", str(env_file)])
        cmd.extend(["-f", str(compat_file), "config"])
        return cmd

    def _has_docker_compose_v2(self) -> bool:
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        return result.returncode == 0

    def _prepare_images(self, compose_dir: Path) -> None:
        if not self.config.docker.image_cache_enabled:
            return

        env = self._load_env(compose_dir / ".env")
        images = {
            "ollama": {
                "primary": env.get("OLLAMA_IMAGE", "ollama/ollama:latest"),
                "fallbacks_csv": env.get("OLLAMA_IMAGE_FALLBACKS", ""),
                "default_fallbacks": [],
            },
            "opencode": {
                "primary": env.get("OPENCODE_IMAGE", "ghcr.io/pilinux/opencode:1.2.15"),
                "fallbacks_csv": env.get("OPENCODE_IMAGE_FALLBACKS", ""),
                "default_fallbacks": [
                    "ghcr.io/opencode-ai/opencode:latest",
                    "docker.io/opencode-ai/opencode:latest",
                    "docker.io/opencodeai/opencode:latest",
                ],
            },
            "claude": {
                "primary": env.get("CLAUDE_IMAGE", "ghcr.io/anthropic-ai/claude-code:latest"),
                "fallbacks_csv": env.get("CLAUDE_IMAGE_FALLBACKS", ""),
                "default_fallbacks": [
                    "docker.io/anthropic-ai/claude-code:latest",
                    "ghcr.io/anthropic/claude-code:latest",
                ],
            },
            "openclaw": {
                "primary": env.get("OPENCLAW_IMAGE", "ghcr.io/openclaw/openclaw:latest"),
                "fallbacks_csv": env.get("OPENCLAW_IMAGE_FALLBACKS", ""),
                "default_fallbacks": ["docker.io/openclaw/openclaw:latest"],
            },
            "openvscode": {
                "primary": env.get("OPENVSCODE_IMAGE", "gitpod/openvscode-server:latest"),
                "fallbacks_csv": env.get("OPENVSCODE_IMAGE_FALLBACKS", ""),
                "default_fallbacks": ["ghcr.io/gitpod-io/openvscode-server:latest"],
            },
            "grype": {
                "primary": env.get(
                    "GRYPE_IMAGE",
                    "anchore/grype:latest",
                ),
                "fallbacks_csv": env.get("GRYPE_IMAGE_FALLBACKS", ""),
                "default_fallbacks": ["ghcr.io/anchore/grype:latest"],
            },
        }

        cache_root = Path(self.config.docker.image_cache_root)
        manifest_path = Path(self.config.docker.image_cache_manifest)
        cache_root.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = self._load_manifest(manifest_path)

        for name, image_config in images.items():
            self._ensure_image_with_fallbacks(
                name=name,
                primary=image_config["primary"],
                fallbacks_csv=image_config["fallbacks_csv"],
                default_fallbacks=image_config["default_fallbacks"],
                cache_root=cache_root,
                manifest=manifest,
                manifest_path=manifest_path,
            )

    def _ensure_image_with_fallbacks(
        self,
        name: str,
        primary: str,
        fallbacks_csv: str,
        default_fallbacks: List[str],
        cache_root: Path,
        manifest: Dict[str, Dict[str, str]],
        manifest_path: Path,
    ) -> None:
        candidates = self._source_chain(primary, fallbacks_csv, default_fallbacks)
        errors: List[str] = []

        for image in candidates:
            try:
                self._ensure_image(name, image, cache_root, manifest, manifest_path)
                if image != primary:
                    self._docker(["tag", image, primary], check=True)
                return
            except ModuleError as exc:
                detail = str(exc).strip() or f"failed candidate {image}"
                errors.append(f"{image}: {detail}")

        raise ModuleError(
            f"docker image resolution failed for {name}; attempted sources: {', '.join(candidates)}",
            recovery_steps=[
                "authenticate to required registries before Stage 3",
                "set explicit mirror chain in .env using *_IMAGE and *_IMAGE_FALLBACKS",
                f"preload image tar artifacts into {cache_root} for offline/cache-first workflows",
                *errors[:3],
            ],
        )

    def _source_chain(self, primary: str, fallbacks_csv: str, default_fallbacks: List[str]) -> List[str]:
        seen: Dict[str, bool] = {}
        chain: List[str] = []

        def add_source(value: str) -> None:
            image = value.strip()
            if not image or image in seen:
                return
            seen[image] = True
            chain.append(image)

        add_source(primary)
        for token in fallbacks_csv.split(","):
            add_source(token)
        for token in default_fallbacks:
            add_source(token)

        return chain

    def _ensure_image(
        self,
        name: str,
        image: str,
        cache_root: Path,
        manifest: Dict[str, Dict[str, str]],
        manifest_path: Path,
    ) -> None:
        tar_path = cache_root / f"{self._safe_name(image)}.tar"

        if not self._image_exists_local(image):
            if tar_path.exists():
                self._docker(["load", "-i", str(tar_path)], check=True)

        should_refresh = self.config.docker.image_allow_refresh and self._refresh_due(image, manifest)
        if self._image_exists_local(image) and not should_refresh:
            return

        if not self.config.docker.image_allow_refresh:
            if self._image_exists_local(image):
                return
            raise ModuleError(
                f"docker image missing and refresh disabled: {image}",
                recovery_steps=[f"preload cache tar at {tar_path} or enable docker.image_allow_refresh"],
            )

        pull = self._docker(["pull", image], check=False)
        if pull.returncode != 0:
            if self._image_exists_local(image):
                return
            raise ModuleError(
                f"docker pull failed for {name} ({image}): {pull.stderr.strip() or pull.stdout.strip()}",
                recovery_steps=[
                    "use digest-pinned image reference in .env",
                    "authenticate to registry if private",
                    f"or preload tar in {cache_root}",
                ],
            )

        self._docker(["save", "-o", str(tar_path), image], check=True)
        digest, created = self._inspect_image(image)
        manifest[image] = {
            "name": name,
            "archive": str(tar_path),
            "digest": digest,
            "created": created,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_manifest(manifest_path, manifest)

    def _refresh_due(self, image: str, manifest: Dict[str, Dict[str, str]]) -> bool:
        ttl = max(0, int(self.config.docker.image_refresh_ttl_hours))
        if ttl == 0:
            return True
        entry = manifest.get(image)
        if not entry or "updated_at" not in entry:
            return True
        try:
            updated_at = datetime.fromisoformat(entry["updated_at"])
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
        except Exception:
            return True
        return datetime.now(timezone.utc) - updated_at >= timedelta(hours=ttl)

    def _image_exists_local(self, image: str) -> bool:
        result = self._docker(["image", "inspect", image], check=False)
        return result.returncode == 0

    def _inspect_image(self, image: str) -> Tuple[str, str]:
        result = self._docker(
            ["image", "inspect", image, "--format", "{{json .RepoDigests}}|{{.Created}}"],
            check=False,
        )
        if result.returncode != 0:
            return "", ""
        raw = result.stdout.strip()
        parts = raw.split("|", 1)
        digest = ""
        created = parts[1] if len(parts) > 1 else ""
        try:
            digests = json.loads(parts[0])
            if digests:
                digest = str(digests[0])
        except Exception:
            digest = ""
        return digest, created

    def _docker(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)

    def _load_env(self, env_file: Path) -> Dict[str, str]:
        env: Dict[str, str] = {}
        if not env_file.exists():
            return env
        for line in env_file.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            env[k.strip()] = v.strip()
        return env

    def _load_manifest(self, path: Path) -> Dict[str, Dict[str, str]]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}

    def _save_manifest(self, path: Path, payload: Dict[str, Dict[str, str]]) -> None:
        path.write_text(json.dumps(payload, indent=2) + "\n")

    @staticmethod
    def _safe_name(image: str) -> str:
        safe = image.replace("/", "_").replace(":", "_").replace("@", "_").replace(".", "_")
        return safe
