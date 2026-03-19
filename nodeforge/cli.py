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
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from nodeforge.local.inventory_db import InventoryDB

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


@app.callback()
def _startup() -> None:
    """Load built-in kinds and any installed addons before running a command."""
    from nodeforge.registry import load_addons

    load_addons()


def _build_pipeline(
    spec_path: Path,
    ensure_keys: bool = False,
    *,
    strict_env: bool = True,
    env_file: Path | None = None,
):
    """Run Parse → Validate → (KeyGen) → Normalize → Plan. Returns (spec, ctx, plan, issues)."""
    from nodeforge.compiler.normalizer import normalize
    from nodeforge.compiler.parser import parse
    from nodeforge.compiler.planner import plan as make_plan
    from nodeforge.registry import get_kind_hooks
    from nodeforge.specs.validators import validate_spec

    spec = parse(spec_path, strict_env=strict_env, env_file=env_file)
    issues = validate_spec(spec)

    # Ensure admin SSH key pairs exist before normalization reads pubkey content.
    # Determined by the kind's registered hooks, not by a hardcoded isinstance check.
    if ensure_keys and get_kind_hooks(spec.kind).needs_key_generation:
        from nodeforge.local.keys import ensure_admin_keys

        ensure_admin_keys(spec, console=console)

    ctx = normalize(spec, spec_dir=spec_path.resolve().parent)
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
    env_file: Path | None = typer.Option(
        None, "--env-file", help="Load environment variables from a .env file"
    ),
    passthrough: bool = typer.Option(
        False,
        "--passthrough",
        help="Leave unresolved ${VAR} references unchanged instead of erroring",
    ),
) -> None:
    """Validate a YAML spec file against its schema."""
    from nodeforge.compiler.parser import parse
    from nodeforge.specs.validators import has_errors, validate_spec

    console.print(f"[bold]Validating:[/bold] {spec}")
    try:
        parsed = parse(spec, strict_env=not passthrough, env_file=env_file)
    except Exception as e:
        console.print(f"[bold red]Parse error:[/bold red] {e}")
        raise typer.Exit(1) from None

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
    env_file: Path | None = typer.Option(
        None, "--env-file", help="Load environment variables from a .env file"
    ),
    passthrough: bool = typer.Option(
        False,
        "--passthrough",
        help="Leave unresolved ${VAR} references unchanged instead of erroring",
    ),
) -> None:
    """Show the execution plan for a spec without applying it."""
    from nodeforge.plan.render_text import render_plan

    try:
        _, _, p, issues = _build_pipeline(spec, strict_env=not passthrough, env_file=env_file)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

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
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output file (default: stdout)"
    ),
    mode: str = typer.Option("guide", "--mode", "-m", help="Output mode: guide or commands"),
    env_file: Path | None = typer.Option(
        None, "--env-file", help="Load environment variables from a .env file"
    ),
    passthrough: bool = typer.Option(
        False,
        "--passthrough",
        help="Leave unresolved ${VAR} references unchanged instead of erroring",
    ),
) -> None:
    """Generate Markdown documentation from a spec's execution plan."""
    from nodeforge.plan.render_markdown import render_markdown

    try:
        _, _, p, issues = _build_pipeline(spec, strict_env=not passthrough, env_file=env_file)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

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
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without executing"
    ),
    env_file: Path | None = typer.Option(
        None, "--env-file", help="Load environment variables from a .env file"
    ),
    passthrough: bool = typer.Option(
        False,
        "--passthrough",
        help="Leave unresolved ${VAR} references unchanged instead of erroring",
    ),
) -> None:
    """Apply a spec to provision infrastructure."""
    from nodeforge.local.inventory_db import InventoryDB
    from nodeforge.logs.writer import write_log
    from nodeforge.registry import get_kind_hooks
    from nodeforge.runtime.executor import Executor
    from nodeforge.runtime.ssh import SSHSession

    try:
        parsed_spec, ctx, p, issues = _build_pipeline(
            spec, ensure_keys=True, strict_env=not passthrough, env_file=env_file
        )
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1) from None

    if issues:
        _print_issues(issues, stop_on_error=True)

    console.print(
        Panel(
            f"[bold]Applying:[/bold] {parsed_spec.meta.name}\n"
            f"[bold]Target:[/bold]  {parsed_spec.host.address}\n"
            f"[bold]Steps:[/bold]   {len(p.steps)}"
            + (" [yellow](DRY RUN)[/yellow]" if dry_run else ""),
            title="nodeforge apply",
            border_style="bright_blue",
        )
    )

    # Build SSH session
    ssh_session = None
    if not dry_run:
        import socket

        def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    return True
            except OSError:
                return False

        login = parsed_spec.login
        key_path = (
            str(ctx.login_key_path) if ctx.login_key_path and ctx.login_key_path.exists() else None
        )

        # For specs that declare ssh_port_fallback (e.g. bootstrap), if login.port is
        # unreachable try ssh.port as fallback. This allows clean re-runs after a
        # partial apply that already moved SSH to the new port.
        effective_port = login.port
        effective_user = login.user
        effective_key_path = key_path
        effective_password = ctx.login_password
        hooks = get_kind_hooks(parsed_spec.kind)
        if hooks.ssh_port_fallback and not _tcp_reachable(parsed_spec.host.address, login.port):
            fallback_port = parsed_spec.ssh.port
            if fallback_port != login.port and _tcp_reachable(
                parsed_spec.host.address, fallback_port
            ):
                console.print(
                    f"[yellow]⚠ login.port {login.port} unreachable — "
                    f"reconnecting on ssh.port {fallback_port}[/yellow]"
                )
                effective_port = fallback_port

                # When the port has already changed, the server may be fully
                # hardened (root login disabled, password auth disabled).  Try
                # the admin user with key auth on the fallback port first.
                admin_name = (
                    parsed_spec.admin_user.name if hasattr(parsed_spec, "admin_user") else None
                )
                admin_key = (
                    str(ctx.admin_key_path)
                    if ctx.admin_key_path and ctx.admin_key_path.exists()
                    else None
                )
                if admin_name and admin_key:
                    try:
                        probe = SSHSession(
                            host=parsed_spec.host.address,
                            user=admin_name,
                            port=fallback_port,
                            key_path=admin_key,
                        )
                        if probe.test_connection():
                            console.print(
                                f"[yellow]⚠ Server already bootstrapped — "
                                f"using {admin_name}@{parsed_spec.host.address}:"
                                f"{fallback_port} with key auth[/yellow]"
                            )
                            effective_user = admin_name
                            effective_key_path = admin_key
                            effective_password = None
                        probe.close()
                    except Exception:
                        pass  # fall through to original credentials
            else:
                console.print(
                    f"[bold red]✗ Cannot reach {parsed_spec.host.address} "
                    f"on port {login.port} or {fallback_port} — "
                    f"check that the host is up and reachable.[/bold red]"
                )
                raise typer.Exit(1)

        ssh_session = SSHSession(
            host=parsed_spec.host.address,
            user=effective_user,
            port=effective_port,
            key_path=effective_key_path,
            password=effective_password,
        )

    # Build inventory DB
    inventory_db = None
    inv_cfg = parsed_spec.local.inventory
    if inv_cfg.enabled:
        inventory_db = InventoryDB(db_path=str(ctx.db_path))

    executor = Executor(
        plan=p,
        ssh_session=ssh_session,
        inventory_db=inventory_db,
        ctx=ctx,
        spec=parsed_spec,
        console=console,
        effective_port=effective_port if ssh_session else None,
    )

    result = executor.apply(dry_run=dry_run)

    # Post-apply: record inventory via the kind's registered hook.
    if not dry_run and inventory_db and "success" in result.status:
        try:
            record_fn = get_kind_hooks(parsed_spec.kind).on_inventory_record
            if record_fn is not None:
                record_fn(inventory_db, parsed_spec, result)
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
        from nodeforge.registry.local_paths import get_local_paths

        log_dir = get_local_paths().log_dir
        console.print(f"[red]Run '{run_id}' not found in {log_dir}[/red]")
        raise typer.Exit(1)

    data = read_log(log_path)

    console.print(
        Panel(
            f"[bold]Spec:[/bold]   {data.get('spec_name')} ({data.get('spec_kind')})\n"
            f"[bold]Target:[/bold] {data.get('target_host')}\n"
            f"[bold]Status:[/bold] {data.get('status')}\n"
            f"[bold]Started:[/bold] {data.get('started_at')}\n"
            f"[bold]Finished:[/bold] {data.get('finished_at')}",
            title=f"Run: {data.get('run_id')}",
        )
    )

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


def _get_db() -> InventoryDB:
    from nodeforge.local.inventory_db import InventoryDB
    from nodeforge.registry.local_paths import get_local_paths

    # Explicit NODEFORGE_DB_PATH takes priority (backward compat),
    # then fall back to get_local_paths() which respects NODEFORGE_STATE_DIR.
    db_path = os.environ.get("NODEFORGE_DB_PATH") or str(get_local_paths().inventory_db_path)
    db = InventoryDB(db_path=db_path)
    db.open()
    return db


@inventory_app.command("list")
def inventory_list() -> None:
    """List all provisioned servers from local inventory."""
    db = _get_db()
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
) -> None:
    """Show details of a specific server from local inventory."""
    from nodeforge.local.inventory import show_server

    db = _get_db()
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
            console.print(
                f"  • {svc.get('service_type')}: {svc.get('service_name')} [{svc.get('status')}]"
            )
    else:
        console.print("[dim]No services recorded.[/dim]")


if __name__ == "__main__":
    app()
