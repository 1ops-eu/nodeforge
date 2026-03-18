"""Docker container status check."""

from __future__ import annotations

from nodeforge.checks.ssh import CheckResult


def check_container_running(session, name: str) -> CheckResult:
    """Check that a Docker container is in running state."""
    result = session.run(
        f"docker inspect --format='{{{{.State.Running}}}}' {name}",
        warn=True,
    )
    if result.ok and "true" in result.stdout.lower():
        return CheckResult(
            passed=True,
            check_type="container_running",
            message=f"Container '{name}' is running",
        )
    return CheckResult(
        passed=False,
        check_type="container_running",
        message=f"Container '{name}' is not running: {result.stderr or result.stdout}",
    )
