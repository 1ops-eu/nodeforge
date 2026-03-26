"""Tests for agent-side executor."""

from loft_cli_agent.executor import AgentExecutor
from loft_cli_core.plan.models import Plan, Step, StepKind, StepScope


def _make_plan(steps):
    return Plan(
        spec_name="test",
        spec_kind="test",
        target_host="localhost",
        spec_hash="test_hash",
        plan_hash="test_plan_hash",
        steps=steps,
        created_at="2026-01-01T00:00:00Z",
    )


def test_agent_executor_simple_command(tmp_path):
    """Agent executor can run a simple shell command."""
    state_path = tmp_path / "state.json"
    steps = [
        Step(
            id="echo_test",
            index=0,
            description="Echo test",
            scope=StepScope.REMOTE,
            kind=StepKind.SSH_COMMAND,
            command="echo hello",
            sudo=False,
        ),
    ]
    plan = _make_plan(steps)
    executor = AgentExecutor(plan=plan, state_path=state_path)
    result = executor.apply()

    assert result.status == "success"
    assert len(result.step_results) == 1
    assert result.step_results[0].status == "success"
    assert "hello" in result.step_results[0].output


def test_agent_executor_idempotent_skip(tmp_path):
    """Agent executor skips unchanged resources on re-apply."""
    state_path = tmp_path / "state.json"
    steps = [
        Step(
            id="echo_test",
            index=0,
            description="Echo test",
            scope=StepScope.REMOTE,
            kind=StepKind.SSH_COMMAND,
            command="echo hello",
            sudo=False,
        ),
    ]
    plan = _make_plan(steps)

    # First apply
    executor = AgentExecutor(plan=plan, state_path=state_path)
    result1 = executor.apply()
    assert result1.applied_count == 1
    assert result1.unchanged_count == 0

    # Second apply — should skip
    executor2 = AgentExecutor(plan=plan, state_path=state_path)
    result2 = executor2.apply()
    assert result2.unchanged_count == 1
    assert result2.applied_count == 0
    assert result2.step_results[0].status == "unchanged"


def test_agent_executor_gate_failure(tmp_path):
    """Agent executor aborts on gate failure."""
    state_path = tmp_path / "state.json"
    steps = [
        Step(
            id="failing_gate",
            index=0,
            description="Gate that fails",
            scope=StepScope.REMOTE,
            kind=StepKind.SSH_COMMAND,
            command="false",
            gate=True,
        ),
        Step(
            id="should_not_run",
            index=1,
            description="Should not run",
            scope=StepScope.REMOTE,
            kind=StepKind.SSH_COMMAND,
            command="echo unreachable",
        ),
    ]
    plan = _make_plan(steps)
    executor = AgentExecutor(plan=plan, state_path=state_path)
    result = executor.apply()

    assert result.status == "failed"
    assert result.aborted_at == 0


def test_agent_executor_file_write(tmp_path):
    """Agent executor can write files."""
    state_path = tmp_path / "state.json"
    target = tmp_path / "output" / "test.conf"
    steps = [
        Step(
            id="write_config",
            index=0,
            description="Write config",
            scope=StepScope.REMOTE,
            kind=StepKind.SSH_UPLOAD,
            file_content="server_name example.com;",
            target_path=str(target),
        ),
    ]
    plan = _make_plan(steps)
    executor = AgentExecutor(plan=plan, state_path=state_path)
    result = executor.apply()

    assert result.status == "success"
    assert target.read_text() == "server_name example.com;"


def test_agent_executor_skips_local_steps(tmp_path):
    """Agent executor skips LOCAL-scoped steps (those run on the client)."""
    state_path = tmp_path / "state.json"
    steps = [
        Step(
            id="remote_step",
            index=0,
            description="Remote",
            scope=StepScope.REMOTE,
            kind=StepKind.SSH_COMMAND,
            command="echo ok",
        ),
        Step(
            id="local_step",
            index=1,
            description="Local (should be skipped by agent)",
            scope=StepScope.LOCAL,
            kind=StepKind.LOCAL_COMMAND,
            command="echo local",
        ),
    ]
    plan = _make_plan(steps)
    executor = AgentExecutor(plan=plan, state_path=state_path)
    result = executor.apply()

    # Only the remote step should appear in results
    assert len(result.step_results) == 1
    assert result.step_results[0].step_id == "remote_step"
