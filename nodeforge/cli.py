"""nodeforge CLI — 6 commands wiring the full pipeline.

validate  <spec.yaml>
plan      <spec.yaml>
docs      <spec.yaml> [--output FILE] [--mode guide|commands]
apply     <spec.yaml> [--dry-run]
inspect   run <run-id>
inventory list | show <server-id>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

app = typer.Typer(
    name="nodeforge",
    help=(
        "Securely bootstrap Linux servers into production-ready nodes — "
        "with auditable plans, generated ops docs, and encrypted local inventory."
    ),
    no_args_is_help=True,
    add_completion=False,
)
inventory_app = typer.Typer(help="Manage local server inventory.", no_args_is_help=True)
inspect_app = typer.Typer(help="Inspect apply runs.", no_args_is_help=True)
app.add_typer(inventory_app, name="inventory")
app.add_typer(inspect_app, name="inspect")

console = Console()


def _build_pipeline(spec_path: Path):
    """Run Parse → Validate → Normalize → Plan. Returns (spec, ctx, plan, issues)."""
    from nodeforge.compiler.parser import parse
    from nodeforge.compiler.normalizer import normalize
    from nodeforge.compiler.planner import plan as make_plan
    from nodeforge.specs.validators import validate_spec

    spec = parse(spec_path)
    issues = validate_spec(spec)
    ctx = normalize(spec)
    p = make_plan(ctx)
    return spec, ctx, p, issues


def _print_issues(issues, stop_on_error: bool = True) -> None:
    from nodeforge.specs.validators import has_errors

    for issue in issues:
        color = "red" if issue.severity == "error" else "yellow"
        console.print(f"  [{color}]{issue}[/{color}]")

    if stop_on_error and has_errors(issues):
        console.print("\n[bold red]Validation errors found. Fix before applying.[/bold red]")
        raise typer.Exit(1)


# ------------------------------------------------------------------ #
# validate
# ------------------------------------------------------------------ #

@app.command()
def validate(
    spec: Path = typer.Argument(..., help="Path to YAML spec file", exists=True),
) -> None:
    """Validate a YAML spec file against its schema."""
    from nodeforge.compiler.parser import parse
    from nodeforge.specs.validators import validate_spec, has_errors

    console.print(f"[bold]Validating:[/bold] {spec}")
    try:
        parsed = parse(spec)
    except Exception as e:
        console.print(f"[bold red]Parse error:[/bold red] {e}")
        raise typer.Exit(1)

    issues = validate_spec(parsed)

    if not issues:
        console.print("[bold green]✓ Spec is valid.[/bold green]")
    else:
        _print_issues(issues, stop_on_error=False)
        if has_errors(issues):
            raise typer.Exit(1)


# ------------------------------------------------------------------ #
# plan
# ------------------------------------------------------------------ #

@app.command()
def plan(
    spec: Path = typer.Argument(..., help="Path to YAML spec file", exists=True),
) -> None:
    """Show the execution plan for a spec without applying it."""
    from nodeforge.plan.render_text import render_plan

    try:
        _, _, p, issues = _build_pipeline(spec)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    if issues:
        console.print("[bold yellow]Validation warnings:[/bold yellow]")
        _print_issues(issues, stop_on_error=True)

    render_plan(p, console=console)


# ------------------------------------------------------------------ #
# docs
# ------------------------------------------------------------------ #

@app.command()
def docs(
    spec: Path = typer.Argument(..., help="Path to YAML spec file", exists=True),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    mode: str = typer.Option("guide", "--mode", "-m", help="Output mode: guide or commands"),
) -> None:
    """Generate Markdown documentation from a spec's execution plan."""
    from nodeforge.plan.render_markdown import render_markdown

    try:
        _, _, p, issues = _build_pipeline(spec)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    if issues:
        _print_issues(issues, stop_on_error=True)

    md = render_markdown(p, mode=mode)

    if output:
        output.write_text(md, encoding="utf-8")
        console.print(f"[bold green]✓ Docs written to:[/bold green] {output}")
    else:
        print(md)


