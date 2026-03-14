"""Local SSH conf.d management.

Adapted from vm_wizard/fab_infra/tasks/user/bootstrap_admin_user/bootstrap_admin_user.py
lines 218-246.

Pattern: write individual .conf files to ~/.ssh/conf.d/ and maintain
Include directives in ~/.ssh/config.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path


_CONF_D_BASE = Path("~/.ssh/conf.d").expanduser()
_SSH_CONFIG = Path("~/.ssh/config").expanduser()


def _conf_d_path(host_name: str, base: Path | None = None) -> Path:
    base = base or _CONF_D_BASE
    return base / f"{host_name}.conf"


def write_ssh_conf_d(
    host_name: str,
    address: str,
    user: str,
    port: int,
    identity_file: str | None = None,
    conf_d_base: Path | None = None,
) -> Path:
    """Write ~/.ssh/conf.d/{host_name}.conf and return the path.

    Idempotent: overwrites own file on re-run.
    """
    base = (conf_d_base or _CONF_D_BASE).expanduser()
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


def remove_ssh_conf_d(host_name: str, conf_d_base: Path | None = None) -> None:
    """Remove the conf.d file for a host."""
    conf_file = _conf_d_path(host_name, conf_d_base)
    if conf_file.exists():
        conf_file.unlink()


def ensure_include(
    conf_d_file: Path,
    config_path: Path | None = None,
) -> None:
    """Ensure 'Include {conf_d_file}' exists in ~/.ssh/config.

    Identical pattern to vm_wizard bootstrap_admin_user.py lines 237-246.
    """
    config = (config_path or _SSH_CONFIG).expanduser()
    config.parent.mkdir(parents=True, exist_ok=True)
    config.touch()
    config.chmod(0o600)

    include_line = f"Include {conf_d_file}"
    existing_lines = config.read_text(encoding="utf-8").splitlines()
    if include_line not in existing_lines:
        with open(config, "a", encoding="utf-8") as f:
            f.write(f"{include_line}\n")


def backup_ssh_config(config_path: Path | None = None) -> Path | None:
    """Create a timestamped backup of ~/.ssh/config if it exists."""
    config = (config_path or _SSH_CONFIG).expanduser()
    if not config.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config.parent / f"config.{ts}.bak"
    shutil.copy2(config, backup)
    backup.chmod(0o600)
    return backup
