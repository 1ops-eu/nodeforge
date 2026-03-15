"""Phase 2: Fill defaults and resolve computed values from spec."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Union

from nodeforge.specs.bootstrap_schema import BootstrapSpec
from nodeforge.specs.service_schema import ServiceSpec
from nodeforge.utils.files import expand_path

AnySpec = Union[BootstrapSpec, ServiceSpec]


@dataclass
class NormalizedContext:
    """Resolved values derived from the spec during normalization."""
    spec: AnySpec

    # Bootstrap-specific resolved values
    pubkey_contents: list[str] = field(default_factory=list)
    wireguard_private_key: str = ""
    ssh_conf_d_path: Path | None = None
    db_path: Path | None = None
    login_key_path: Path | None = None
    login_password: str | None = None
    admin_key_path: Path | None = None


def normalize(spec) -> NormalizedContext:
    """Resolve all paths, read key files, compute derived values."""
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge.registry import load_addons, get_normalizer
    load_addons()

    ctx = NormalizedContext(spec=spec)

    normalizer = get_normalizer(spec.kind)
    if normalizer is None:
        raise RuntimeError(f"No normalizer registered for spec kind '{spec.kind}'")
    normalizer(spec, ctx)

    return ctx


def _normalize_bootstrap(spec: BootstrapSpec, ctx: NormalizedContext) -> None:
    # Resolve login private key path
    ctx.login_key_path = expand_path(spec.login.private_key)
    ctx.login_password = spec.login.password or None

    # Derive admin private key path from the first .pub entry in pubkeys
    for pk_str in spec.admin_user.pubkeys:
        pk_path = expand_path(pk_str)
        if pk_path.suffix == ".pub":
            candidate = pk_path.with_suffix("")
            if candidate.exists():
                ctx.admin_key_path = candidate
                break

    # Read pubkey file contents (missing files are stored as placeholder for plan/docs)
    for pk_path_str in spec.admin_user.pubkeys:
        pk_path = expand_path(pk_path_str)
        if pk_path.exists():
            ctx.pubkey_contents.append(pk_path.read_text(encoding="utf-8").strip())
        else:
            ctx.pubkey_contents.append(f"<key not found: {pk_path}>")

    # Read WireGuard private key
    if spec.wireguard.enabled and spec.wireguard.private_key_file:
        wg_key_path = expand_path(spec.wireguard.private_key_file)
        if wg_key_path.exists():
            ctx.wireguard_private_key = wg_key_path.read_text(encoding="utf-8").strip()
        else:
            ctx.wireguard_private_key = f"<key not found: {wg_key_path}>"

    # Compute SSH conf.d path
    ssh_conf_d_base = Path("~/.ssh/conf.d").expanduser()
    ctx.ssh_conf_d_path = ssh_conf_d_base / f"{spec.host.name}.conf"

    # If host_alias not set, default to host name
    if not spec.local.ssh_config.host_alias:
        spec.local.ssh_config.host_alias = spec.host.name

    # Resolve inventory db path and key
    inv = spec.local.inventory
    ctx.db_path = expand_path(inv.db_path)


def _normalize_service(spec: ServiceSpec, ctx: NormalizedContext) -> None:
    # Resolve login key
    ctx.login_key_path = expand_path(spec.login.private_key)
    ctx.login_password = spec.login.password or None

    # Resolve inventory
    inv = spec.local.inventory
    ctx.db_path = expand_path(inv.db_path)

    # Resolve postgres role password from env
    if spec.postgres and spec.postgres.create_role:
        role = spec.postgres.create_role
        if role.password_env:
            pw = os.environ.get(role.password_env, "")
            role.password_env = pw  # store resolved value
