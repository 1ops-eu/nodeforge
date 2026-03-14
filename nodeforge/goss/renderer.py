"""Render goss validation results as a human-readable Rich table.

The output is intentionally concise: one row per check, colour-coded status,
a summary line, and — if there were failures — a separate panel listing only
the failing checks with their details so the operator can act immediately.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    pass

# Goss resource-type display names (goss JSON uses lower-case keys)
_TYPE_LABELS: dict[str, str] = {
    "User":      "user",
    "File":      "file",
    "Service":   "service",
    "Port":      "port",
    "Package":   "package",
    "Command":   "command",
    "Interface": "interface",
    "Addr":      "addr",
    "DNS":       "dns",
    "HTTP":      "http",
    "Process":   "process",
    "Kernel":    "kernel-param",
    "Mount":     "mount",
    "Gossfile":  "gossfile",
}


def render_goss_results(goss_result: dict, console: Console | None = None) -> None:
    """Pretty-print goss validation results to the terminal.

    Args:
        goss_result: dict returned by ``shipper.ship_and_run()``.
        console:     Rich Console to write to (creates a new one if None).
    """
    if console is None:
        console = Console()

    # ------------------------------------------------------------------ #
    # Guard: shipper-level error (goss never ran)
    # ------------------------------------------------------------------ #
    if goss_result.get("error"):
        console.print(Panel(
            f"[bold red]Goss could not run:[/bold red]\n{goss_result['error']}",
            title="[bold red]Goss Error[/bold red]",
            border_style="red",
        ))
        return

    results: list[dict] = goss_result.get("results", [])
    summary: dict = goss_result.get("summary", {})

    total    = summary.get("test-count",   len(results))
    passed   = summary.get("success-count", sum(1 for r in results if r.get("successful")))
    failed   = summary.get("failed-count",  sum(1 for r in results if not r.get("successful")))
    skipped  = summary.get("skipped-count", 0)
    duration = summary.get("total-duration", 0)
    duration_s = f"{duration / 1e9:.2f}s" if duration else ""

    all_pass = failed == 0

    # ------------------------------------------------------------------ #
    # Main results table
    # ------------------------------------------------------------------ #
    table = Table(
        show_header=True,
        header_style="bold dim",
        border_style="bright_blue",
        box=_rich_box(),
        padding=(0, 1),
        expand=False,
    )
    table.add_column("Resource type", min_width=12, no_wrap=True)
    table.add_column("Resource ID",   min_width=30)
    table.add_column("Property",      min_width=16)
    table.add_column("Status",        min_width=9,  justify="center")
    table.add_column("Details",       min_width=24)

    for r in results:
        resource_type = r.get("resource-type", "")
        resource_id   = r.get("resource-id", "")
        property_name = r.get("property", "")
        successful    = r.get("successful", False)
        expected      = r.get("expected", [])
        found         = r.get("found", [])
        msg           = r.get("msg", "")

        label = _TYPE_LABELS.get(resource_type, resource_type.lower())

        if successful:
            status_text = Text("✓ PASS", style="bold green")
            details     = Text("")
        else:
            status_text = Text("✗ FAIL", style="bold red")
            # Produce a compact diff-style detail string
            exp_str   = _short(expected)
            found_str = _short(found)
            if msg and msg not in ("", "none"):
                details = Text(msg[:60], style="red")
            elif exp_str != found_str:
                details = Text(f"want {exp_str}  got {found_str}", style="red")
            else:
                details = Text(exp_str[:60], style="red")

        table.add_row(
            Text(label, style="dim"),
            Text(_truncate(resource_id, 40), style=""),
            Text(property_name, style="dim"),
            status_text,
            details,
        )

    # ------------------------------------------------------------------ #
    # Summary footer text
    # ------------------------------------------------------------------ #
    if all_pass:
        summary_style  = "bold green"
        summary_icon   = "✓"
        summary_label  = "All checks passed"
    else:
        summary_style  = "bold red"
        summary_icon   = "✗"
        summary_label  = f"{failed} check{'s' if failed != 1 else ''} failed"

    counts = (
        f"{total} total  •  "
        f"[green]{passed} passed[/green]  •  "
        f"{'[red]' if failed else '[dim]'}{failed} failed{'[/red]' if failed else '[/dim]'}  •  "
        f"[dim]{skipped} skipped[/dim]"
        + (f"  •  [dim]{duration_s}[/dim]" if duration_s else "")
    )

    title = (
        f"[{summary_style}]{summary_icon} Goss Verification — {summary_label}[/{summary_style}]"
    )

    console.print(Panel(table, title=title, border_style="green" if all_pass else "red"))
    console.print(f"  {counts}\n")

    # ------------------------------------------------------------------ #
    # Failure detail panel — only shown when there are failures
    # ------------------------------------------------------------------ #
    if not all_pass:
        failed_lines: list[str] = []
        for r in results:
            if r.get("successful"):
                continue
            rtype = _TYPE_LABELS.get(r.get("resource-type", ""), r.get("resource-type", "").lower())
            rid   = r.get("resource-id", "")
            prop  = r.get("property", "")
            exp   = _short(r.get("expected", []))
            fnd   = _short(r.get("found", []))
            msg   = r.get("msg", "")
            line  = f"[bold]{rtype}[/bold].[dim]{_truncate(rid, 35)}[/dim]  {prop}"
            if msg and msg not in ("", "none"):
                line += f"\n    [red]{msg}[/red]"
            else:
                line += f"\n    expected [green]{exp}[/green]  got [red]{fnd}[/red]"
            failed_lines.append(line)

        console.print(Panel(
            "\n\n".join(failed_lines),
            title="[bold red]Failed checks — action required[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _short(value) -> str:
    """Compact representation of goss expected/found lists."""
    if isinstance(value, list):
        if len(value) == 0:
            return "[]"
        if len(value) == 1:
            return str(value[0])
        return "[" + ", ".join(str(v) for v in value[:3]) + (", …" if len(value) > 3 else "") + "]"
    return str(value)


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def _rich_box():
    """Return a simple box style compatible with all Rich versions."""
    try:
        from rich import box
        return box.SIMPLE_HEAVY
    except Exception:
        return None
