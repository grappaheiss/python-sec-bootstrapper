"""CLI entry point using Typer."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sec_bootstrapper.core.base import BaseModule, ModuleRegistry
from sec_bootstrapper.core.config import Config, ExecutionPhase, ExecutionStage
from sec_bootstrapper.core.debloat import DebloatScanner
from sec_bootstrapper.core.rollback import RollbackManager
from sec_bootstrapper.core.stage_gate import StageGateManager
from sec_bootstrapper.core.tool_cache import ToolCacheManager, write_tool_cache_report
from sec_bootstrapper.modules.ai_frameworks import parse_ai_selection

app = typer.Typer(
    name="sec-bootstrapper",
    help="Modular Linux Security Hardening CLI",
    rich_markup_mode="rich",
)

console = Console()


def _default_config_path() -> Path:
    return Path.home() / ".config" / "sec_bootstrapper" / "config.yaml"


def _topological_order(modules: List[type[BaseModule]]) -> List[type[BaseModule]]:
    by_name: Dict[str, type[BaseModule]] = {m.name: m for m in modules}
    visited: set[str] = set()
    temp: set[str] = set()
    order: List[type[BaseModule]] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in temp:
            raise RuntimeError(f"circular dependency detected at {name}")

        temp.add(name)
        mod = by_name[name]
        for dep in mod.dependencies:
            if dep in by_name:
                visit(dep)
        temp.remove(name)
        visited.add(name)
        order.append(mod)

    for mod_name in sorted(by_name):
        visit(mod_name)

    return order


def _load_config(config_path: Optional[Path]) -> Config:
    path = config_path or _default_config_path()
    if not path.exists():
        console.print(f"[red]Config file not found: {path}[/red]")
        console.print("[dim]Run 'sec-bootstrapper init' to create a configuration file.[/dim]")
        raise typer.Exit(1)

    try:
        return Config.from_yaml(path)
    except Exception as exc:
        console.print(f"[red]Error loading config: {exc}[/red]")
        raise typer.Exit(1)


def _module_enabled(config: Config, module_name: str) -> bool:
    """Return whether a module is enabled by config toggle, defaulting to True."""
    toggles = config.modules
    if hasattr(toggles, module_name):
        return bool(getattr(toggles, module_name))
    return True


def _confirm_stage_readiness(stage: ExecutionStage, phase: ExecutionPhase) -> None:
    """Require explicit operator confirmation for high-impact stage actions."""
    if phase != ExecutionPhase.SERVER:
        return

    if stage == ExecutionStage.STAGE2:
        proceed = typer.confirm(
            "Ready to apply Docker daemon hardening now? "
            "(This backs up daemon config, writes secure policy, and restarts Docker. "
            "Remaining full-install step after this: Stage 3 runtime validation.)"
        )
        if not proceed:
            console.print("[yellow]Stage 2 canceled by operator. No Docker daemon changes were made.[/yellow]")
            raise typer.Exit()

    if stage == ExecutionStage.STAGE3:
        proceed = typer.confirm(
            "Ready to run hardened Docker workload validation now? "
            "(This validates Docker workload path for final handoff evidence. "
            "If this passes, remaining step is security/acceptance review.)"
        )
        if not proceed:
            console.print("[yellow]Stage 3 canceled by operator. No compose workload was started.[/yellow]")
            raise typer.Exit()


def _plan_has(modules_to_run: List[type[BaseModule]], module_name: str) -> bool:
    return any(mod.name == module_name for mod in modules_to_run)


def _print_stage_bridge(stage: ExecutionStage, phase: ExecutionPhase, modules_to_run: List[type[BaseModule]]) -> None:
    """Print sequence reminders so operators know what remains."""
    if phase != ExecutionPhase.SERVER:
        return

    if stage == ExecutionStage.STAGE1 and _plan_has(modules_to_run, "docker_prereq"):
        console.print(
            Panel(
                "Docker bridge reminder:\n"
                "1) This step prepares initial Docker runtime/tools.\n"
                "2) Remaining step: run Stage 2 to harden Docker daemon policy.\n"
                "3) Remaining step: run Stage 3 to validate compose workload connectivity.",
                title="Remaining Steps",
                border_style="yellow",
            )
        )

    if stage == ExecutionStage.STAGE2 and _plan_has(modules_to_run, "docker_baseline"):
        console.print(
            Panel(
                "Docker hardening step:\n"
                "1) This step applies secure daemon policy.\n"
                "2) Remaining step: run Stage 3 for workload validation.\n"
                "3) Target proof: opencode -> ollama:11434 connectivity.",
                title="Remaining Steps",
                border_style="yellow",
            )
        )

    if stage == ExecutionStage.STAGE3 and _plan_has(modules_to_run, "docker_ai_validation"):
        console.print(
            Panel(
                "Final runtime validation step:\n"
                "1) Validate secure compose path for Ollama + Opencode.\n"
                "2) Capture health/connectivity evidence for handoff.\n"
                "3) If successful, proceed to security review/closure.",
                title="Remaining Steps",
                border_style="yellow",
            )
        )


def _apply_interactive_overrides(
    config: Config,
    modules_to_run: List[type[BaseModule]],
    dry_run: bool,
    interactive_prompts: bool,
) -> None:
    """Apply optional interactive overrides for runtime-sensitive inputs."""
    if dry_run or not interactive_prompts:
        return

    module_names = {mod.name for mod in modules_to_run}

    if "user_setup" in module_names:
        default_username = (
            config.security.ssh.allowed_users[0] if config.security.ssh.allowed_users else "chad"
        )
        username = typer.prompt(
            "Non-root username to configure",
            default=default_username,
            show_default=True,
        ).strip()
        if not username:
            console.print("[red]Username cannot be empty.[/red]")
            raise typer.Exit(1)
        config.security.ssh.allowed_users = [username]

        password = typer.prompt(
            f"Password for {username}",
            hide_input=True,
            confirmation_prompt=True,
        )
        config.metadata["user_setup_password"] = password

    if "local_key_prep" in module_names and config.security.ssh.bootstrap_keys:
        console.print("[dim]Configure bootstrap SSH key filenames (leave defaults to keep current names).[/dim]")
        for idx, spec in enumerate(config.security.ssh.bootstrap_keys, start=1):
            key_name = typer.prompt(
                f"Bootstrap key {idx} filename",
                default=spec.name,
                show_default=True,
            ).strip()
            if not key_name:
                console.print("[red]Key filename cannot be empty.[/red]")
                raise typer.Exit(1)
            spec.name = key_name


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
):
    """Sec Bootstrapper - Harden Linux hosts and Docker runtime in controlled stages."""


@app.command()
def init(
    config_path: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to save configuration file",
    ),
):
    """Initialize configuration file."""
    console.print(Panel.fit("[bold blue]Sec Bootstrapper - Initialize Configuration[/bold blue]"))

    config_path = config_path or _default_config_path()
    if config_path.exists() and not typer.confirm(f"Config file exists at {config_path}. Overwrite?"):
        raise typer.Exit()

    config = Config()
    config.to_yaml(config_path)
    console.print(f"[green]✓ Configuration created at {config_path}[/green]")


@app.command("run")
def run_hardening(
    stage: ExecutionStage = typer.Option(ExecutionStage.STAGE1, "--stage", help="Execution stage"),
    phase: ExecutionPhase = typer.Option(ExecutionPhase.SERVER, "--phase", help="Execution phase"),
    module: Optional[str] = typer.Option(None, "--module", "-m", help="Run single module"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to configuration file"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview changes only"),
    interactive_prompts: bool = typer.Option(
        True,
        "--interactive-prompts/--no-interactive-prompts",
        help="Prompt for runtime values such as username/password and key names",
    ),
    accept_stage: bool = typer.Option(
        False,
        "--accept-stage",
        help="Mark stage accepted when all modules succeed",
    ),
):
    """Run staged hardening modules."""
    console.print(Panel.fit("[bold blue]Sec Bootstrapper - Running Hardening[/bold blue]"))

    # Ensure decorators run and registry is populated.
    import sec_bootstrapper.modules  # noqa: F401

    config = _load_config(config_path)
    config.execution.stage = stage
    config.execution.phase = phase
    config.execution.dry_run = dry_run

    gate = StageGateManager(config.stage_gate.state_file)
    allowed, reason = gate.can_run(stage.value)
    if not allowed:
        console.print(f"[red]{reason}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Stage gate: {reason}[/dim]")

    cache_manager = ToolCacheManager(
        manifest_file=Path(config.tool_cache.manifest_file),
        cache_root=Path(config.tool_cache.cache_root),
        fallback_root=Path(config.tool_cache.fallback_root),
        allow_download=config.tool_cache.allow_download,
    )
    report = cache_manager.report()
    write_tool_cache_report(
        Path("artifacts/tool_cache_report.json"),
        report,
    )

    if module:
        mod_class = ModuleRegistry.get(module)
        if not mod_class:
            console.print(f"[red]Unknown module: {module}[/red]")
            raise typer.Exit(1)
        modules_to_run = [mod_class]
    else:
        modules_to_run = ModuleRegistry.get_by_stage(stage.stage_number, phase=phase.value)

    modules_to_run = [m for m in modules_to_run if _module_enabled(config, m.name)]

    if not modules_to_run:
        console.print(f"[yellow]No modules found for stage={stage.value}, phase={phase.value}[/yellow]")
        raise typer.Exit()

    modules_to_run = _topological_order(modules_to_run)
    _apply_interactive_overrides(config, modules_to_run, dry_run=dry_run, interactive_prompts=interactive_prompts)

    table = Table(title=f"Execution Plan ({stage.value} / {phase.value})")
    table.add_column("Module", style="cyan")
    table.add_column("Stage", style="magenta")
    table.add_column("Description", style="green")
    table.add_column("Dependencies", style="yellow")

    for mod_class in modules_to_run:
        deps = ", ".join(mod_class.dependencies) if mod_class.dependencies else "None"
        table.add_row(mod_class.name, str(mod_class.stage), mod_class.description, deps)
    console.print(table)
    _print_stage_bridge(stage, phase, modules_to_run)

    if dry_run:
        console.print("[yellow]⚡ DRY-RUN MODE: no changes will be made[/yellow]")

    if not dry_run and phase == ExecutionPhase.SERVER and not typer.confirm(
        "This will modify system configuration. Continue?"
    ):
        raise typer.Exit()
    if not dry_run:
        _confirm_stage_readiness(stage, phase)

    rollback = RollbackManager()
    results = []

    for mod_class in modules_to_run:
        start_ts = time.time()
        console.print(f"[blue]→ Running {mod_class.name}...[/blue]")
        mod_instance = mod_class(config=config, rollback_manager=rollback, dry_run=dry_run)
        result = mod_instance.run()
        results.append(result)
        elapsed = time.time() - start_ts

        if result.status.value == "success":
            console.print(f"[green]✓ {mod_class.name}: {result.message} ({elapsed:.1f}s)[/green]")
            for change in result.changes:
                console.print(f"  [dim]- {change}[/dim]")
        elif result.status.value == "skipped":
            console.print(f"[dim]⊘ {mod_class.name}: {result.message} ({elapsed:.1f}s)[/dim]")
        else:
            console.print(f"[red]✗ {mod_class.name}: {result.message} ({elapsed:.1f}s)[/red]")
            for step in result.recovery_steps:
                console.print(f"  [dim]- {step}[/dim]")

    failed = [r for r in results if r.status.value in {"failed", "rolled_back"}]
    if failed:
        if not dry_run:
            gate.mark(stage.value, "failed", evidence=f"failed_modules={','.join(r.module_name for r in failed)}")
            console.print("[red]Stage execution failed; gate marked failed.[/red]")
        else:
            console.print("[red]Stage execution failed during dry-run; gate state unchanged.[/red]")
        raise typer.Exit(1)

    if dry_run:
        console.print(f"[yellow]✓ Dry-run successful; stage gate unchanged for {stage.value}[/yellow]")
        return

    gate_status = "accepted" if accept_stage else "completed"
    gate.mark(stage.value, gate_status, evidence=f"modules={','.join(m.name for m in modules_to_run)}")
    console.print(f"[green]✓ Stage {stage.value} marked as {gate_status}[/green]")


@app.command("install-ai")
def install_ai(
    args: List[str] = typer.Argument(None, help="Argparse-style flags, e.g. --openclaw --vscode"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to configuration file"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview changes only"),
):
    """Install AI framework modules using argparse-style flags."""
    import sec_bootstrapper.modules  # noqa: F401

    config = _load_config(config_path)
    selection = parse_ai_selection(args or [])
    frameworks = selection.frameworks or ([config.ai_frameworks.install] if config.ai_frameworks.install else [])
    frameworks = [f for f in frameworks if f and f != "none"]

    if not frameworks:
        console.print("[yellow]No AI frameworks selected.[/yellow]")
        raise typer.Exit()

    rollback = RollbackManager()
    for framework in frameworks:
        mod_class = ModuleRegistry.get(framework)
        if not mod_class:
            console.print(f"[red]AI module not found: {framework}[/red]")
            raise typer.Exit(1)

        module_instance = mod_class(config=config, rollback_manager=rollback, dry_run=dry_run)
        result = module_instance.run()
        status = result.status.value
        if status in {"failed", "rolled_back"}:
            console.print(f"[red]✗ {framework}: {result.message}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✓ {framework}: {result.message}[/green]")


@app.command("stage-status")
def stage_status(config_path: Optional[Path] = typer.Option(None, "--config", "-c")):
    """Show stage gate status."""
    config = _load_config(config_path)
    gate = StageGateManager(config.stage_gate.state_file)

    table = Table(title="Stage Gate Status")
    table.add_column("Stage", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Completed At", style="yellow")
    table.add_column("Evidence", style="magenta")

    for name, record in gate.state.stages.items():
        table.add_row(name, record.status, record.completed_at or "-", record.evidence or "-")
    console.print(table)


@app.command("list-modules")
def list_modules():
    """List available modules."""
    import sec_bootstrapper.modules  # noqa: F401

    table = Table(title="Registered Modules")
    table.add_column("Name", style="cyan")
    table.add_column("Stage", style="magenta")
    table.add_column("Phase", style="blue")
    table.add_column("Dependencies", style="yellow")

    for name in sorted(ModuleRegistry.list_all()):
        mod = ModuleRegistry.get(name)
        if mod:
            deps = ", ".join(mod.dependencies) if mod.dependencies else "-"
            table.add_row(mod.name, str(mod.stage), mod.phase, deps)
    console.print(table)


@app.command("debloat")
def debloat_scan(
    only_recommended: bool = typer.Option(
        False,
        "--only-recommended",
        help="Show only rows that are currently recommended for removal/disablement.",
    ),
):
    """Scan for optional/noisy distro components and print hardening recommendations."""
    scanner = DebloatScanner()
    report = scanner.scan()

    if not report.apt_supported:
        console.print("[yellow]APT package inventory not available; package scan was skipped.[/yellow]")
    if not report.systemctl_supported:
        console.print("[yellow]systemctl not available; service scan was skipped.[/yellow]")

    findings = report.recommended_findings if only_recommended else report.findings
    if not findings:
        console.print("[green]No debloat recommendations found.[/green]")
        return

    table = Table(title="Debloat Recommendations")
    table.add_column("Pick", style="cyan", no_wrap=True)
    table.add_column("Component", style="magenta")
    table.add_column("Installed", style="green")
    table.add_column("Enabled/Active Services", style="yellow")
    table.add_column("Why", style="white")

    for finding in findings:
        marker = "x" if finding.recommended else " "
        packages = ", ".join(finding.installed_packages) if finding.installed_packages else "-"
        services_list = finding.enabled_services + [
            svc for svc in finding.active_services if svc not in finding.enabled_services
        ]
        services = ", ".join(services_list) if services_list else "-"
        table.add_row(marker, finding.rule.title, packages, services, finding.rule.rationale)

    console.print(table)
    console.print(
        "[bold]To tighten security we recommend removing/disabling items marked x.[/bold]"
    )

    if report.recommended_packages:
        console.print("\n[bold]Suggested package cleanup (review before running):[/bold]")
        console.print(
            "sudo apt-get purge -y " + " ".join(report.recommended_packages),
            style="dim",
        )
        console.print("sudo apt-get autoremove -y", style="dim")

    if report.recommended_services:
        console.print("\n[bold]Suggested service disablement (review before running):[/bold]")
        console.print(
            "sudo systemctl disable --now " + " ".join(report.recommended_services),
            style="dim",
        )


if __name__ == "__main__":
    app()
