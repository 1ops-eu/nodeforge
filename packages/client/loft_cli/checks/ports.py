"""TCP port connectivity check."""

from __future__ import annotations

import socket

from loft_cli.checks.ssh import CheckResult


def check_port_open(host: str, port: int, timeout: int = 5) -> CheckResult:
    """Return True if the TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return CheckResult(
                passed=True,
                check_type="port_open",
                message=f"Port {host}:{port} is open",
            )
    except (TimeoutError, ConnectionRefusedError, OSError) as e:
        return CheckResult(
            passed=False,
            check_type="port_open",
            message=f"Port {host}:{port} is not reachable: {e}",
        )
