"""Local WireGuard state storage.

After a successful WireGuard bootstrap, nodeforge persists a local copy of
all key material and configuration under:

    {wg_state_base}/{host_name}/
        private.key   — the Curve25519 private key (mode 0600)
        public.key    — the derived public key (mode 0644)
        wg0.conf      — exact wg-quick config that was deployed (mode 0600)
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
    interface: str,
    address: str,
    endpoint: str,
    allowed_ips: list[str],
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
        Base64-encoded Curve25519 private key (contents of private_key_file).
    public_key:
        Derived public key (populated by the normalizer via PyNaCl).
    wg_conf_content:
        Exact string that was uploaded to ``/etc/wireguard/{interface}.conf``
        on the remote server.
    interface:
        WireGuard interface name (e.g. ``wg0``).
    address:
        Interface CIDR address (e.g. ``10.10.0.1/24``).
    endpoint:
        Peer endpoint (e.g. ``192.168.56.10:51820``).
    allowed_ips:
        List of allowed IP CIDRs for the peer.
    persistent_keepalive:
        Keepalive interval in seconds.

    Returns
    -------
    Path
        The per-host directory that was created/updated.
    """
    host_dir = _wg_host_dir(host_name)
    ensure_dir(host_dir, mode=0o700)

    # private key — readable only by owner
    _write(host_dir / "private.key", private_key + "\n", mode=0o600)

    # public key — not secret
    _write(host_dir / "public.key", public_key + "\n", mode=0o644)

    # deployed wg-quick config — contains private key, so restrict
    _write(host_dir / f"{interface}.conf", wg_conf_content, mode=0o600)

    # metadata — provenance + interface/peer summary
    metadata = {
        "host_name": host_name,
        "spec_name": spec_name,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "interface": interface,
        "address": address,
        "endpoint": endpoint,
        "allowed_ips": allowed_ips,
        "persistent_keepalive": persistent_keepalive,
        "public_key": public_key,
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
