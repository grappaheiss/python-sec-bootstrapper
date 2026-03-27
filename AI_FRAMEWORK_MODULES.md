# T-022 AI Framework Modules

## Implemented Modules

- `openclaw`
- `opencode`
- `claude`
- `vscode`

All are registered stage-3 modules under `sec_bootstrapper/modules/ai_frameworks.py`.

## Argparse-Based Selection

`install-ai` consumes argparse-style flags:

```bash
sec-bootstrapper install-ai --openclaw --opencode
sec-bootstrapper install-ai --all
sec-bootstrapper install-ai --vscode --extensions python,docker
```

Parser implementation: `parse_ai_selection(args: List[str])`.

## Behavior

- Framework modules currently use marker-based install stubs for safe bootstrap scaffolding.
- Marker path:
  - `~/.local/share/sec_bootstrapper/ai/<framework>`
- This is intentional to support security-first baseline rollout before binding vendor-specific installers.
