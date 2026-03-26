"""Orchestrate removal of all local loft-cli state for a decommissioned host.

``loft-cli remove <host>`` is the lifecycle endpoint: apply creates,
doctor monitors, remove cleans up.  It tears down:

1. Active WireGuard tunnel (if running)
2. WireGuard local state (``~/.wg/loft-cli/{host}/``)
3. SSH conf.d entry (``~/.ssh/conf.d/loft-cli/{host}.conf``)
4. Inventory record (marked as decommissioned)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console


def remove_host(host_name: str, *, console: Console | None = None) -> list[dict]:
    """Remove all local state for a host.

    Returns a list of result dicts: [{"action": ..., "status": ..., "detail": ...}].
    """
    results: list[dict] = []

    if console is None:
        from rich.console import Console

        console = Console()

    # 1. Tear down active WireGuard tunnel
    try:
        from loft_cli.local.tunnel import tunnel_down

        ok, msg = tunnel_down(host_name)
        results.append(
            {"action": "tunnel_down", "status": "ok" if ok else "skipped", "detail": msg}
        )
        console.print(f"  [{'green' if ok else 'dim'}]Tunnel: {msg}[/{'green' if ok else 'dim'}]")
    except Exception as e:
        results.append({"action": "tunnel_down", "status": "error", "detail": str(e)})
        console.print(f"  [yellow]Tunnel teardown: {e}[/yellow]")

    # 2. Remove WireGuard local state
    try:
        from loft_cli.local.wireguard_store import _wg_host_dir

        wg_dir = _wg_host_dir(host_name)
        if wg_dir.exists():
            import shutil

            shutil.rmtree(wg_dir)
            results.append(
                {"action": "wireguard_state", "status": "ok", "detail": f"Removed {wg_dir}"}
            )
            console.print(f"  [green]WireGuard state: removed {wg_dir}[/green]")
        else:
            results.append(
                {"action": "wireguard_state", "status": "skipped", "detail": "No WG state found"}
            )
            console.print("  [dim]WireGuard state: none found[/dim]")
    except Exception as e:
        results.append({"action": "wireguard_state", "status": "error", "detail": str(e)})
        console.print(f"  [yellow]WireGuard state removal: {e}[/yellow]")

    # 3. Remove SSH conf.d entry
    try:
        from loft_cli.local.ssh_config import remove_ssh_conf_d

        remove_ssh_conf_d(host_name)
        results.append(
            {
                "action": "ssh_config",
                "status": "ok",
                "detail": f"Removed SSH config for {host_name}",
            }
        )
        console.print(f"  [green]SSH config: removed conf.d entry for {host_name}[/green]")
    except Exception as e:
        results.append({"action": "ssh_config", "status": "error", "detail": str(e)})
        console.print(f"  [yellow]SSH config removal: {e}[/yellow]")

    # 4. Mark inventory record as decommissioned
    try:
        import os

        from loft_cli.local.inventory_db import InventoryDB
        from loft_cli_core.registry.local_paths import get_local_paths

        db_path = os.environ.get("LOFT_CLI_DB_PATH") or str(get_local_paths().inventory_db_path)
        db = InventoryDB(db_path=db_path)
        try:
            db.open()
            server = db.get_server(host_name)
            if server:
                db.upsert_server(
                    id=host_name,
                    name=server.get("name", host_name),
                    address=server.get("address", ""),
                    bootstrap_status="decommissioned",
                    os_family=server.get("os_family", ""),
                    ssh_alias=server.get("ssh_alias", ""),
                    ssh_host=server.get("ssh_host", ""),
                    ssh_user=server.get("ssh_user", ""),
                    ssh_port=server.get("ssh_port"),
                    ssh_identity_file=server.get("ssh_identity_file", ""),
                    wireguard_enabled=False,
                    wireguard_interface=server.get("wireguard_interface", ""),
                    wireguard_address=server.get("wireguard_address", ""),
                )
                results.append(
                    {
                        "action": "inventory",
                        "status": "ok",
                        "detail": f"Marked {host_name} as decommissioned",
                    }
                )
                console.print(f"  [green]Inventory: marked {host_name} as decommissioned[/green]")
            else:
                results.append(
                    {
                        "action": "inventory",
                        "status": "skipped",
                        "detail": "No inventory record found",
                    }
                )
                console.print("  [dim]Inventory: no record found[/dim]")
        finally:
            db.close()
    except Exception as e:
        results.append({"action": "inventory", "status": "error", "detail": str(e)})
        console.print(f"  [yellow]Inventory update: {e}[/yellow]")

    return results
