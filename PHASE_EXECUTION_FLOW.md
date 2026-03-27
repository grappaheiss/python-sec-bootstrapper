# T-022 Phase Execution Flow

## Stage and Phase Model

- Stage 1: host baseline hardening + Docker prerequisites
- Stage 2: Docker daemon/runtime hardening
- Stage 3: Dockerized AI stack validation and AI framework modules

Each stage can be run in one of two phases:

- `local_prep`: local workstation preparation and key handoff guidance
- `server`: server-side hardening modules

## Phase 1 (Local Prep)

Command:

```bash
sec-bootstrapper run --stage stage1 --phase local_prep
```

Flow:

1. `local_key_prep` ensures local SSH keypair exists.
2. Operator gets explicit key-copy transition guidance:
   - `ssh-copy-id -p <port> <user>@<host>`
3. Operator confirms key copy out-of-band.
4. Server phase starts only after operator transition.

## Phase 2 (Server Hardening)

Command:

```bash
sec-bootstrapper run --stage stage1 --phase server --accept-stage
```

Flow:

1. Stage 1 modules execute in dependency order (including `docker_prereq` when Docker is enabled).
2. On success, stage can be marked `accepted` with `--accept-stage`.
3. Stage 2 is blocked until Stage 1 is accepted.

## Stage-Gate Enforcement

- Attempting Stage 2 before Stage 1 acceptance returns: `stage2 blocked`.
- Attempting Stage 3 before Stage 2 acceptance returns: `stage3 blocked`.
- `stage-status` prints persisted gate status/evidence.

## Docker Validation Progression

1. Stage 2:

```bash
sec-bootstrapper run --stage stage2 --phase server --accept-stage
```

Operator gate:
- CLI asks: `Ready to apply Docker daemon hardening now?`
- If declined, Stage 2 exits without changing daemon config.

2. Stage 3:

```bash
sec-bootstrapper run --stage stage3 --phase server
sec-bootstrapper install-ai --openclaw --opencode
```

Operator gate:
- CLI asks: `Ready to run hardened Docker workload validation now?`
- If declined, Stage 3 exits without starting compose workload.

3. Runtime connectivity proof target:
   - `opencode -> ollama:11434`
   - Compose template and verification plan in `artifacts/docker/SECURE_DOCKER_TEST_IMPL.md`
