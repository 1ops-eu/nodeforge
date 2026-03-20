"""Docker Compose container health check.

Polls ``docker compose ps --format json`` to verify all containers in a
compose project are healthy/running.  Used by the COMPOSE_HEALTH_CHECK
step kind.
"""

from __future__ import annotations

import json
import time

from nodeforge.checks.ssh import CheckResult


def check_compose_health(
    session,
    directory: str,
    compose_file: str,
    project_name: str,
    timeout: int = 120,
    interval: int = 5,
) -> CheckResult:
    """Poll compose container health until all are healthy or timeout expires.

    Args:
        session: SSH session for running remote commands.
        directory: Remote project directory.
        compose_file: Compose filename (relative to directory).
        project_name: Docker Compose project name.
        timeout: Maximum seconds to wait for healthy state.
        interval: Seconds between polls.

    Returns:
        CheckResult with per-container status in details.
    """
    deadline = time.monotonic() + timeout
    last_statuses: dict[str, str] = {}

    cmd = (
        f"bash -c 'cd {directory} && "
        f"docker compose -f {compose_file} -p {project_name} ps --format json'"
    )

    while time.monotonic() < deadline:
        result = session.run(cmd, sudo=True, warn=True)
        if not result.ok:
            time.sleep(interval)
            continue

        containers = _parse_compose_ps(result.stdout)
        if not containers:
            time.sleep(interval)
            continue

        last_statuses = {c["name"]: c["state"] for c in containers}

        # Check if all containers are in an acceptable state
        all_healthy = all(_is_container_healthy(c) for c in containers)

        if all_healthy:
            return CheckResult(
                passed=True,
                check_type="compose_health",
                message=f"All {len(containers)} containers healthy/running",
                details={"containers": last_statuses},
            )

        time.sleep(interval)

    # Timeout — report which containers are not healthy
    unhealthy = {
        name: state
        for name, state in last_statuses.items()
        if state.lower() not in ("running", "healthy")
    }
    return CheckResult(
        passed=False,
        check_type="compose_health",
        message=(
            f"Timeout after {timeout}s: {len(unhealthy)} container(s) not healthy: "
            + ", ".join(f"{n}={s}" for n, s in unhealthy.items())
        ),
        details={"containers": last_statuses, "unhealthy": unhealthy},
    )


def _parse_compose_ps(stdout: str) -> list[dict]:
    """Parse docker compose ps --format json output.

    Docker Compose v2 outputs one JSON object per line (NDJSON format).
    Earlier versions may output a JSON array.
    """
    containers: list[dict] = []
    stdout = stdout.strip()
    if not stdout:
        return containers

    # Try JSON array first
    if stdout.startswith("["):
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            pass

    # NDJSON: one JSON object per line
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            # Normalize field names (docker compose v2 uses different casing)
            containers.append(
                {
                    "name": obj.get("Name") or obj.get("name", "unknown"),
                    "state": obj.get("State") or obj.get("state", "unknown"),
                    "health": obj.get("Health") or obj.get("health", ""),
                    "service": obj.get("Service") or obj.get("service", ""),
                }
            )
        except json.JSONDecodeError:
            continue

    return containers


def _is_container_healthy(container: dict) -> bool:
    """Determine if a container is in an acceptable running state."""
    state = container.get("state", "").lower()
    health = container.get("health", "").lower()

    # If health check is defined, it must be "healthy"
    if health and health != "healthy":
        return False

    # State must be "running"
    return state == "running"
