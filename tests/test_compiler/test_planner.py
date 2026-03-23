"""Tests for the planner — critical SSH lockout prevention invariants."""

from nodeforge.compiler.normalizer import normalize
from nodeforge.compiler.planner import plan
from nodeforge_core.plan.models import StepScope
from nodeforge_core.specs.loader import load_spec


def _make_plan(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    return plan(ctx)


def test_plan_has_steps(bootstrap_yaml):
    p = _make_plan(bootstrap_yaml)
    assert len(p.steps) > 0


def test_plan_has_gate(bootstrap_yaml):
    """The plan must contain exactly one gate: verify_admin_login_on_new_port."""
    p = _make_plan(bootstrap_yaml)
    gates = [s for s in p.steps if s.gate]
    assert len(gates) == 1
    assert gates[0].id == "verify_admin_login_on_new_port"


def test_disable_root_depends_on_gate(bootstrap_yaml):
    """CRITICAL: disable_root_login must depend on the gate step index."""
    p = _make_plan(bootstrap_yaml)

    gate = next(s for s in p.steps if s.gate)
    disable_root = next(s for s in p.steps if s.id == "disable_root_login")

    assert gate.index in disable_root.depends_on, (
        f"disable_root_login (step {disable_root.index}) must depend on gate "
        f"(step {gate.index}), but depends_on={disable_root.depends_on}"
    )


def test_disable_password_auth_depends_on_gate(bootstrap_yaml):
    """CRITICAL: disable_password_auth must depend on the gate step index."""
    p = _make_plan(bootstrap_yaml)

    gate = next(s for s in p.steps if s.gate)
    disable_pw = next(s for s in p.steps if s.id == "disable_password_auth")

    assert gate.index in disable_pw.depends_on, (
        f"disable_password_auth (step {disable_pw.index}) must depend on gate "
        f"(step {gate.index}), but depends_on={disable_pw.depends_on}"
    )


def test_gate_comes_before_hardening(bootstrap_yaml):
    """Gate index must be less than disable_root_login and disable_password_auth."""
    p = _make_plan(bootstrap_yaml)
    gate = next(s for s in p.steps if s.gate)
    disable_root = next(s for s in p.steps if s.id == "disable_root_login")
    disable_pw = next(s for s in p.steps if s.id == "disable_password_auth")

    assert gate.index < disable_root.index
    assert gate.index < disable_pw.index


def test_local_steps_come_after_remote(bootstrap_yaml):
    """All local steps must have higher indices than all remote steps."""
    p = _make_plan(bootstrap_yaml)
    remote_steps = [s for s in p.steps if s.scope == StepScope.REMOTE]
    local_steps = [s for s in p.steps if s.scope == StepScope.LOCAL]

    if not local_steps:
        return  # no local steps in this spec, skip

    max_remote_idx = max(s.index for s in remote_steps) if remote_steps else -1
    min_local_idx = min(s.index for s in local_steps)
    assert min_local_idx > max_remote_idx


def test_plan_hashes_are_set(bootstrap_yaml):
    p = _make_plan(bootstrap_yaml)
    assert p.spec_hash
    assert p.plan_hash
    assert len(p.spec_hash) == 64  # sha256 hex


def test_step_indices_sequential(bootstrap_yaml):
    p = _make_plan(bootstrap_yaml)
    indices = [s.index for s in p.steps]
    assert indices == list(range(len(p.steps)))
