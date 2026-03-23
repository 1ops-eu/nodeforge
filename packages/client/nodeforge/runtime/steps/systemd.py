"""Shell command builders and unit file renderers for systemd kinds.

Used by both systemd_unit and systemd_timer planners.
"""

from __future__ import annotations


def render_service_unit(
    *,
    description: str,
    exec_start: str,
    exec_stop: str | None = None,
    working_directory: str | None = None,
    user: str = "root",
    group: str = "root",
    restart: str = "on-failure",
    restart_sec: int = 5,
    after: list[str] | None = None,
    environment: dict[str, str] | None = None,
    environment_file: str | None = None,
    service_type: str = "simple",
    wanted_by: str = "multi-user.target",
) -> str:
    """Render a systemd .service unit file from structured parameters."""
    lines: list[str] = ["[Unit]"]
    lines.append(f"Description={description}")
    if after:
        lines.append(f"After={' '.join(after)}")
    lines.append("")

    lines.append("[Service]")
    lines.append(f"Type={service_type}")
    lines.append(f"ExecStart={exec_start}")
    if exec_stop:
        lines.append(f"ExecStop={exec_stop}")
    if working_directory:
        lines.append(f"WorkingDirectory={working_directory}")
    lines.append(f"User={user}")
    lines.append(f"Group={group}")
    lines.append(f"Restart={restart}")
    lines.append(f"RestartSec={restart_sec}")
    if environment:
        for key, value in sorted(environment.items()):
            lines.append(f"Environment={key}={value}")
    if environment_file:
        lines.append(f"EnvironmentFile={environment_file}")
    lines.append("")

    lines.append("[Install]")
    lines.append(f"WantedBy={wanted_by}")
    lines.append("")

    return "\n".join(lines)


def render_timer_unit(
    *,
    description: str,
    on_calendar: str,
    persistent: bool = True,
    accuracy_sec: str = "1min",
    unit: str | None = None,
    wanted_by: str = "timers.target",
) -> str:
    """Render a systemd .timer unit file from structured parameters."""
    lines: list[str] = ["[Unit]"]
    lines.append(f"Description={description}")
    lines.append("")

    lines.append("[Timer]")
    lines.append(f"OnCalendar={on_calendar}")
    if persistent:
        lines.append("Persistent=true")
    lines.append(f"AccuracySec={accuracy_sec}")
    if unit:
        lines.append(f"Unit={unit}")
    lines.append("")

    lines.append("[Install]")
    lines.append(f"WantedBy={wanted_by}")
    lines.append("")

    return "\n".join(lines)


def render_logrotate_config(
    *,
    name: str,
    path: str,
    rotate: int = 7,
    frequency: str = "daily",
    compress: bool = True,
    max_size: str = "",
) -> str:
    """Render a logrotate configuration file."""
    lines: list[str] = [f"{path} {{"]
    lines.append(f"    {frequency}")
    lines.append(f"    rotate {rotate}")
    lines.append("    missingok")
    lines.append("    notifempty")
    if compress:
        lines.append("    compress")
        lines.append("    delaycompress")
    if max_size:
        lines.append(f"    maxsize {max_size}")
    lines.append("    copytruncate")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def daemon_reload() -> str:
    return "systemctl daemon-reload"


def enable_unit(unit_name: str) -> str:
    return f"systemctl enable {unit_name}"


def enable_now_unit(unit_name: str) -> str:
    return f"systemctl enable --now {unit_name}"


def restart_unit(unit_name: str) -> str:
    return f"systemctl restart {unit_name}"


def is_active(unit_name: str) -> str:
    return f"systemctl is-active {unit_name}"
