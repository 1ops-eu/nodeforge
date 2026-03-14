"""WireGuard interface check."""
from __future__ import annotations

from nodeforge.checks.ssh import CheckResult


def check_wireguard_up(session, interface: str) -> CheckResult:
    """Check that the WireGuard interface is up via 'wg show'."""
    result = session.run(f"wg show {interface}", sudo=True, warn=True)
    if result.ok and interface in result.stdout:
        return CheckResult(
            passed=True,
            check_type="wireguard_up",
            message=f"WireGuard interface {interface} is up",
        )
    return CheckResult(
        passed=False,
        check_type="wireguard_up",
        message=f"WireGuard interface {interface} is not up: {result.stderr}",
    )
