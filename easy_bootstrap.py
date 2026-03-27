#!/usr/bin/env python3
"""Argparse front-end for easy_bootstrap.sh (T-023 contract)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SHELL_RUNNER = SCRIPT_DIR / "easy_bootstrap.sh"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easy_bootstrap.py",
        description=(
            "Argparse entrypoint for T-022 easy bootstrap. "
            "Delegates to easy_bootstrap.sh while preserving bridge/action parity."
        ),
    )

    parser.add_argument("--host", help="Remote server address")
    parser.add_argument("--user", dest="user_name", help="Remote SSH user")
    parser.add_argument("--port", default="22", help="SSH port (default: 22)")
    parser.add_argument("--alias", dest="alias_name", help="SSH alias for ~/.ssh/config")
    parser.add_argument(
        "--user-setup-user",
        dest="user_setup_user",
        help="Non-root user to configure for stage user_setup",
    )
    parser.add_argument(
        "--key-names",
        dest="key_names_csv",
        help="Override bootstrap key names (4 comma-separated values)",
    )
    parser.add_argument(
        "--stage-config",
        default="config/config.local.yaml",
        help="Config file for stage execution",
    )
    parser.add_argument(
        "--ai-images",
        dest="ai_images_csv",
        help=(
            "Optional image list; mandatory defaults "
            "ollama,opencode,claude,openclaw,openvscode,grype are always included"
        ),
    )
    parser.add_argument("--docker-script", help="Follow-on Docker hardening script path")
    parser.add_argument("--compose-file", help="Compose file for image pull bridge")
    parser.add_argument("--compose-env-file", help="Optional env-file for compose bridge")

    parser.add_argument("--debloat", action="store_true", help="Run debloat recommendation scan")
    parser.add_argument("--no-debloat", action="store_true", help="Skip debloat recommendation scan")
    parser.add_argument("--run-stage1", action="store_true", help="Run sec-bootstrapper stage1")
    parser.add_argument("--run-docker-hardening", action="store_true", help="Run sec-bootstrapper stage2")
    parser.add_argument("--run-stage3", action="store_true", help="Run sec-bootstrapper stage3")
    parser.add_argument("--run-pipeline", action="store_true", help="Run stage1 -> stage2 -> stage3")
    parser.add_argument("--run-docker-script", action="store_true", help="Run Docker hardening script bridge")
    parser.add_argument("--install-ai-images", action="store_true", help="Pull AI images via compose bridge")
    parser.add_argument("--gui", action="store_true", help="Enable GUI checklist mode")
    parser.add_argument("--no-gui", action="store_true", help="Disable GUI checklist mode")
    parser.add_argument("--gen-keys", action="store_true", help="Always generate bootstrap keys")
    parser.add_argument("--no-gen-keys", action="store_true", help="Never generate bootstrap keys")
    parser.add_argument("--skip-remote", action="store_true", help="Skip remote ssh-keyscan/ssh-copy-id steps")
    parser.add_argument("--yes", action="store_true", help="Non-interactive mode")
    parser.add_argument(
        "--print-shell-args",
        action="store_true",
        help="Print delegated easy_bootstrap.sh argument list and exit",
    )

    return parser


def to_shell_args(ns: argparse.Namespace) -> list[str]:
    args: list[str] = []

    def add_opt(flag: str, value: str | None) -> None:
        if value is not None and value != "":
            args.extend([flag, value])

    add_opt("--host", ns.host)
    add_opt("--user", ns.user_name)
    add_opt("--port", ns.port)
    add_opt("--alias", ns.alias_name)
    add_opt("--user-setup-user", ns.user_setup_user)
    add_opt("--key-names", ns.key_names_csv)
    add_opt("--stage-config", ns.stage_config)
    add_opt("--ai-images", ns.ai_images_csv)
    add_opt("--docker-script", ns.docker_script)
    add_opt("--compose-file", ns.compose_file)
    add_opt("--compose-env-file", ns.compose_env_file)

    bool_flags = [
        (ns.debloat, "--debloat"),
        (ns.no_debloat, "--no-debloat"),
        (ns.run_stage1, "--run-stage1"),
        (ns.run_docker_hardening, "--run-docker-hardening"),
        (ns.run_stage3, "--run-stage3"),
        (ns.run_pipeline, "--run-pipeline"),
        (ns.run_docker_script, "--run-docker-script"),
        (ns.install_ai_images, "--install-ai-images"),
        (ns.gui, "--gui"),
        (ns.no_gui, "--no-gui"),
        (ns.gen_keys, "--gen-keys"),
        (ns.no_gen_keys, "--no-gen-keys"),
        (ns.skip_remote, "--skip-remote"),
        (ns.yes, "--yes"),
    ]
    for enabled, flag in bool_flags:
        if enabled:
            args.append(flag)

    return args


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    if not SHELL_RUNNER.exists():
        parser.error(f"Bootstrap runner not found: {SHELL_RUNNER}")

    delegated_args = to_shell_args(ns)
    if ns.print_shell_args:
        print(" ".join(delegated_args))
        return 0

    cmd = [str(SHELL_RUNNER), *delegated_args]
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
