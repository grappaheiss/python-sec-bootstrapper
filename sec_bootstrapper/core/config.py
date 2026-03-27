"""Configuration schemas using Pydantic."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ExecutionPhase(str, Enum):
    """Execution phases for hardening."""

    LOCAL_PREP = "local_prep"
    SERVER = "server"


class ExecutionStage(str, Enum):
    """Stage-gated delivery track for T-022."""

    STAGE1 = "stage1"
    STAGE2 = "stage2"
    STAGE3 = "stage3"

    @property
    def stage_number(self) -> int:
        return {
            ExecutionStage.STAGE1: 1,
            ExecutionStage.STAGE2: 2,
            ExecutionStage.STAGE3: 3,
        }[self]


class SSHBootstrapKey(BaseModel):
    """Local bootstrap SSH key spec used in phase=local_prep."""

    name: str = Field(min_length=1)
    key_type: Literal["ed25519", "rsa"] = "ed25519"
    bits: Optional[int] = None
    comment: Optional[str] = None

    @field_validator("bits")
    @classmethod
    def validate_bits(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if value < 2048:
            raise ValueError("RSA key bits must be >= 2048")
        return value


class SSHConfig(BaseModel):
    """SSH hardening configuration."""

    port: int = Field(default=2222, ge=1, le=65535)
    password_auth: bool = False
    root_login: bool = False
    max_auth_tries: int = Field(default=3, ge=1)
    grace_time: int = Field(default=30, ge=1)
    allowed_users: List[str] = Field(default_factory=lambda: ["chad"])
    bootstrap_keys: List[SSHBootstrapKey] = Field(
        default_factory=lambda: [
            SSHBootstrapKey(name="id_ed25519_bootstrap_1", key_type="ed25519"),
            SSHBootstrapKey(name="id_ed25519_bootstrap_2", key_type="ed25519"),
            SSHBootstrapKey(name="id_rsa_bootstrap_1", key_type="rsa", bits=4096),
            SSHBootstrapKey(name="id_rsa_bootstrap_2", key_type="rsa", bits=4096),
        ]
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if v == 22:
            raise ValueError("Port 22 is not recommended for security. Use a non-standard port.")
        return v


class FirewallConfig(BaseModel):
    """Firewall configuration."""

    enabled: bool = True
    ipv6: bool = False
    incoming_policy: Literal["deny", "allow"] = "deny"
    outgoing_policy: Literal["deny", "allow"] = "allow"


class Fail2BanConfig(BaseModel):
    """Fail2Ban jail configuration."""

    enabled: bool = True
    port: int = 2222
    maxretry: int = 3
    bantime: str = "1h"
    findtime: str = "10m"


class AutoUpdateConfig(BaseModel):
    """Automatic update configuration."""

    enabled: bool = True


class SystemConfig(BaseModel):
    """System-level configuration."""

    timezone: str = "UTC"
    entropy_daemon: bool = True


class TailscaleConfig(BaseModel):
    """Tailscale VPN configuration."""

    enabled: bool = True


class DockerConfig(BaseModel):
    """Docker hardening configuration."""

    enabled: bool = True
    userns_remap: bool = True
    gvisor: bool = False
    base_pool_cidr: str = "10.203.55.0/24"
    pool_slice_size: int = 28
    image_cache_root: Path = Field(default=Path("/tools/dockerimages"))
    image_cache_manifest: Path = Field(default=Path("/tools/dockerimages/manifest.json"))
    image_cache_enabled: bool = True
    image_allow_refresh: bool = True
    image_refresh_ttl_hours: int = 24


class OpenClawConfig(BaseModel):
    """OpenClaw AI framework configuration."""

    install_daemon: bool = True
    dev_mode: bool = False


class OpencodeConfig(BaseModel):
    """Opencode AI framework configuration."""

    version: str = "latest"


class ClaudeConfig(BaseModel):
    """Claude Code CLI configuration."""

    method: str = "claude-code"


class VSCodeConfig(BaseModel):
    """VSCode configuration."""

    extensions: List[str] = Field(default_factory=list)


class AIFrameworksConfig(BaseModel):
    """AI frameworks installation configuration."""

    install: Optional[Literal["openclaw", "opencode", "claude", "vscode", "none"]] = "none"
    openclaw: OpenClawConfig = Field(default_factory=OpenClawConfig)
    opencode: OpencodeConfig = Field(default_factory=OpencodeConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    vscode: VSCodeConfig = Field(default_factory=VSCodeConfig)


class SecurityConfig(BaseModel):
    """Security hardening configuration."""

    ssh: SSHConfig = Field(default_factory=SSHConfig)
    firewall: FirewallConfig = Field(default_factory=FirewallConfig)
    fail2ban: Fail2BanConfig = Field(default_factory=Fail2BanConfig)
    auto_updates: AutoUpdateConfig = Field(default_factory=AutoUpdateConfig)


class OptionalFeatures(BaseModel):
    """Optional features configuration."""

    tailscale: bool = True
    docker: bool = True


class TargetConfig(BaseModel):
    """Target server configuration."""

    host: str = "localhost"
    port: int = 22
    user: str = "root"


class ExecutionConfig(BaseModel):
    """Execution configuration."""

    phase: ExecutionPhase = ExecutionPhase.SERVER
    stage: ExecutionStage = ExecutionStage.STAGE1
    dry_run: bool = False
    auto_rollback: bool = True
    log_level: str = "INFO"


class StageGateConfig(BaseModel):
    """Persistent stage gate tracking configuration."""

    state_file: Path = Field(
        default_factory=lambda: Path.home() / ".local" / "state" / "sec_bootstrapper" / "stages.json"
    )


class ToolCacheConfig(BaseModel):
    """Portable /tools artifact cache behavior."""

    cache_root: Path = Field(default=Path("/tools"))
    fallback_root: Path = Field(
        default_factory=lambda: Path.home() / ".cache" / "sec_bootstrapper" / "tools"
    )
    manifest_file: Path = Field(default=Path("config/tools_manifest.yaml"))
    allow_download: bool = True


class ModuleToggleConfig(BaseModel):
    """Optional module toggles."""

    fail2ban: bool = True
    unattended_upgrades: bool = True
    system_hardening: bool = True
    tailscale: bool = True
    dev_runtime_tools: bool = True
    docker_prereq: bool = True
    firejail: bool = True
    clamav: bool = True
    rkhunter: bool = True
    lynis: bool = True
    docker_baseline: bool = True
    docker_ai_validation: bool = True


class Config(BaseModel):
    """Main configuration model."""

    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)
    tailscale: TailscaleConfig = Field(default_factory=TailscaleConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    optional: OptionalFeatures = Field(default_factory=OptionalFeatures)
    ai_frameworks: AIFrameworksConfig = Field(default_factory=AIFrameworksConfig)
    modules: ModuleToggleConfig = Field(default_factory=ModuleToggleConfig)
    stage_gate: StageGateConfig = Field(default_factory=StageGateConfig)
    tool_cache: ToolCacheConfig = Field(default_factory=ToolCacheConfig)
    metadata: Dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        """Load configuration from YAML file."""
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f) or {}
        cfg = cls(**data)
        cfg._normalize_paths()
        return cfg

    @staticmethod
    def _expand_path(path: Path) -> Path:
        raw = os.path.expandvars(os.path.expanduser(str(path)))
        return Path(raw)

    def _normalize_paths(self) -> None:
        self.stage_gate.state_file = self._expand_path(self.stage_gate.state_file)
        self.tool_cache.cache_root = self._expand_path(self.tool_cache.cache_root)
        self.tool_cache.fallback_root = self._expand_path(self.tool_cache.fallback_root)
        self.tool_cache.manifest_file = self._expand_path(self.tool_cache.manifest_file)
        self.docker.image_cache_root = self._expand_path(self.docker.image_cache_root)
        self.docker.image_cache_manifest = self._expand_path(self.docker.image_cache_manifest)

    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        import yaml

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
