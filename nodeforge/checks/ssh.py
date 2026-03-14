"""SSH connectivity check — used by the GATE step."""
from __future__ import annotations

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
) -> CheckResult:
    """Test SSH connectivity. This is what GATE step 'verify_admin_login_on_new_port' calls."""
    from nodeforge.runtime.ssh import SSHSession

    session = SSHSession(
        host=host,
        user=user,
        port=port,
        password=password,
        key_path=key_path,
    )
    try:
        ok = session.test_connection()
        if ok:
            return CheckResult(
                passed=True,
                check_type="ssh_reachable",
                message=f"SSH login succeeded: {user}@{host}:{port}",
            )
        else:
            return CheckResult(
                passed=False,
                check_type="ssh_reachable",
                message=f"SSH login failed: {user}@{host}:{port}",
            )
    except Exception as e:
        return CheckResult(
            passed=False,
            check_type="ssh_reachable",
            message=f"SSH connection error: {e}",
        )
    finally:
        session.close()
