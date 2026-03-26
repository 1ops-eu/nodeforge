"""loft-cli-agent CLI — server-side execution commands.

Commands:
    apply   <plan.json>  — Execute a plan from a JSON file
    doctor  <plan.json>  — Check drift between desired plan and actual state
    status               — Print current runtime state
    version              — Print agent version
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="loft-cli-agent",
    help="Server-side agent for loft-cli — executes plans locally.",
    no_args_is_help=True,
)

console = Console()


@app.command()
def apply(
    plan_file: Path = typer.Argument(..., help="Path to plan JSON file", exists=True),
) -> None:
    """Execute a plan from a JSON file."""
    from loft_cli_agent.executor import AgentExecutor
    from loft_cli_agent.lock import LockError, MutationLock
    from loft_cli_agent.paths import ensure_agent_dirs
    from loft_cli_core.plan.models import Plan

    ensure_agent_dirs()

    # Load the plan
    try:
        plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
        plan = Plan.model_validate(plan_data)
    except Exception as e:
        console.print(f"[bold red]Failed to load plan:[/bold red] {e}")
        raise typer.Exit(1) from None

    console.print(
        Panel(
            f"[bold]Spec:[/bold]  {plan.spec_name} ({plan.spec_kind})\n"
            f"[bold]Steps:[/bold] {len(plan.steps)}",
            title="loft-cli-agent apply",
            border_style="bright_blue",
        )
    )

    # Acquire mutation lock and execute
    try:
        with MutationLock():
            executor = AgentExecutor(plan=plan)
            result = executor.apply()
    except LockError as e:
        console.print(f"[bold red]Lock error:[/bold red] {e}")
        raise typer.Exit(1) from None

    # Print results
    icons = {"success": "✓", "failed": "✗", "skipped": "○", "unchanged": "≡"}
    colors = {"success": "green", "failed": "red", "skipped": "dim", "unchanged": "blue"}

    for sr in result.step_results:
        icon = icons.get(sr.status, "?")
        color = colors.get(sr.status, "white")
        duration = f"{sr.duration_seconds:.1f}s" if sr.duration_seconds else ""
        console.print(
            f"  [{color}]{icon}[/{color}] [{sr.step_index:>2}] {sr.step_id[:50]}"
            + (f" [{duration}]" if duration else ""),
        )
        if sr.status == "failed" and sr.error:
            console.print(f"     [red]{sr.error[:120]}[/red]")

    # Summary
    console.print(
        f"\n[bold]Applied:[/bold] {result.applied_count}  "
        f"[bold]Unchanged:[/bold] {result.unchanged_count}  "
        f"[bold]Status:[/bold] {result.status}"
    )

    # Write result JSON to stdout for the client to parse
    result_json = result.model_dump_json(indent=2)
    # Write to a result file that the client can download
    result_path = Path("/var/lib/loft-cli/last-result.json")
    with contextlib.suppress(Exception):
        result_path.write_text(result_json, encoding="utf-8")

    # Store desired state for drift detection (doctor command)
    desired_path = Path("/var/lib/loft-cli/desired/desired-state.json")
    with contextlib.suppress(Exception):
        desired_path.parent.mkdir(parents=True, exist_ok=True)
        desired_path.write_text(plan_file.read_text(encoding="utf-8"), encoding="utf-8")

    if result.status == "failed":
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Print current runtime state."""
    from loft_cli_agent.state import load_state

    state = load_state()

    if not state.last_applied:
        console.print("[dim]No apply has been run yet.[/dim]")
        return

    console.print(
        Panel(
            f"[bold]Agent version:[/bold] {state.version}\n"
            f"[bold]Last applied:[/bold]  {state.last_applied}\n"
            f"[bold]Spec hash:[/bold]     {state.spec_hash[:16]}…\n"
            f"[bold]Plan hash:[/bold]     {state.plan_hash[:16]}…\n"
            f"[bold]Resources:[/bold]     {len(state.resources)}",
            title="loft-cli-agent status",
            border_style="bright_blue",
        )
    )

    for rid, rs in state.resources.items():
        status_color = "green" if rs.status == "applied" else "red"
        console.print(f"  [{status_color}]●[/{status_color}] {rid} ({rs.applied_at})")


