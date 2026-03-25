"""WireGuard tunnel management — up, down, status.

Manages client-side WireGuard tunnels using ``wg-quick``. Each host gets a
uniquely-named interface (``wg-{host}``) so multiple tunnels can coexist
(e.g. Vagrant + Hetzner + production simultaneously).

State discovery uses ``~/.wg/nodeforge/{host}/`` directories created by
``wireguard_store.save_wireguard_state()``.

Requires ``wg-quick`` (part of ``wireguard-tools``) and ``sudo`` access.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _wg_state_base() -> Path:
    """Return the WireGuard state base directory."""
    from nodeforge_core.registry.local_paths import get_local_paths

    return get_local_paths().wg_state_base


def _interface_name(host_name: str) -> str:
    """Derive the client-side WireGuard interface name from the host name.

    Uses ``wg-{host}`` (truncated to 15 chars — Linux interface name limit).
    Server side always keeps ``wg0`` (it only has one tunnel).
    """
    raw = f"wg-{host_name}"
    return raw[:15]


def _host_dir(host_name: str) -> Path:
    """Return the per-host WireGuard state directory."""
    return _wg_state_base() / host_name


def _client_conf_path(host_name: str) -> Path:
    """Return the path to the client wg-quick config file."""
    return _host_dir(host_name) / "client.conf"


def tunnel_up(host_name: str) -> tuple[bool, str]:
    """Bring up the WireGuard tunnel for a host.

    Creates a temporary config file named after the interface so
    ``wg-quick`` creates the correctly-named interface.

    Returns (success: bool, message: str).
    """
    conf_path = _client_conf_path(host_name)
    if not conf_path.exists():
        return False, f"No client.conf found at {conf_path} — run nodeforge apply first"

    iface = _interface_name(host_name)

    # Check if the interface is already active
    if _is_interface_active(iface):
        return True, f"Tunnel {iface} is already active"

    # Create a temporary config named after the interface so wg-quick
    # creates the right interface name. wg-quick derives the interface
    # name from the config file stem.
    iface_conf = conf_path.parent / f"{iface}.conf"
    try:
        # Copy client.conf content to {iface}.conf
        iface_conf.write_text(conf_path.read_text(encoding="utf-8"), encoding="utf-8")
        iface_conf.chmod(0o600)

        result = subprocess.run(
            ["sudo", "wg-quick", "up", str(iface_conf)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, f"Tunnel {iface} is up"
        else:
            stderr = result.stderr.strip()
            return False, f"wg-quick up failed (exit {result.returncode}): {stderr}"
    except FileNotFoundError:
        return False, "wg-quick not found — install wireguard-tools"
    except subprocess.TimeoutExpired:
        return False, "wg-quick up timed out (30s)"
    except PermissionError:
        return False, "sudo access required for wg-quick"
    finally:
        # Clean up the temporary interface config
        if iface_conf.exists() and iface_conf != conf_path:
            iface_conf.unlink(missing_ok=True)


def tunnel_down(host_name: str) -> tuple[bool, str]:
    """Tear down the WireGuard tunnel for a host.

    Creates a temporary config file (mirroring ``tunnel_up``) so
    ``wg-quick down`` can find the interface configuration.  If
    ``client.conf`` is missing (e.g. host already removed), falls back
    to ``ip link del`` as a last resort.

    Returns (success: bool, message: str).
    """
    iface = _interface_name(host_name)

    if not _is_interface_active(iface):
        return True, f"Tunnel {iface} is not active"

    conf_path = _client_conf_path(host_name)
    iface_conf = conf_path.parent / f"{iface}.conf" if conf_path.exists() else None

    try:
        # Primary path: use wg-quick down with a temp config file
        if iface_conf is not None:
            iface_conf.write_text(conf_path.read_text(encoding="utf-8"), encoding="utf-8")
            iface_conf.chmod(0o600)
            result = subprocess.run(
                ["sudo", "wg-quick", "down", str(iface_conf)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, f"Tunnel {iface} is down"
            # wg-quick failed — fall through to ip link del

        # Fallback: delete the interface directly
        result = subprocess.run(
            ["sudo", "ip", "link", "del", iface],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, f"Tunnel {iface} torn down (ip link del fallback)"
        stderr = result.stderr.strip()
        return False, f"Failed to tear down {iface}: {stderr}"
    except FileNotFoundError:
        return False, "wg-quick not found — install wireguard-tools"
    except subprocess.TimeoutExpired:
        return False, "wg-quick down timed out (30s)"
    except PermissionError:
        return False, "sudo access required for wg-quick"
    finally:
        if iface_conf is not None and iface_conf.exists() and iface_conf != conf_path:
            iface_conf.unlink(missing_ok=True)


def tunnel_status() -> list[dict]:
    """List all known hosts with their WireGuard tunnel status.

    Scans ``{wg_state_base}/*/metadata.json`` for host info and
    cross-references with active interfaces via ``wg show``.

    Returns a list of dicts with keys:
        host_name, interface, endpoint, vpn_ip, peer_address, active, deployed_at
    """
    base = _wg_state_base()
    if not base.exists():
        return []

    # Get list of active WireGuard interfaces
    active_interfaces = _get_active_interfaces()

    hosts = []
    for host_dir in sorted(base.iterdir()):
        if not host_dir.is_dir():
            continue

        metadata_path = host_dir / "metadata.json"
        if not metadata_path.exists():
            continue

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        host_name = host_dir.name
        iface = _interface_name(host_name)
        vpn_ip = metadata.get("address", "").split("/")[0]

        hosts.append(
            {
                "host_name": host_name,
                "interface": iface,
                "endpoint": metadata.get("endpoint", ""),
                "vpn_ip": vpn_ip,
                "peer_address": metadata.get("peer_address", ""),
                "active": iface in active_interfaces,
                "deployed_at": metadata.get("deployed_at", ""),
            }
        )

    return hosts


def _is_interface_active(iface: str) -> bool:
    """Check if a WireGuard interface is currently active."""
    try:
        result = subprocess.run(
            ["sudo", "wg", "show", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        return False


def _get_active_interfaces() -> set[str]:
    """Return the set of active WireGuard interface names."""
    try:
        result = subprocess.run(
            ["sudo", "wg", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return set(result.stdout.strip().split())
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        pass
    return set()
