"""nodeforge-agent CLI — server-side execution commands.

Commands:
    apply   <plan.json>  — Execute a plan from a JSON file
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
    name="nodeforge-agent",
    help="Server-side agent for nodeforge — executes plans locally.",
    no_args_is_help=True,
)

console = Console()


@app.command()
def apply(
    plan_file: Path = typer.Argument(..., help="Path to plan JSON file", exists=True),
) -> None:
    """Execute a plan from a JSON file."""
    from nodeforge_agent.executor import AgentExecutor
    from nodeforge_agent.lock import LockError, MutationLock
    from nodeforge_agent.paths import ensure_agent_dirs
    from nodeforge_core.plan.models import Plan

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
            title="nodeforge-agent apply",
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
    result_path = Path("/var/lib/nodeforge/last-result.json")
    with contextlib.suppress(Exception):
        result_path.write_text(result_json, encoding="utf-8")

    if result.status == "failed":
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Print current runtime state."""
    from nodeforge_agent.state import load_state

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
            title="nodeforge-agent status",
            border_style="bright_blue",
        )
    )

    for rid, rs in state.resources.items():
        status_color = "green" if rs.status == "applied" else "red"
        console.print(f"  [{status_color}]●[/{status_color}] {rid} ({rs.applied_at})")


@app.command()
def version() -> None:
    """Print agent version."""
    from nodeforge_core import __version__

    console.print(f"nodeforge-agent {__version__}")


if __name__ == "__main__":
    app()
