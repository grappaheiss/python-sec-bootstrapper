# T-022 Rollback and Failure Model

## Rollback Strategy

- File backup before mutation via `RollbackManager.backup_file()`.
- Backups and state persist under:
  - `~/.local/state/sec_bootstrapper/backups` (default)
  - `~/.local/state/sec_bootstrapper/state.json` (default)
- On module failure, `BaseModule.run()` triggers `rollback_module(module_name)`.

## Failure States

- `failed`: module check/apply/verify error.
- `rolled_back`: failure occurred and rollback completed.
- `skipped`: module reported no work needed.

## Stage-Level Failure Handling

- If any module in a stage returns `failed`/`rolled_back`, stage state is marked `failed`.
- Stage 2 and 3 remain blocked until prerequisite stage is marked `accepted`.

## Recovery Artifacts

- Module recovery steps are returned from `ModuleError.recovery_steps`.
- Manifest entries are written to JSONL (`manifest.jsonl`) for audit.
- Tool cache report persisted to `artifacts/tool_cache_report.json` per run.