@app.command()
def doctor(
    plan_file: Path = typer.Argument(
        None, help="Path to desired-state plan JSON (optional — uses stored state if omitted)"
    ),
) -> None:
    """Check drift between desired state and actual runtime state.

    Compares the desired plan against the current runtime-state.json to
    identify resources that have drifted (content hash mismatch), are
    missing (new), or are orphaned (present in state but not in plan).

    Outputs a JSON report to /var/lib/loft-cli/doctor-result.json.
    """
    from loft_cli_agent.state import load_state
    from loft_cli_core.plan.models import Plan, StepScope
    from loft_cli_core.utils.hashing import sha256_string

    # Load desired plan
    desired_path = plan_file
    if desired_path is None:
        desired_path = Path("/var/lib/loft-cli/desired/desired-state.json")
    if not desired_path.exists():
        console.print(
            "[bold red]No desired state found.[/bold red] "
            "Run 'loft-cli apply' first, or provide a plan file."
        )
        raise typer.Exit(1)

    try:
        plan_data = json.loads(desired_path.read_text(encoding="utf-8"))
        plan = Plan.model_validate(plan_data)
    except Exception as e:
        console.print(f"[bold red]Failed to load desired state:[/bold red] {e}")
        raise typer.Exit(1) from None

    state = load_state()

    console.print(
        Panel(
            f"[bold]Spec:[/bold]  {plan.spec_name} ({plan.spec_kind})\n"
            f"[bold]Last applied:[/bold] {state.last_applied or 'never'}",
            title="loft-cli-agent doctor",
            border_style="bright_blue",
        )
    )

    # Compare desired steps against runtime state
    remote_steps = [s for s in plan.steps if s.scope in (StepScope.REMOTE, StepScope.VERIFY)]

    drifted = []
    missing = []
    unchanged = []
    always_run_steps = []

    desired_ids = set()
    for step in remote_steps:
        desired_ids.add(step.id)
        parts = [step.id, step.command or "", step.file_content or "", step.target_path or ""]
        content_hash = sha256_string("".join(parts))
        is_always = "always" in step.tags or step.gate or step.scope == StepScope.VERIFY

        if is_always:
            always_run_steps.append(step.id)
            continue

        existing = state.resources.get(step.id)
        if existing is None:
            missing.append(step.id)
        elif existing.content_hash != content_hash:
            drifted.append(step.id)
        else:
            unchanged.append(step.id)

    # Orphaned resources: in state but not in desired plan
    orphaned = [rid for rid in state.resources if rid not in desired_ids]

    # Print results
    icons = {"drifted": "~", "missing": "+", "unchanged": "=", "orphaned": "-"}
    colors = {"drifted": "yellow", "missing": "green", "unchanged": "dim", "orphaned": "red"}

    for rid in missing:
        console.print(
            f"  [{colors['missing']}]{icons['missing']}[/{colors['missing']}] {rid} (new — not yet applied)"
        )
    for rid in drifted:
        console.print(
            f"  [{colors['drifted']}]{icons['drifted']}[/{colors['drifted']}] {rid} (drifted — content changed)"
        )
    for rid in orphaned:
        console.print(
            f"  [{colors['orphaned']}]{icons['orphaned']}[/{colors['orphaned']}] {rid} (orphaned — no longer in spec)"
        )
    for rid in unchanged:
        console.print(
            f"  [{colors['unchanged']}]{icons['unchanged']}[/{colors['unchanged']}] {rid}"
        )

    # Summary
    console.print(
        f"\n[green]+{len(missing)} new[/green]  "
        f"[yellow]~{len(drifted)} drifted[/yellow]  "
        f"[red]-{len(orphaned)} orphaned[/red]  "
        f"[dim]={len(unchanged)} unchanged[/dim]  "
        f"[cyan]{len(always_run_steps)} always-run[/cyan]"
    )

    # Write doctor result as JSON for client to download
    doctor_result = {
        "spec_name": plan.spec_name,
        "spec_kind": plan.spec_kind,
        "drifted": drifted,
        "missing": missing,
        "orphaned": orphaned,
        "unchanged": unchanged,
        "always_run": always_run_steps,
        "healthy": len(drifted) == 0 and len(missing) == 0 and len(orphaned) == 0,
    }
    result_path = Path("/var/lib/loft-cli/doctor-result.json")
    with contextlib.suppress(Exception):
        result_path.write_text(json.dumps(doctor_result, indent=2), encoding="utf-8")

    if drifted or missing or orphaned:
        console.print("\n[bold yellow]Server has drifted from desired state.[/bold yellow]")
        raise typer.Exit(1)
    else:
        console.print("\n[bold green]Server matches desired state.[/bold green]")


@app.command()
def version() -> None:
    """Print agent version."""
    from loft_cli_core import __version__

    console.print(f"loft-cli-agent {__version__}")


if __name__ == "__main__":
    app()
