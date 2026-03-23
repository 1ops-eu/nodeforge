"""Diff renderer for dry-run comparison.

Shows what would change on the server if the plan were applied,
comparing the new plan against the agent's current runtime state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nodeforge_core.plan.models import Plan, StepScope
from nodeforge_core.utils.hashing import sha256_string

if TYPE_CHECKING:
    from nodeforge_core.state import RuntimeState


def _step_content_hash(step) -> str:
    """Compute the same content hash as the agent executor."""
    parts = [step.id, step.command or "", step.file_content or "", step.target_path or ""]
    return sha256_string("".join(parts))


def render_diff(
    plan: Plan,
    current_state: RuntimeState | None,
    console: Console | None = None,
) -> None:
    """Render a diff showing what would change if the plan were applied.

    Compares each step's content hash against the runtime state to
    classify steps as: added (new), changed, unchanged, or always-run.
    """
    c = console or Console()

    c.print(
        Panel(
            f"[bold]Spec:[/bold]   {plan.spec_name} ({plan.spec_kind})\n"
            f"[bold]Target:[/bold] {plan.target_host}\n"
            f"[bold]Steps:[/bold]  {len(plan.steps)}",
            title="nodeforge diff",
            border_style="bright_blue",
        )
    )

    if current_state is None:
        c.print("[yellow]No runtime state found — all steps would be applied (first run)[/yellow]")
        current_resources = {}
    else:
        current_resources = current_state.resources

    # Classify steps
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", min_width=30)
    table.add_column("Status", width=12)
    table.add_column("Description", min_width=40)

    added = 0
    changed = 0
    unchanged = 0
    always_run = 0

    remote_steps = [s for s in plan.steps if s.scope in (StepScope.REMOTE, StepScope.VERIFY)]

    for step in remote_steps:
        content_hash = _step_content_hash(step)
        is_always = "always" in step.tags or step.gate or step.scope == StepScope.VERIFY

        if is_always:
            status = "always"
            color = "cyan"
            always_run += 1
        elif step.id not in current_resources:
            status = "+ added"
            color = "green"
            added += 1
        elif current_resources[step.id].content_hash != content_hash:
            status = "~ changed"
            color = "yellow"
            changed += 1
        else:
            status = "= unchanged"
            color = "dim"
            unchanged += 1

        table.add_row(
            str(step.index),
            step.id,
            Text(status, style=color),
            step.description[:60],
        )

    c.print(table)

    # Summary
    c.print(
        f"\n[green]+{added} added[/green]  "
        f"[yellow]~{changed} changed[/yellow]  "
        f"[dim]={unchanged} unchanged[/dim]  "
        f"[cyan]{always_run} always-run[/cyan]"
    )

    if changed == 0 and added == 0:
        c.print("\n[bold green]No changes — server is up to date.[/bold green]")
    else:
        c.print(f"\n[bold]{added + changed} step(s) would be applied.[/bold]")