# ------------------------------------------------------------------ #
# apply
# ------------------------------------------------------------------ #

@app.command()
def apply(
    spec: Path = typer.Argument(..., help="Path to YAML spec file", exists=True),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done without executing"),
    db_key: Optional[str] = typer.Option(None, "--db-key", envvar="NODEFORGE_SQLCIPHER_KEY",
                                          help="SQLCipher inventory key"),
) -> None:
    """Apply a spec to provision infrastructure."""
    from nodeforge.runtime.ssh import SSHSession
    from nodeforge.runtime.executor import Executor
    from nodeforge.local.sqlcipher import InventoryDB
    from nodeforge.local.inventory import record_bootstrap, record_service_apply
    from nodeforge.logs.writer import write_log
    from nodeforge.specs.bootstrap_schema import BootstrapSpec

    try:
        parsed_spec, ctx, p, issues = _build_pipeline(spec)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)

    if issues:
        _print_issues(issues, stop_on_error=True)

    console.print(Panel(
        f"[bold]Applying:[/bold] {parsed_spec.meta.name}\n"
        f"[bold]Target:[/bold]  {parsed_spec.host.address}\n"
        f"[bold]Steps:[/bold]   {len(p.steps)}"
        + (" [yellow](DRY RUN)[/yellow]" if dry_run else ""),
        title="nodeforge apply",
        border_style="bright_blue",
    ))

    # Build SSH session
    ssh_session = None
    if not dry_run:
        login = parsed_spec.login
        key_path = str(ctx.login_key_path) if ctx.login_key_path and ctx.login_key_path.exists() else None
        ssh_session = SSHSession(
            host=parsed_spec.host.address,
            user=login.user,
            port=login.port,
            key_path=key_path,
        )

    # Build inventory DB
    inventory_db = None
    inv_cfg = (
        parsed_spec.local.inventory
        if isinstance(parsed_spec, BootstrapSpec)
        else parsed_spec.local.inventory
    )
    if inv_cfg.enabled and db_key:
        inventory_db = InventoryDB(key=db_key, db_path=str(ctx.db_path))
    elif inv_cfg.enabled:
        console.print("[yellow]⚠ NODEFORGE_SQLCIPHER_KEY not set — inventory will be skipped[/yellow]")

    executor = Executor(
        plan=p,
        ssh_session=ssh_session,
        inventory_db=inventory_db,
        ctx=ctx,
        spec=parsed_spec,
        console=console,
    )

    result = executor.apply(dry_run=dry_run)

    # Post-apply: record inventory
    if not dry_run and inventory_db and "success" in result.status:
        try:
            if isinstance(parsed_spec, BootstrapSpec):
                record_bootstrap(inventory_db, parsed_spec, result)
            else:
                record_service_apply(inventory_db, parsed_spec, result)
        except Exception as e:
            console.print(f"[yellow]⚠ Inventory update failed: {e}[/yellow]")
        finally:
            inventory_db.close()

    # Write execution log
    if not dry_run:
        try:
            log_path = write_log(result)
            console.print(f"\n[dim]Run log: {log_path}[/dim]")
        except Exception as e:
            console.print(f"[yellow]⚠ Log write failed: {e}[/yellow]")

    # Close SSH session
    if ssh_session:
        ssh_session.close()

    # Summary
    status_color = {
        "success": "green",
        "success_with_local_warnings": "yellow",
        "failed": "red",
    }.get(result.status, "white")

    console.print(f"\n[bold {status_color}]Status: {result.status}[/bold {status_color}]")

    if result.status == "failed":
        raise typer.Exit(1)


# ------------------------------------------------------------------ #
# inspect run <run-id>
# ------------------------------------------------------------------ #

