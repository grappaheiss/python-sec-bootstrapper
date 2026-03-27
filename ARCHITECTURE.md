# T-022 Architecture

## Overview

`sec_bootstrapper` is a modular Python hardening framework with explicit staged execution and persistent stage gates.

- CLI layer: `sec_bootstrapper/cli/main.py` (Typer commands for `init`, `run`, `install-ai`, `stage-status`, `list-modules`)
- Core layer:
  - `core/base.py`: module lifecycle (`check/apply/verify`), registry, dependency metadata
  - `core/config.py`: `config.yaml` schema (execution, security, docker, stage gate, tool cache)
  - `core/stage_gate.py`: Stage 1 -> Stage 2 -> Stage 3 gate enforcement and persistence
  - `core/tool_cache.py`: `/tools`-first artifact resolution, checksum/version verification, download-on-miss
  - `core/rollback.py`: backup/state tracking and rollback restore operations
  - `core/manifest.py`: JSONL execution trail
- Module layer: one class per control area under `sec_bootstrapper/modules/`

## Module Lifecycle Contract

Each module implements:

1. `check()` to decide if work is needed.
2. `apply()` to execute privileged/system changes.
3. `verify()` to confirm the expected security outcome.

Runtime behavior in `BaseModule.run()`:

1. Log `module_start`
2. `check`
3. `apply` (or dry-run preview)
4. `verify`
5. On failure: attempt rollback + return recovery steps
6. Log `module_end`

## Orchestration Model

- Modules are registered by decorator metadata: `name`, `phase`, `stage`, `dependencies`, `provides`.
- Execution plan is stage-filtered and dependency-sorted (topological order).
- Stage gate rules:
  - Stage 1 has no prerequisite.
  - Stage 2 requires Stage 1 `accepted`.
  - Stage 3 requires Stage 2 `accepted`.

## Security Boundaries

- Privileged host mutations are concentrated in module `apply()` implementations.
- File backups are created before modifying sensitive files (`sshd_config`, `daemon.json`, fail2ban/ufw configs).
- Rollback manager tracks installed packages and backup artifacts.
- Tool cache integrity check requires manifest SHA256 + version command match.

## AI Framework Selection

- `install-ai` uses argparse-style flags through `parse_ai_selection()`:
  - `--openclaw --opencode --claude --vscode --all --extensions`
- Selected frameworks map to registered modules (`openclaw`, `opencode`, `claude`, `vscode`).
