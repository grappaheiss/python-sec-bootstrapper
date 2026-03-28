# python-sec-bootstrapper

Linux hardening bootstrapper with staged execution, rollback tracking, Docker baseline hardening, and Stage 3 runtime validation hooks.

Repo name is `python-sec-bootstrapper`.
Python package and CLI name are `sec-bootstrapper`.

## Snapshot

| Item | Value |
|---|---|
| First thing to run | `python3 easy_bootstrap.py --help` |
| Safe demo path | Stage 1 dry-run with `config/config.fast.yaml` |
| Python | `>=3.10` |
| Distros | Ubuntu 22.04+, Debian 12+, Fedora 38+, Parrot |

## What It Does

Three stages:

1. Stage 1 hardens the host.
   SSH, firewall, fail2ban, packages, system baseline, Docker prereqs.
2. Stage 2 hardens the Docker daemon.
3. Stage 3 validates the Docker workload path.

The code is split into modules with a `check -> apply -> verify` lifecycle. Stage gates block later stages until the previous one is accepted.

## Run It

Use a disposable VM first.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 easy_bootstrap.py --help
HOME="$PWD" .venv/bin/python -m sec_bootstrapper.cli.main run \
  --stage stage1 \
  --phase server \
  --dry-run \
  --config config/config.fast.yaml
```

That gives you the CLI contract, then a safe Stage 1 preview.

## Public Proof

Keep the first public proof narrow:

1. Show `easy_bootstrap.py --help`
2. Run Stage 1 dry-run with `config/config.fast.yaml`
3. Point at:
   `MODULE_INVENTORY.md`
   `CONFIG_SCHEMA.md`
   `ROLLBACK_AND_FAILURE_MODEL.md`

Do not present Stage 2 or Stage 3 as public proof unless you have clean environment-specific evidence for them.

## Files That Matter

| Type | Path | Notes |
|---|---|---|
| CLI | `easy_bootstrap.py` | argparse wrapper for the shell bootstrap path |
| CLI | `sec_bootstrapper/cli/main.py` | Typer entrypoint |
| Config | `config/config.yaml` | default config |
| Config | `config/config.fast.yaml` | trimmed first-run profile |
| Config | `config/tools_manifest.yaml` | tool cache manifest |
| Core | `sec_bootstrapper/core/` | config, rollback, stage gate, manifest, cache |
| Modules | `sec_bootstrapper/modules/` | hardening and validation modules |
| Tests | `tests/` | unit and integration coverage |

## Modules

Stage 1:

- `local_key_prep`
- `system_baseline`
- `system_packages`
- `user_setup`
- `ssh_hardening`
- `firewall`
- `fail2ban`
- `unattended_upgrades`
- `system_hardening`
- `tailscale`
- `dev_runtime_tools`
- `docker_prereq`
- `firejail`
- `clamav`
- `rkhunter`
- `lynis`

Stage 2:

- `docker_baseline`

Stage 3:

- `docker_ai_validation`
- `openclaw`, `opencode`, `claude`, `vscode` integration hooks

## Repo Layout

```text
sec_bootstrapper/
  cli/
  core/
  modules/
config/
tests/
easy_bootstrap.py
easy_bootstrap.sh
```

## Verify

```bash
python3 easy_bootstrap.py --help
pytest -q
```

Dry-run path:

```bash
HOME="$PWD" .venv/bin/python -m sec_bootstrapper.cli.main run \
  --stage stage1 \
  --phase server \
  --dry-run \
  --config config/config.fast.yaml
```

## Limits

- Review the config before any live run.
- Stage 2 rewrites Docker daemon policy and restarts Docker.
- Stage 3 can pull images unless you lock it down to cache-only behavior.
- The current public proof is strongest around Stage 1 dry-run and repo structure.
