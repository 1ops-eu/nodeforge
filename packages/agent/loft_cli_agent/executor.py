"""Agent-side plan executor.

Executes plan steps locally on the managed server via subprocess,
rather than over SSH. Supports idempotent re-apply by tracking
resource state via content hashes.

Policy integration: when a policy.yaml is present at
``/etc/loft-cli/policy.yaml``, each step is evaluated against
the policy before execution.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from loft_cli_agent.state import (
    load_state,
    resource_changed,
    save_state,
    update_resource,
)
from loft_cli_core.agent_models import AgentApplyResult, AgentStepResult
from loft_cli_core.agent_paths import AGENT_CONFIG_DIR
from loft_cli_core.plan.models import Plan, Step, StepScope
from loft_cli_core.policy import PolicyAction, PolicyConfig, evaluate_step, load_policy
from loft_cli_core.state import RuntimeState
from loft_cli_core.utils.hashing import sha256_string

# Default policy.yaml location on the managed server.
_POLICY_PATH = AGENT_CONFIG_DIR / "policy.yaml"


class AgentExecutor:
    """Execute plan steps locally on the managed server."""

    def __init__(
        self,
        plan: Plan,
        state_path: Path | None = None,
        policy_path: Path | None = None,
        approval_tokens: list[str] | None = None,
    ) -> None:
        self._plan = plan
        self._state_path = state_path
        self._state: RuntimeState = load_state(state_path)
        self._policy: PolicyConfig | None = load_policy(
            policy_path if policy_path is not None else _POLICY_PATH
        )
        self._approval_tokens = {t.split(":")[0]: t for t in (approval_tokens or [])}

    def apply(self) -> AgentApplyResult:
        """Execute all remote/verify steps in order, with idempotent skip logic."""
        started_at = datetime.now(UTC).isoformat()
        step_results: list[AgentStepResult] = []
        aborted_at: int | None = None
        unchanged_count = 0
        applied_count = 0

        # Filter to remote and verify steps only — local steps run on the client
        steps = [s for s in self._plan.steps if s.scope in (StepScope.REMOTE, StepScope.VERIFY)]

        for step in steps:
            # Check dependencies
            if self._has_failed_dependency(step, step_results):
                result = AgentStepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="skipped",
                    error="Dependency failed",
                )
                step_results.append(result)
                if step.gate:
                    aborted_at = step.index
                    break
                continue

            if aborted_at is not None:
                step_results.append(
                    AgentStepResult(
                        step_index=step.index,
                        step_id=step.id,
                        scope=step.scope.value,
                        status="skipped",
                        error="Plan aborted",
                    )
                )
                continue

            # Idempotency check: skip unchanged resources
            content_hash = self._step_content_hash(step)
            is_always = "always" in step.tags or step.gate or step.scope == StepScope.VERIFY
            if not is_always and not resource_changed(self._state, step.id, content_hash):
                result = AgentStepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="unchanged",
                    output="Resource unchanged — skipped",
                )
                step_results.append(result)
                unchanged_count += 1
                continue

            # Policy check: evaluate step against policy rules
            decision = evaluate_step(self._policy, step.id, step.kind, step.tags)
            if decision.action == PolicyAction.DENY:
                result = AgentStepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="failed",
                    error=f"Denied by policy: {decision.reason}",
                )
                step_results.append(result)
                if step.gate:
                    aborted_at = step.index
                    break
                continue
            if decision.action == PolicyAction.REQUIRE_APPROVAL:
                token = self._approval_tokens.get(step.id)
                if token is None:
                    result = AgentStepResult(
                        step_index=step.index,
                        step_id=step.id,
                        scope=step.scope.value,
                        status="failed",
                        error=f"Requires approval: {decision.reason}. Pass --approval-token.",
                    )
                    step_results.append(result)
                    if step.gate:
                        aborted_at = step.index
                        break
                    continue

            # Execute the step
            result = self._execute_step(step)
            step_results.append(result)
            applied_count += 1

            # Update state tracking
            update_resource(
                self._state,
                step.id,
                content_hash,
                status="applied" if result.status == "success" else "failed",
            )

            if result.status == "failed" and (step.index == 0 or step.gate):
                aborted_at = step.index
                break

        # Update plan-level state
        from loft_cli_core import __version__

        self._state.version = __version__
        self._state.spec_hash = self._plan.spec_hash
        self._state.plan_hash = self._plan.plan_hash

        # Save state atomically
        save_state(self._state, self._state_path)

        finished_at = datetime.now(UTC).isoformat()
        any_failed = aborted_at is not None or any(r.status == "failed" for r in step_results)

        return AgentApplyResult(
            plan_hash=self._plan.plan_hash,
            spec_hash=self._plan.spec_hash,
            step_results=step_results,
            status="failed" if any_failed else "success",
            aborted_at=aborted_at,
            started_at=started_at,
            finished_at=finished_at,
            unchanged_count=unchanged_count,
            applied_count=applied_count,
        )

    def _has_failed_dependency(self, step: Step, results: list[AgentStepResult]) -> bool:
        for dep_idx in step.depends_on:
            dep_result = next((r for r in results if r.step_index == dep_idx), None)
            if dep_result and dep_result.status == "failed":
                return True
        return False

    def _step_content_hash(self, step: Step) -> str:
        """Compute a content hash for idempotency tracking."""
        parts = [step.id, step.command or "", step.file_content or "", step.target_path or ""]
        return sha256_string("".join(parts))

    def _execute_step(self, step: Step) -> AgentStepResult:
        """Execute a single step locally."""
        start = time.monotonic()
        try:
            if step.kind in ("ssh_command", "agent_command"):
                result = self._execute_command(step)
            elif step.kind in ("ssh_upload", "agent_file_write"):
                result = self._execute_file_write(step)
            elif step.kind == "gate":
                result = self._execute_gate(step)
            elif step.kind == "verify":
                result = self._execute_verify(step)
            elif step.kind in ("compose_health_check", "agent_compose_health"):
                result = self._execute_compose_health(step)
            else:
                result = AgentStepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="failed",
                    error=f"Unknown step kind: '{step.kind}'",
                )
        except Exception as e:
            result = AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error=str(e),
            )
        result.duration_seconds = time.monotonic() - start
        return result

    def _execute_command(self, step: Step) -> AgentStepResult:
        """Execute a shell command locally."""
        cmd = step.command or ""
        try:
            if step.sudo:
                proc = subprocess.run(
                    ["sudo", "bash", "-c", cmd],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            else:
                proc = subprocess.run(
                    ["bash", "-c", cmd],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success" if proc.returncode == 0 else "failed",
                output=proc.stdout,
                error=proc.stderr if proc.returncode != 0 else "",
            )
        except subprocess.TimeoutExpired:
            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error=f"Command timed out after 300s: {cmd[:80]}",
            )

    def _execute_file_write(self, step: Step) -> AgentStepResult:
        """Write file content directly to the filesystem."""
        if not step.file_content or not step.target_path:
            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error="Missing file_content or target_path",
            )

        target = Path(step.target_path)
        try:
            # Ensure parent directory exists
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(step.file_content, encoding="utf-8")

            if step.sudo:
                # Fix ownership to root when running as agent
                subprocess.run(
                    ["chown", "root:root", str(target)],
                    capture_output=True,
                    check=False,
                )
                subprocess.run(
                    ["chmod", "600", str(target)],
                    capture_output=True,
                    check=False,
                )

            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output=f"Written: {target}",
            )
        except Exception as e:
            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error=f"File write failed: {e}",
            )

    def _execute_gate(self, step: Step) -> AgentStepResult:
        """Execute a gate step — locally verify SSH or service accessibility."""
        # On the agent, gate checks can verify services are reachable locally
        if step.command and step.command.startswith("ssh_check:"):
            _, host, port_str, user = step.command.split(":", 3)
            import socket

            try:
                with socket.create_connection((host, int(port_str)), timeout=5):
                    return AgentStepResult(
                        step_index=step.index,
                        step_id=step.id,
                        scope=step.scope.value,
                        status="success",
                        output=f"Port {port_str} reachable on {host}",
                    )
            except OSError as e:
                return AgentStepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="failed",
                    error=f"Port {port_str} unreachable on {host}: {e}",
                )

        if step.command and step.command.startswith("http_check:"):
            return self._execute_http_check(step)

        # Fallback: run as command
        return self._execute_command(step)

    def _execute_verify(self, step: Step) -> AgentStepResult:
        """Execute a verification step locally."""
        if step.command and step.command.startswith("check:"):
            return self._execute_local_check(step)
        if step.command:
            return self._execute_command(step)
        return AgentStepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success",
            output="ok",
        )

    def _execute_local_check(self, step: Step) -> AgentStepResult:
        """Dispatch a postflight check locally."""
        parts = step.command.split(":", maxsplit=2) if step.command else []
        check_type = parts[1] if len(parts) > 1 else ""
        params = parts[2] if len(parts) > 2 else ""

        try:
            if check_type == "port_open":
                import socket

                host, port_str = params.split(":", 1)
                try:
                    with socket.create_connection((host, int(port_str)), timeout=5):
                        return self._check_result(step, True, f"Port {port_str} open on {host}")
                except OSError:
                    return self._check_result(step, False, f"Port {port_str} closed on {host}")

            elif check_type in ("postgres_ready", "nginx_ready", "wireguard_up"):
                # Run a simple local service check
                check_cmds = {
                    "postgres_ready": "pg_isready",
                    "nginx_ready": "nginx -t",
                    "wireguard_up": f"wg show {params}",
                }
                cmd = check_cmds[check_type]
                proc = subprocess.run(
                    ["bash", "-c", cmd], capture_output=True, text=True, timeout=10
                )
                return self._check_result(step, proc.returncode == 0, proc.stdout or proc.stderr)

            elif check_type == "container_running":
                proc = subprocess.run(
                    ["docker", "inspect", "-f", "{{.State.Running}}", params],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                running = proc.stdout.strip() == "true"
                return self._check_result(step, running, f"Container {params}: running={running}")

            elif check_type == "http":
                import urllib.request

                url, status_str = params.rsplit(":", 1)
                try:
                    resp = urllib.request.urlopen(url, timeout=10)  # noqa: S310
                    actual = resp.status
                    passed = actual == int(status_str)
                    return self._check_result(
                        step, passed, f"HTTP {url}: {actual} (expected {status_str})"
                    )
                except Exception as e:
                    return self._check_result(step, False, f"HTTP {url}: {e}")

            else:
                return self._check_result(step, False, f"Unknown check type: {check_type}")

        except Exception as exc:
            return self._check_result(step, False, f"Check error: {exc}")

    def _check_result(self, step: Step, passed: bool, message: str) -> AgentStepResult:
        return AgentStepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success" if passed else "failed",
            output=message if passed else "",
            error="" if passed else message,
        )

    def _execute_http_check(self, step: Step) -> AgentStepResult:
        """Execute an HTTP readiness check with retry loop."""
        import urllib.request

        # The URL may contain colons (e.g. http://host:port/), so parse
        # from the right: the trailing 4 fields are always integers.
        rest = step.command[len("http_check:") :]
        parts = rest.rsplit(":", 4)
        if len(parts) != 5:
            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error=f"Malformed http_check command: {step.command}",
            )

        url, status_str, retries_str, interval_str, timeout_str = parts
        expected = int(status_str)
        retries = int(retries_str)
        interval = int(interval_str)
        req_timeout = int(timeout_str)

        last_error = ""
        for attempt in range(retries):
            try:
                resp = urllib.request.urlopen(url, timeout=req_timeout)  # noqa: S310
                if resp.status == expected:
                    return AgentStepResult(
                        step_index=step.index,
                        step_id=step.id,
                        scope=step.scope.value,
                        status="success",
                        output=f"HTTP {url}: {resp.status} (expected {expected}) "
                        f"on attempt {attempt + 1}/{retries}",
                    )
                last_error = f"HTTP {url}: got {resp.status}, expected {expected}"
            except Exception as e:
                last_error = f"HTTP {url}: {e}"
            if attempt < retries - 1:
                time.sleep(interval)

        return AgentStepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="failed",
            error=f"HTTP check failed after {retries} attempts: {last_error}",
        )

    def _execute_compose_health(self, step: Step) -> AgentStepResult:
        """Poll docker compose ps for container health."""
        if not step.command or not step.command.startswith("compose_health:"):
            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error=f"Invalid compose_health command: {step.command}",
            )

        parts = step.command.split(":", 5)
        if len(parts) != 6:
            return AgentStepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error="Malformed compose_health command",
            )

        _, directory, compose_file, project_name, timeout_s, interval_s = parts
        timeout = int(timeout_s)
        interval = int(interval_s)
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            proc = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"cd {directory} && docker compose -f {compose_file} "
                    f"-p {project_name} ps --format json",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    # Parse container statuses
                    all_healthy = True
                    for line in proc.stdout.strip().splitlines():
                        container = json.loads(line)
                        health = container.get("Health", container.get("Status", ""))
                        if "healthy" not in health.lower() and "running" not in health.lower():
                            all_healthy = False
                            break
                    if all_healthy:
                        return AgentStepResult(
                            step_index=step.index,
                            step_id=step.id,
                            scope=step.scope.value,
                            status="success",
                            output=f"All containers healthy in {project_name}",
                        )
                except (json.JSONDecodeError, KeyError):
                    pass
            time.sleep(interval)

        return AgentStepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="failed",
            error=f"Health check timed out after {timeout}s for {project_name}",
        )
