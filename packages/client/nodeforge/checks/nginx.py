"""Nginx readiness check."""

from __future__ import annotations

from nodeforge.checks.ssh import CheckResult


def check_nginx_ready(session) -> CheckResult:
    """Check that nginx configuration is valid and service is running."""
    result = session.run("nginx -t 2>&1 && systemctl is-active nginx", warn=True)
    if result.ok:
        return CheckResult(
            passed=True,
            check_type="nginx_ready",
            message="Nginx is running with valid configuration",
        )
    return CheckResult(
        passed=False,
        check_type="nginx_ready",
        message=f"Nginx check failed: {result.stderr or result.stdout}",
    )
