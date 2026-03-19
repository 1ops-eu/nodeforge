# nodeforge/checks/ — Runtime Verification Checks

This package provides check functions used by the executor during plan execution. Each check takes a connection or parameters and returns a `CheckResult` with pass/fail status.

---

## Files

| File | Purpose |
|---|---|
| `ssh.py` | SSH connectivity check — used by GATE steps for lockout prevention. Retries up to 5 times with 1-second delay to handle the brief sshd reload window. |
| `container.py` | Docker container running check — verifies a container is in `Running` state via `docker inspect`. |
| `http.py` | HTTP health check — verifies an endpoint returns the expected status code (uses `requests`). |
| `postgres.py` | PostgreSQL readiness check — runs `pg_isready` on the remote host. |
| `nginx.py` | Nginx readiness check — verifies config validity via `nginx -t` and that the service is active. |
| `wireguard.py` | WireGuard interface check — verifies the interface is up via `wg show`. |
| `ports.py` | TCP port connectivity check — attempts a socket connection to verify a port is open. |
| `__init__.py` | Empty package marker |

---

## CheckResult Model

All check functions return a `CheckResult` (defined in `ssh.py`):

```python
class CheckResult(BaseModel):
    passed: bool          # True if the check succeeded
    check_type: str       # e.g., "ssh_reachable", "container_running", "http"
    message: str          # Human-readable result description
    details: dict = {}    # Optional additional data
```

---

## SSH Check (`ssh.py`)

`check_ssh_reachable(host, port, user, key_path, password, timeout, retries, retry_delay) -> CheckResult`

This is the critical check used by the GATE steps that enforce SSH lockout prevention:

- Creates a temporary `SSHSession` and calls `test_connection()`
- Passes the `timeout` parameter through to `SSHSession` as `connect_timeout`, ensuring that SSH attempts to firewalled ports fail fast (default 10 seconds) instead of hanging at the TCP default (~30 seconds)
- Retries up to 5 times with 1-second delays to handle the brief window after `systemctl reload ssh` where the daemon has acknowledged the reload but hasn't re-bound to its port
- The session is closed after each attempt to avoid connection pooling issues

---

## Usage

Checks are invoked by the executor, not called directly by users. The executor's `_execute_gate()` method parses the step command (e.g., `ssh_check:host:port:user`) and calls the appropriate check function. Other check types (`container_running`, `http`, `postgres_ready`, etc.) are called from `_execute_verify()`.

---

## Design Decisions

- **Retry with delay for SSH**: sshd reload has a brief unavailability window; retrying prevents false gate failures.
- **Pydantic CheckResult**: consistent structure across all check types; easy to serialize for logging.
- **Stateless functions**: each check creates its own connection/session and cleans up — no shared state between checks.
