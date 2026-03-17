"""Local WireGuard state storage.

After a successful WireGuard bootstrap, nodeforge persists a local copy of
all key material and configuration under:

    {wg_state_base}/{host_name}/
        private.key   — server Curve25519 private key (mode 0600)
        public.key    — server public key derived via PyNaCl (mode 0644)
        wg0.conf      — server wg-quick config deployed to remote (mode 0600)
        client.key    — auto-generated client private key (mode 0600)
        client.conf   — client wg-quick config for local use (mode 0600)
        metadata.json — interface details, peer config, deployment provenance

The base directory is addon-overridable via ``register_local_paths()``, so
commercial clones can use a deeper nested structure without touching this file:

    register_local_paths(LocalPathsConfig(
        wg_state_base=Path("~/.wg/mycompany/project1/").expanduser(),
    ))
    # → ~/.wg/mycompany/project1/{host_name}/private.key  etc.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from nodeforge.utils.files import ensure_dir


def _wg_host_dir(host_name: str) -> Path:
    """Return the per-host WireGuard state directory (not yet created)."""
    from nodeforge.registry.local_paths import get_local_paths

    return get_local_paths().wg_state_base / host_name


def save_wireguard_state(
    *,
    host_name: str,
    spec_name: str,
    private_key: str,
    public_key: str,
    wg_conf_content: str,
    client_private_key: str,
    client_public_key: str,
    client_conf_content: str,
    interface: str,
    address: str,
    endpoint: str,
    peer_address: str,
    persistent_keepalive: int,
) -> Path:
    """Persist WireGuard key material and config for one host.

    Parameters
    ----------
    host_name:
        Value of ``spec.host.name`` — used as the directory name.
    spec_name:
        Value of ``spec.meta.name`` — recorded in metadata for provenance.
    private_key:
        Base64-encoded Curve25519 server private key (contents of private_key_file).
    public_key:
        Derived server public key (populated by the normalizer via PyNaCl).
    wg_conf_content:
        Exact string uploaded to ``/etc/wireguard/{interface}.conf`` on the remote.
    client_private_key:
        Auto-generated client Curve25519 private key (base64).
    client_public_key:
        Derived client public key.
    client_conf_content:
        Client wg-quick config for local use (``wg-quick up client.conf``).
    interface:
        WireGuard interface name (e.g. ``wg0``).
    address:
        Server interface CIDR address (e.g. ``10.10.0.1/24``).
    endpoint:
        Server public endpoint (e.g. ``192.168.56.10:51820``).
    peer_address:
        Client/peer VPN IP CIDR (e.g. ``10.10.0.2/32``).
    persistent_keepalive:
        Keepalive interval in seconds.

    Returns
    -------
    Path
        The per-host directory that was created/updated.
    """
    host_dir = _wg_host_dir(host_name)
    ensure_dir(host_dir, mode=0o700)

    # Server private key — readable only by owner
    _write(host_dir / "private.key", private_key + "\n", mode=0o600)

    # Server public key — not secret
    _write(host_dir / "public.key", public_key + "\n", mode=0o644)

    # Server wg-quick config deployed to remote — contains private key
    _write(host_dir / f"{interface}.conf", wg_conf_content, mode=0o600)

    # Client private key — only write if not already present (stable peer identity)
    client_key_path = host_dir / "client.key"
    if not client_key_path.exists():
        _write(client_key_path, client_private_key + "\n", mode=0o600)

    # Client wg-quick config for local use — always refresh (server config may change)
    _write(host_dir / "client.conf", client_conf_content, mode=0o600)

    # metadata — provenance + interface/peer summary
    metadata = {
        "host_name": host_name,
        "spec_name": spec_name,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "interface": interface,
        "address": address,
        "endpoint": endpoint,
        "peer_address": peer_address,
        "persistent_keepalive": persistent_keepalive,
        "server_public_key": public_key,
        "client_public_key": client_public_key,
    }
    _write(
        host_dir / "metadata.json",
        json.dumps(metadata, indent=2) + "\n",
        mode=0o644,
    )

    return host_dir


def _write(path: Path, content: str, mode: int) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)
