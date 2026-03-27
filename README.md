# python-sec-bootstrapper

Staged Linux hardening bootstrapper for SSH, firewall, fail2ban, package baseline, Docker daemon policy, and Dockerized AI runtime validation.

`python-sec-bootstrapper` is the public repo package. The installable Python package and CLI are currently named `sec-bootstrapper`.

## At A Glance

| Item | Value |
|---|---|
| Repo name | `python-sec-bootstrapper` |
| Package name | `sec-bootstrapper` |
| First public proof | Stage 1 dry-run with `config/config.fast.yaml` |
| Main promise | staged host hardening with rollback-aware execution |
| Safety rule | review config before any live host run |

## Why This Exists

Most hardening scripts are either one-shot shell blobs or private ops glue. This project takes a different approach:

- stage-gated execution so Docker hardening does not run before host baseline acceptance
- modular lifecycle (`check -> apply -> verify`) instead of opaque shell side effects
- rollback-aware file mutation with state tracking and manifest logging
- cache-first tooling and image handling so repeated runs do not redownload everything

## Quick Start

Use a disposable VM or lab host first. Do not point the live stages at a production machine until you have reviewed the config and dry-run output.

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

Expected outcome:

- the bridge CLI prints its operator contract
- the stage runner loads the fast profile and previews Stage 1 changes without modifying the host
- no stage-gate acceptance is recorded during dry-run

## What You Are Building

This repo is a staged hardening workflow for Linux hosts that starts with SSH and system baseline controls, then hardens Docker, then validates a containerized AI toolchain path.

| Input | Action | Output |
|---|---|---|
| `config/config.fast.yaml` | run Stage 1 dry-run | preview of SSH, firewall, package, and baseline host changes |
| accepted Stage 1 state | run Stage 2 | Docker daemon hardening with explicit operator confirmation |
| accepted Stage 2 state | run Stage 3 | Dockerized workload validation and AI image/runtime checks |

## Parts Inventory

| Part Type | Name | Exact Spec | Source Path | Required | Notes |
|---|---|---|---|---|---|
| command | `python3` | `>=3.10` | local runtime | yes | base interpreter |
| command | `pip` | installs `requirements.txt` | local runtime | yes | bootstrap dependency path |
| command | `easy_bootstrap.py` | argparse wrapper around `easy_bootstrap.sh` | `easy_bootstrap.py` | yes | easiest operator entrypoint |
| command | `sec-bootstrapper` | Typer CLI exposed by `pyproject.toml` | `sec_bootstrapper/cli/main.py` | yes | direct staged runner |
| file | `config/config.yaml` | default profile | `config/config.yaml` | yes | generic baseline config |
| file | `config/config.fast.yaml` | skips slower scanners | `config/config.fast.yaml` | recommended | best first public demo path |
| file | `config/tools_manifest.yaml` | version and checksum manifest | `config/tools_manifest.yaml` | yes | cache contract |
| module | `stage1` | host hardening baseline | `sec_bootstrapper/modules/` | yes | SSH, firewall, packages, fail2ban |
| module | `stage2` | Docker daemon baseline | `sec_bootstrapper/modules/docker_baseline.py` | yes | asks for confirmation before apply |
| module | `stage3` | Docker AI validation | `sec_bootstrapper/modules/docker_ai_validation.py` | yes | validates runtime path |
| image | mandatory stage3 set | `ollama`, `opencode`, `claude`, `openclaw`, `openvscode`, `grype` | bridge and stage3 flow | conditional | pulled when Stage 3 path is selected |

## Supported Targets

- Ubuntu 22.04+
- Debian 12+
- Fedora 38+
- Parrot

## Public Proof Path

This is the cleanest first proof sequence for a technical stranger:

1. Inspect the operator-facing bridge contract.

```bash
python3 easy_bootstrap.py --help
```

2. Run a safe Stage 1 dry-run using the fast profile.

```bash
HOME="$PWD" .venv/bin/python -m sec_bootstrapper.cli.main run \
  --stage stage1 \
  --phase server \
  --dry-run \
  --config config/config.fast.yaml
```

3. Review the module inventory and config docs before any live run.

- `MODULE_INVENTORY.md`
- `CONFIG_SCHEMA.md`
- `ROLLBACK_AND_FAILURE_MODEL.md`

4. For a first public release, keep the proof path focused on Stage 1 dry-run plus the supporting module and rollback docs.

## Stage Model

- `stage1`
  - `local_prep`: generate bootstrap SSH keys and guide key-copy handoff
  - `server`: apply host hardening modules
- `stage2`
  - `server`: harden the Docker daemon and runtime defaults
- `stage3`
  - `server`: validate Dockerized AI workload path and optional framework hooks

## Implemented Modules

Stage 1 modules:

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

Stage 2 modules:

- `docker_baseline`

Stage 3 modules:

- `docker_ai_validation`
- `openclaw`, `opencode`, `claude`, `vscode` integration hooks

## Repository Layout

```text
sec_bootstrapper/
  cli/main.py
  core/
  modules/
config/
  config.yaml
  config.fast.yaml
  tools_manifest.yaml
tests/
easy_bootstrap.py
easy_bootstrap.sh
```

## Verification

Fast local checks:

```bash
python3 easy_bootstrap.py --help
pytest -q
```

For staged execution, start with:

```bash
HOME="$PWD" .venv/bin/python -m sec_bootstrapper.cli.main run \
  --stage stage1 \
  --phase server \
  --dry-run \
  --config config/config.fast.yaml
```

Recommended reading order for a new visitor:

1. `At A Glance`
2. `Quick Start`
3. `Public Proof Path`
4. `Parts Inventory`
5. `Safety Boundary`

## Safety Boundary

- Treat this as a lab-first tool until you have reviewed every enabled module in your config.
- Stage 2 changes Docker daemon policy and restarts Docker.
- Stage 3 validates container workloads and can pull images unless cache-only policy is configured.
- Public repo packaging excludes live host evidence, machine-local state, private runbooks, and generated stage state.

## Known Gaps

- Stage 2 and Stage 3 require environment-specific operator review before they should be presented as public release evidence.
- No hosted screenshots are included yet; first release should use terminal proof and sanitized config excerpts.
- The current public proof is strongest for Stage 1 dry-run and repo structure, not full production-host validation.
