"""Rich console output for the 'nodeforge plan' command."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nodeforge.plan.models import Plan, StepKind, StepScope

_SCOPE_COLORS = {
    StepScope.REMOTE: "cyan",
    StepScope.LOCAL: "green",
    StepScope.VERIFY: "blue",
}

_KIND_LABELS: dict[str, str] = {
    StepKind.SSH_COMMAND: "ssh cmd",
    StepKind.SSH_UPLOAD: "ssh upload",
    StepKind.LOCAL_COMMAND: "local cmd",
    StepKind.LOCAL_FILE_WRITE: "file write",
    StepKind.LOCAL_DB_WRITE: "db write",
    StepKind.VERIFY: "verify",
    StepKind.GATE: "GATE",
}


def render_plan(plan: Plan, console: Console | None = None) -> None:
    """Print the plan to the console as a Rich table."""
    if console is None:
        console = Console()

    # Summary panel
    summary_lines = [
        f"[bold]Spec:[/bold]   {plan.spec_name}  ({plan.spec_kind})",
        f"[bold]Target:[/bold] {plan.target_host}",
        f"[bold]Steps:[/bold]  {len(plan.steps)}  "
        f"([cyan]{len(plan.remote_steps())} remote[/cyan], "
        f"[green]{len(plan.local_steps())} local[/green])",
        f"[bold]Hash:[/bold]   {plan.plan_hash[:16]}…",
    ]
    console.print(
        Panel("\n".join(summary_lines), title="nodeforge plan", border_style="bright_blue")
    )

    # Steps table
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="italic", min_width=30)
    table.add_column("Description", min_width=40)
    table.add_column("Scope", width=8)
    table.add_column("Kind", width=12)
    table.add_column("Gate", width=6)
    table.add_column("Depends", width=12)

    for step in plan.steps:
        color = _SCOPE_COLORS.get(step.scope, "white")
        scope_text = Text(step.scope.value, style=color)
        kind_label = _KIND_LABELS.get(step.kind, step.kind)

        gate_text = Text("YES", style="bold yellow") if step.gate else Text("")
        depends_text = (
            Text(", ".join(str(d) for d in step.depends_on)) if step.depends_on else Text("")
        )

        desc = step.description
        if step.gate:
            desc = f"[bold yellow]{desc}[/bold yellow]"

        table.add_row(
            str(step.index),
            step.id,
            desc,
            scope_text,
            kind_label,
            gate_text,
            depends_text,
        )

    console.print(table)