@inspect_app.command("run")
def inspect_run(
    run_id: str = typer.Argument(..., help="Run ID (or prefix) to inspect"),
) -> None:
    """Show details of a past apply run."""
    from nodeforge.logs.reader import find_log, read_log

    log_path = find_log(run_id)
    if not log_path:
        console.print(f"[red]Run '{run_id}' not found in ~/.nodeforge/runs/[/red]")
        raise typer.Exit(1)

    data = read_log(log_path)

    console.print(Panel(
        f"[bold]Spec:[/bold]   {data.get('spec_name')} ({data.get('spec_kind')})\n"
        f"[bold]Target:[/bold] {data.get('target_host')}\n"
        f"[bold]Status:[/bold] {data.get('status')}\n"
        f"[bold]Started:[/bold] {data.get('started_at')}\n"
        f"[bold]Finished:[/bold] {data.get('finished_at')}",
        title=f"Run: {data.get('run_id')}",
    ))

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("#", width=4)
    table.add_column("Step", min_width=30)
    table.add_column("Scope", width=8)
    table.add_column("Status", width=10)
    table.add_column("Duration", width=10)

    for step in data.get("steps", []):
        status = step["status"]
        color = {"success": "green", "failed": "red", "skipped": "dim"}.get(status, "white")
        table.add_row(
            str(step["index"]),
            step["id"],
            step["scope"],
            Text(status, style=color),
            f"{step['duration_seconds']:.1f}s",
        )

    console.print(table)


# ------------------------------------------------------------------ #
# inventory list | show
# ------------------------------------------------------------------ #

def _get_db(db_key: str | None) -> "InventoryDB":
    from nodeforge.local.sqlcipher import InventoryDB

    key = db_key or os.environ.get("NODEFORGE_SQLCIPHER_KEY")
    if not key:
        console.print("[red]NODEFORGE_SQLCIPHER_KEY not set[/red]")
        raise typer.Exit(1)

    db_path = os.environ.get("NODEFORGE_DB_PATH", "~/.nodeforge/inventory.db")
    db = InventoryDB(key=key, db_path=db_path)
    db.open()
    return db


@inventory_app.command("list")
def inventory_list(
    db_key: Optional[str] = typer.Option(None, "--db-key", envvar="NODEFORGE_SQLCIPHER_KEY"),
) -> None:
    """List all provisioned servers from local inventory."""
    db = _get_db(db_key)
    try:
        servers = db.list_servers()
    finally:
        db.close()

    if not servers:
        console.print("[dim]No servers in inventory.[/dim]")
        return

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Name", min_width=20)
    table.add_column("Address", min_width=15)
    table.add_column("Status", min_width=15)
    table.add_column("SSH", min_width=25)
    table.add_column("WireGuard")

    for s in servers:
        ssh_info = f"{s.get('ssh_user', '')}@{s.get('ssh_alias', s.get('name', ''))}:{s.get('ssh_port', '')}"
        wg = "yes" if s.get("wireguard_enabled") else "no"
        status_color = "green" if s.get("bootstrap_status") == "bootstrapped" else "yellow"
        table.add_row(
            s.get("name", ""),
            s.get("address", ""),
            Text(s.get("bootstrap_status", ""), style=status_color),
            ssh_info,
            wg,
        )
    console.print(table)


@inventory_app.command("show")
def inventory_show(
    server_id: str = typer.Argument(..., help="Server name or ID"),
    db_key: Optional[str] = typer.Option(None, "--db-key", envvar="NODEFORGE_SQLCIPHER_KEY"),
) -> None:
    """Show details of a specific server from local inventory."""
    from nodeforge.local.inventory import show_server

    db = _get_db(db_key)
    try:
        data = show_server(db, server_id)
    finally:
        db.close()

    if data is None:
        console.print(f"[red]Server '{server_id}' not found in inventory.[/red]")
        raise typer.Exit(1)

    lines = []
    for k, v in data.items():
        if k == "services":
            continue
        lines.append(f"[bold]{k}:[/bold] {v}")
    console.print(Panel("\n".join(lines), title=f"Server: {server_id}"))

    services = data.get("services", [])
    if services:
        console.print("\n[bold]Services:[/bold]")
        for svc in services:
            console.print(f"  • {svc.get('service_type')}: {svc.get('service_name')} [{svc.get('status')}]")
    else:
        console.print("[dim]No services recorded.[/dim]")


if __name__ == "__main__":
    app()
