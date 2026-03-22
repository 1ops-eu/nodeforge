"""Tests for the plan executor — gate semantics, dependency skipping, dry run."""

from __future__ import annotations

from nodeforge.runtime.executor import Executor, StepResult
from nodeforge_core.plan.models import Plan, Step, StepKind, StepScope


def _make_plan(steps: list[Step]) -> Plan:
    for i, s in enumerate(steps):
        s.index = i
    return Plan(
        spec_name="test",
        spec_kind="bootstrap",
        target_host="1.2.3.4",
        spec_hash="abc",
        plan_hash="def",
        steps=steps,
        created_at="2026-01-01T00:00:00Z",
    )


def _step(
    id,
    kind=StepKind.SSH_COMMAND,
    scope=StepScope.REMOTE,
    gate=False,
    depends_on=None,
    command="echo ok",
) -> Step:
    return Step(
        id=id,
        index=0,
        description=id,
        scope=scope,
        kind=kind,
        command=command,
        gate=gate,
        depends_on=depends_on or [],
    )


def test_dry_run_all_steps_succeed(mock_ssh_session):
    steps = [
        _step("step_a"),
        _step("step_b"),
        _step("step_c"),
    ]
    p = _make_plan(steps)
    executor = Executor(plan=p, ssh_session=mock_ssh_session)
    result = executor.apply(dry_run=True)

    assert result.status == "success"
    assert all(r.status == "success" for r in result.step_results)
    mock_ssh_session.run.assert_not_called()


def test_gate_failure_aborts_plan(mock_ssh_session, mocker):
    """When a gate step fails, subsequent steps must be skipped."""
    mock_ssh_session.run.return_value = mocker.MagicMock(
        ok=False, stdout="", stderr="timeout", return_code=1
    )

    gate_step = _step("gate", kind=StepKind.GATE, gate=True, command="ssh_check:1.2.3.4:2222:admin")
    after_gate = _step("after_gate", depends_on=[0])

    p = _make_plan([gate_step, after_gate])

    # Mock the gate check to fail
    mocker.patch(
        "nodeforge.checks.ssh.check_ssh_reachable",
        return_value=mocker.MagicMock(passed=False, message="connection refused"),
    )

    executor = Executor(plan=p, ssh_session=mock_ssh_session)
    result = executor.apply(dry_run=False)

    assert result.status == "failed"
    assert result.aborted_at == 0  # gate is step 0

    gate_result = next(r for r in result.step_results if r.step_id == "gate")
    assert gate_result.status == "failed"


def test_dependency_failure_skips_dependent(mock_ssh_session, mocker):
    """If step A fails, step B with depends_on=[A] should be skipped."""
    from nodeforge.runtime.ssh import CommandResult

    # Step 0 succeeds (preflight), step 1 fails, step 2 depends on step 1 → skipped
    ok = CommandResult(ok=True, stdout="ok", stderr="", return_code=0)
    fail = CommandResult(ok=False, stdout="", stderr="err", return_code=1)
    mock_ssh_session.run.side_effect = [ok, fail]

    preflight = _step("preflight")  # index 0 — succeeds
    step_a = _step("step_a")  # index 1 — fails
    step_b = _step("step_b", depends_on=[1])  # depends on step_a (index 1)

    p = _make_plan([preflight, step_a, step_b])
    executor = Executor(plan=p, ssh_session=mock_ssh_session)
    result = executor.apply(dry_run=False)

    result_b = next(r for r in result.step_results if r.step_id == "step_b")
    assert result_b.status == "skipped"


def test_local_step_failure_gives_warning_status(mock_ssh_session):
    """If a LOCAL step fails, status should be success_with_local_warnings (not failed)."""
    remote_step = _step("remote", scope=StepScope.REMOTE)
    local_step = _step(
        "local",
        scope=StepScope.LOCAL,
        kind=StepKind.LOCAL_COMMAND,
        command="fail_command",
    )

    p = _make_plan([remote_step, local_step])

    executor = Executor(plan=p, ssh_session=mock_ssh_session)
    # Make local command raise an exception

    def fail_local(step):

        return StepResult(
            step_index=step.index,
            step_id=step.id,
            scope="local",
            status="failed",
            error="local fail",
        )

    executor._execute_local_command = fail_local
    result = executor.apply(dry_run=False)

    assert result.status == "success_with_local_warnings"
