"""SSH connectivity check — used by the GATE step."""

from __future__ import annotations

import time

from pydantic import BaseModel


class CheckResult(BaseModel):
    passed: bool
    check_type: str
    message: str
    details: dict = {}


def check_ssh_reachable(
    host: str,
    port: int,
    user: str,
    key_path: str | None = None,
    password: str | None = None,
    timeout: int = 10,
    retries: int = 5,
    retry_delay: float = 1.0,
) -> CheckResult:
    """Test SSH connectivity. This is what GATE step 'verify_admin_login_on_new_port' calls.

    Retries up to ``retries`` times with ``retry_delay`` seconds between attempts.
    This handles the brief window after ``systemctl reload ssh`` where the daemon
    has acknowledged the reload but has not yet re-bound to its port.
    """
    from loft_cli.runtime.ssh import SSHSession

    last_message = f"SSH login failed: {user}@{host}:{port}"
    for attempt in range(retries):
        session = SSHSession(
            host=host,
            user=user,
            port=port,
            password=password,
            key_path=key_path,
            connect_timeout=timeout,
        )
        try:
            ok = session.test_connection()
            if ok:
                return CheckResult(
                    passed=True,
                    check_type="ssh_reachable",
                    message=f"SSH login succeeded: {user}@{host}:{port}",
                )
            last_message = f"SSH login failed: {user}@{host}:{port}"
        except Exception as e:
            last_message = f"SSH connection error: {e}"
        finally:
            session.close()

        if attempt < retries - 1:
            time.sleep(retry_delay)

    return CheckResult(
        passed=False,
        check_type="ssh_reachable",
        message=last_message,
    )
