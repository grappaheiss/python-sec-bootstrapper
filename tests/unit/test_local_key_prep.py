"""Unit tests for local_key_prep multi-key bootstrap behavior."""

from pathlib import Path
from unittest.mock import MagicMock

from sec_bootstrapper.core.config import Config
from sec_bootstrapper.modules.local_key_prep import LocalKeyPrepModule


def _build_module(config: Config, tmp_path: Path) -> LocalKeyPrepModule:
    rollback = MagicMock()
    rollback.get_backups_for_module.return_value = []
    module = LocalKeyPrepModule(
        config=config,
        rollback_manager=rollback,
        dry_run=False,
    )
    return module


def test_default_bootstrap_key_inventory() -> None:
    config = Config()
    keys = config.security.ssh.bootstrap_keys

    assert len(keys) == 4
    assert [k.key_type for k in keys].count("ed25519") == 2
    assert [k.key_type for k in keys].count("rsa") == 2


def test_apply_generates_expected_keygen_commands(monkeypatch, tmp_path: Path) -> None:
    config = Config()
    module = _build_module(config, tmp_path)

    # Force ~/.ssh path into temporary test home.
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0)

    module._run_command = fake_run  # type: ignore[assignment]
    module.apply()

    assert len(calls) == 4
    # Ensure RSA keys include explicit bits and ED keys do not.
    rsa_calls = [c for c in calls if c[c.index("-t") + 1] == "rsa"]
    ed_calls = [c for c in calls if c[c.index("-t") + 1] == "ed25519"]
    assert len(rsa_calls) == 2
    assert len(ed_calls) == 2
    for cmd in rsa_calls:
        assert "-b" in cmd
        assert "4096" in cmd
    for cmd in ed_calls:
        assert "-b" not in cmd


def test_verify_requires_all_keypairs(monkeypatch, tmp_path: Path) -> None:
    config = Config()
    module = _build_module(config, tmp_path)

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    # Create only one keypair: verify should fail.
    first = config.security.ssh.bootstrap_keys[0].name
    (ssh_dir / first).write_text("priv")
    (ssh_dir / f"{first}.pub").write_text("pub")
    assert module.verify() is False

    # Create all remaining keypairs: verify should pass.
    for spec in config.security.ssh.bootstrap_keys[1:]:
        (ssh_dir / spec.name).write_text("priv")
        (ssh_dir / f"{spec.name}.pub").write_text("pub")
    assert module.verify() is True
