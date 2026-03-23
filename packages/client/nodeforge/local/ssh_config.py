"""Local SSH conf.d management.

SSH config fragments are written to:

    {ssh_conf_d_base}/{host_name}.conf

where ``ssh_conf_d_base`` defaults to ``~/.ssh/conf.d/nodeforge/`` but is
addon-overridable via ``register_local_paths()``.  A single glob Include:

    Include {ssh_conf_d_base}/*

is written once to ``~/.ssh/config`` and covers all fragments in the
directory — no per-file Include management needed.

Commercial clones that want a deeper folder structure (e.g.
``~/.ssh/conf.d/mycompany/project1/env/``) only need to call
``register_local_paths()`` in their addon's ``register()`` function; this
module never needs to be modified.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path


def _conf_d_base() -> Path:
    """Return the active SSH conf.d base directory (addon-overridable)."""
    from nodeforge_core.registry.local_paths import get_local_paths

    return get_local_paths().ssh_conf_d_base


def write_ssh_conf_d(
    host_name: str,
    address: str,
    user: str,
    port: int,
    identity_file: str | None = None,
) -> Path:
    """Write {ssh_conf_d_base}/{host_name}.conf and return the path.

    Idempotent: overwrites own file on re-run.
    """
    base = _conf_d_base()
    base.mkdir(parents=True, exist_ok=True)
    base.chmod(0o700)

    conf_file = base / f"{host_name}.conf"

    lines = [
        f"# nodeforge managed: {host_name}",
        f"Host {host_name}",
        f"  HostName {address}",
        f"  User {user}",
        f"  Port {port}",
    ]
    if identity_file:
        expanded = str(Path(identity_file).expanduser())
        lines.append(f"  IdentityFile {expanded}")
        lines.append("  IdentitiesOnly yes")

    content = "\n".join(lines) + "\n"
    conf_file.write_text(content, encoding="utf-8")
    conf_file.chmod(0o600)
    return conf_file


def remove_ssh_conf_d(host_name: str) -> None:
    """Remove the conf.d file for a host."""
    conf_file = _conf_d_base() / f"{host_name}.conf"
    if conf_file.exists():
        conf_file.unlink()


def ensure_include(config_path: Path) -> None:
    """Ensure 'Include {ssh_conf_d_base}/*' exists in ~/.ssh/config.

    Writes a single glob Include that covers all fragments in the nodeforge
    conf.d directory.  Written once, never removed — safe to call repeatedly.
    """
    config = config_path.expanduser()
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    config.chmod(0o600)

    include_line = f"Include {_conf_d_base()}/*"
    existing_lines = config.read_text(encoding="utf-8").splitlines()
    if include_line not in existing_lines:
        with open(config, "a", encoding="utf-8") as f:
            f.write(f"{include_line}\n")


def backup_ssh_config(config_path: Path) -> Path | None:
    """Create a timestamped backup of ~/.ssh/config if it exists."""
    config = config_path.expanduser()
    if not config.exists():
        return None
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = config.parent / f"config.{ts}.bak"
    shutil.copy2(config, backup)
    backup.chmod(0o600)
    return backup
