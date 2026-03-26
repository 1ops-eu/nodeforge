"""HTTP health check."""

from __future__ import annotations

from loft_cli.checks.ssh import CheckResult


def check_http(url: str, expect_status: int = 200, timeout: int = 10) -> CheckResult:
    """Check that an HTTP endpoint returns the expected status code."""
    try:
        import requests

        response = requests.get(url, timeout=timeout)
        if response.status_code == expect_status:
            return CheckResult(
                passed=True,
                check_type="http",
                message=f"HTTP {url} returned {response.status_code}",
            )
        return CheckResult(
            passed=False,
            check_type="http",
            message=f"HTTP {url} returned {response.status_code}, expected {expect_status}",
        )
    except Exception as e:
        return CheckResult(
            passed=False,
            check_type="http",
            message=f"HTTP check failed for {url}: {e}",
        )
