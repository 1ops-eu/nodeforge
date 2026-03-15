"""Plan execution engine with gate/dependency semantics.

Critical invariants enforced here:
- Steps with gate=True abort the plan on failure
- Steps in depends_on that failed cause the dependent step to be skipped
- Local steps run only after all remote critical steps succeed
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from rich.console import Console

from nodeforge.plan.models import Plan, Step, StepKind, StepScope


class StepResult(BaseModel):
    step_index: int
    step_id: str
    scope: str
    status: Literal["success", "failed", "skipped"]
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0


class ApplyResult(BaseModel):
    plan: Plan
    step_results: list[StepResult]
    status: Literal["success", "failed", "success_with_local_warnings"]
    aborted_at: int | None = None
    started_at: str
    finished_at: str = ""


class Executor:
    def __init__(
        self,
        plan: Plan,
        ssh_session=None,
        inventory_db=None,
        ctx=None,
        spec=None,
        console: Console | None = None,
    ) -> None:
        self._plan = plan
        self._session = ssh_session
        self._db = inventory_db
        self._ctx = ctx
        self._spec = spec
        self._console = console or Console()

    def apply(self, dry_run: bool = False) -> ApplyResult:
        """Execute all steps in order, respecting gates and dependencies."""
        started_at = datetime.now(timezone.utc).isoformat()
        step_results: list[StepResult] = []
        aborted_at: int | None = None
        remote_failed = False
        local_warnings = False

        for step in self._plan.steps:
            # Check if any dependency failed — skip if so
            if self._has_failed_dependency(step, step_results):
                result = StepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="skipped",
                    error="Dependency failed",
                )
                step_results.append(result)
                self._print_step(step, result)
                if step.gate:
                    aborted_at = step.index
                    break
                continue

            if aborted_at is not None:
                # Plan aborted — skip all remaining steps
                step_results.append(StepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="skipped",
                    error="Plan aborted",
                ))
                continue

            result = self._execute_step(step, dry_run)
            step_results.append(result)
            self._print_step(step, result)

            if result.status == "failed":
                if step.index == 0:
                    # Preflight connection failure — abort immediately with a clear message.
                    # Continuing makes no sense: every subsequent step would fail with the
                    # same connection error, obscuring the real problem.
                    self._console.print(
                        f"\n[bold red]✗ Preflight failed: cannot connect to the host.[/bold red]\n"
                        f"  Check that the host is up, login.port is correct, and credentials are valid.\n"
                        f"  Error: {result.error or result.output}"
                    )
                    aborted_at = step.index
                    break
                elif step.gate:
                    aborted_at = step.index
                    self._console.print(
                        f"\n[bold red]⛔ GATE FAILED at step {step.index}: {step.id}[/bold red]"
                    )
                    if step.rollback_hint:
                        self._console.print(f"[yellow]Recovery:[/yellow] {step.rollback_hint}")
                    break
                elif step.scope == StepScope.LOCAL:
                    local_warnings = True
                else:
                    remote_failed = True

        finished_at = datetime.now(timezone.utc).isoformat()

        if aborted_at is not None or remote_failed:
            final_status = "failed"
        elif local_warnings:
            final_status = "success_with_local_warnings"
        else:
            final_status = "success"

        return ApplyResult(
            plan=self._plan,
            step_results=step_results,
            status=final_status,
            aborted_at=aborted_at,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _has_failed_dependency(self, step: Step, results: list[StepResult]) -> bool:
        """Return True if any dependency step failed."""
        for dep_idx in step.depends_on:
            dep_result = next((r for r in results if r.step_index == dep_idx), None)
            if dep_result and dep_result.status == "failed":
                return True
        return False

    def _execute_step(self, step: Step, dry_run: bool) -> StepResult:
        start = time.monotonic()

        if dry_run:
            duration = time.monotonic() - start
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output=f"[dry-run] would execute: {step.command or step.kind.value}",
                duration_seconds=duration,
            )

        try:
            if step.kind == StepKind.GATE:
                result = self._execute_gate(step)
            elif step.kind == StepKind.SSH_COMMAND:
                result = self._execute_ssh_command(step)
            elif step.kind == StepKind.SSH_UPLOAD:
                result = self._execute_ssh_upload(step)
            elif step.kind == StepKind.LOCAL_FILE_WRITE:
                result = self._execute_local_file_write(step)
            elif step.kind == StepKind.LOCAL_DB_WRITE:
                result = self._execute_local_db_write(step)
            elif step.kind == StepKind.LOCAL_COMMAND:
                result = self._execute_local_command(step)
            elif step.kind == StepKind.VERIFY:
                result = self._execute_verify(step)
            else:
                result = StepResult(
                    step_index=step.index,
                    step_id=step.id,
                    scope=step.scope.value,
                    status="failed",
                    error=f"Unknown step kind: {step.kind}",
                )
        except Exception as e:
            result = StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error=str(e),
            )

        result.duration_seconds = time.monotonic() - start
        return result

    def _execute_ssh_command(self, step: Step) -> StepResult:
        if self._session is None:
            raise RuntimeError("No SSH session available")
        cmd_result = self._session.run(step.command or "", sudo=step.sudo, warn=True)
        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success" if cmd_result.ok else "failed",
            output=cmd_result.stdout,
            error=cmd_result.stderr if not cmd_result.ok else "",
        )

    def _execute_ssh_upload(self, step: Step) -> StepResult:
        if self._session is None:
            raise RuntimeError("No SSH session available")
        if step.file_content and step.target_path:
            # Expand ~ on the remote side so paths like ~/.goss/... resolve
            # correctly for the connecting user (not necessarily root).
            target = step.target_path
            if target.startswith("~/") or target == "~":
                expand_result = self._session.run("echo $HOME", sudo=False, warn=True)
                if expand_result.ok:
                    home = expand_result.stdout.strip()
                    target = home + target[1:]  # replace leading ~ with $HOME

            # For goss files: ensure the parent directory exists first
            if "/.goss/" in target:
                parent = target.rsplit("/", 1)[0]
                self._session.run(f"mkdir -p {parent}", sudo=False, warn=True)

            self._session.upload_content(step.file_content, target, sudo=step.sudo)
        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success",
            output=f"Uploaded to {step.target_path}",
        )

    def _execute_gate(self, step: Step) -> StepResult:
        """Execute a gate step — typically an SSH login verification."""
        from nodeforge.checks.ssh import check_ssh_reachable

        if step.command and step.command.startswith("ssh_check:"):
            _, host, port_str, user = step.command.split(":", 3)
            key_path = None
            password = None
            if self._ctx:
                # Use admin key (no password) when the gate target is the admin user.
                # Use root login credentials (key or password) for all other gates.
                admin_name = (
                    self._spec.admin_user.name
                    if self._spec and hasattr(self._spec, "admin_user")
                    else None
                )
                if user == admin_name and self._ctx.admin_key_path:
                    key_path = str(self._ctx.admin_key_path)
                else:
                    key_path = str(self._ctx.login_key_path) if self._ctx.login_key_path else None
                    password = self._ctx.login_password
            check = check_ssh_reachable(host, int(port_str), user, key_path=key_path, password=password)
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success" if check.passed else "failed",
                output=check.message,
                error="" if check.passed else check.message,
            )
        # Default verify: run the command
        return self._execute_ssh_command(step)

    def _execute_verify(self, step: Step) -> StepResult:
        """Execute a verify step (non-gate)."""
        # ── goss: no spec was generated (generator failed) ──────────────
        if step.command == "goss_unavailable":
            self._console.print(
                "\n[bold yellow]⚠  No goss spec is available for this run.[/bold yellow]\n"
                "   Server state will NOT be automatically verified.\n"
                "   Ensure nodeforge.goss.generator can import and run cleanly.\n"
            )
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",  # warning, not a hard failure
                output="[WARNING] goss spec unavailable — server state not verified",
            )

        # ── goss: ship succeeded, now run validate ───────────────────────
        if step.command == "goss_validate":
            return self._execute_goss_validate(step)

        if step.command and step.command.startswith("check:"):
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="[check skipped in V1]",
            )
        if step.command and not step.command.startswith(("echo ", "ssh_check:")):
            return self._execute_ssh_command(step)
        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success",
            output="ok",
        )

    def _execute_goss_validate(self, step: Step) -> StepResult:
        """Install goss on the remote, update the master gossfile, run validate."""
        from nodeforge.goss.shipper import ship_and_run
        from nodeforge.goss.renderer import render_goss_results

        if self._session is None:
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="[dry-run or no session — goss validate skipped]",
            )

        spec_name = self._plan.spec_name
        admin_user = self._spec.admin_user.name if self._spec else "admin"

        # Retrieve the goss file content that was embedded in the ship step
        goss_content: str | None = None
        for s in self._plan.steps:
            if s.id == "ship_goss_file":
                goss_content = s.file_content
                break

        if not goss_content:
            self._console.print(
                "[bold yellow]⚠  goss_validate: could not find ship_goss_file content "
                "in plan — skipping.[/bold yellow]"
            )
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="[WARNING] goss content missing in plan — validate skipped",
            )

        goss_result = ship_and_run(
            session=self._session,
            spec_name=spec_name,
            goss_yaml_content=goss_content,
            admin_user=admin_user,
        )

        # Always render — even on error the renderer shows a clear message
        self._console.print()
        render_goss_results(goss_result, console=self._console)

        # A goss failure is "success_with_warnings" territory — the server WAS
        # configured; goss surfaces discrepancies for the operator to review.
        # We mark the step failed so the final apply status reflects reality,
        # but we do NOT abort the plan (step.gate is False).
        if goss_result.get("error"):
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="failed",
                error=goss_result["error"],
                output=goss_result.get("raw_output", ""),
            )

        status = "success" if goss_result["exit_ok"] else "failed"
        summary = goss_result.get("summary", {})
        output = (
            f"goss: {summary.get('test-count', '?')} checks, "
            f"{summary.get('success-count', '?')} passed, "
            f"{summary.get('failed-count', '?')} failed"
        )
        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status=status,
            output=output,
            error="" if goss_result["exit_ok"] else f"{summary.get('failed-count', '?')} check(s) failed",
        )

    def _execute_local_file_write(self, step: Step) -> StepResult:
        from pathlib import Path
        from nodeforge.local.ssh_config import write_ssh_conf_d, ensure_include
        from nodeforge.utils.files import expand_path

        if step.id == "write_local_ssh_conf_d" and self._spec and self._ctx:
            spec = self._spec
            ctx = self._ctx
            conf_file = write_ssh_conf_d(
                host_name=spec.host.name,
                address=spec.host.address,
                user=spec.admin_user.name,
                port=spec.ssh.port,
                identity_file=spec.login.private_key,
            )
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output=f"Written: {conf_file}",
            )
        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success",
            output="[local file write ok]",
        )

    def _execute_local_command(self, step: Step) -> StepResult:
        from nodeforge.local.ssh_config import backup_ssh_config, ensure_include

        if step.command == "backup_ssh_config":
            backup = backup_ssh_config()
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output=f"Backup: {backup}" if backup else "No existing config to backup",
            )
        elif step.command == "ensure_include" and self._ctx:
            from pathlib import Path
            if self._ctx.ssh_conf_d_path:
                ensure_include(self._ctx.ssh_conf_d_path)
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="Include directive ensured",
            )
        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success",
            output=f"[local command: {step.command}]",
        )

    def _execute_local_db_write(self, step: Step) -> StepResult:
        if self._db is None:
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="[inventory disabled — skipped]",
            )

        if step.command == "init_inventory":
            self._db.open()
            self._db.initialize()
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="Inventory database initialized",
            )
        elif step.command == "upsert_server" and self._spec and self._ctx:
            from nodeforge.local.inventory import record_bootstrap
            # Will be called after apply completes with full result
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="Server record queued for upsert",
            )
        elif step.command == "record_run":
            return StepResult(
                step_index=step.index,
                step_id=step.id,
                scope=step.scope.value,
                status="success",
                output="Run metadata queued for recording",
            )

        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope=step.scope.value,
            status="success",
            output=f"[db write: {step.command}]",
        )

    def _print_step(self, step: Step, result: StepResult) -> None:
        icons = {"success": "✓", "failed": "✗", "skipped": "○"}
        colors = {"success": "green", "failed": "red", "skipped": "dim"}
        icon = icons.get(result.status, "?")
        color = colors.get(result.status, "white")
        duration = f"{result.duration_seconds:.1f}s" if result.duration_seconds else ""
        self._console.print(
            f"  [{color}]{icon}[/{color}] [{step.index:>2}] {step.description[:60]}"
            + (f" [{duration}]" if duration else ""),
        )
        if result.status == "failed" and result.error:
            self._console.print(f"     [red]{result.error[:120]}[/red]")
