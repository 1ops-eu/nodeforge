"""PostgreSQL readiness check."""

from __future__ import annotations

from nodeforge.checks.ssh import CheckResult


def check_postgres_ready(session) -> CheckResult:
    """Check that PostgreSQL is ready via pg_isready."""
    result = session.run("pg_isready", warn=True)
    if result.ok:
        return CheckResult(
            passed=True,
            check_type="postgres_ready",
            message="PostgreSQL is ready",
        )
    return CheckResult(
        passed=False,
        check_type="postgres_ready",
        message=f"PostgreSQL not ready: {result.stderr}",
    )
