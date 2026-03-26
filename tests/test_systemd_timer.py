"""Tests for systemd_timer kind -- schema, validation, and planning."""

import pytest
from pydantic import ValidationError

from loft_cli.runtime.steps.systemd import render_timer_unit
from loft_cli_core.specs.systemd_timer_schema import (
    SystemdTimerSpec,
    TimerConfig,
    TimerServiceConfig,
)
from loft_cli_core.specs.validators import has_errors, validate_systemd_timer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_systemd_timer_spec(**overrides) -> SystemdTimerSpec:
    base = {
        "kind": "systemd_timer",
        "meta": {"name": "test-st", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "timer": {
            "timer_name": "cleanup",
            "on_calendar": "*-*-* 02:00:00",
        },
        "service": {
            "exec_start": "/usr/local/bin/cleanup.sh",
        },
    }
    base.update(overrides)
    return SystemdTimerSpec.model_validate(base)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSystemdTimerSchema:
    def test_timer_config_defaults(self):
        cfg = TimerConfig(timer_name="t", on_calendar="daily")
        assert cfg.persistent is True
        assert cfg.accuracy_sec == "1min"

    def test_service_config_defaults(self):
        cfg = TimerServiceConfig(exec_start="/bin/x")
        assert cfg.user == "root"
        assert cfg.group == "root"

    def test_spec_round_trip(self):
        spec = _make_systemd_timer_spec()
        assert spec.kind == "systemd_timer"
        assert spec.timer.timer_name == "cleanup"
        assert spec.service.exec_start == "/usr/local/bin/cleanup.sh"

    def test_spec_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_systemd_timer_spec(extra_field="nope")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSystemdTimerValidation:
    def test_valid_spec(self):
        spec = _make_systemd_timer_spec()
        issues = validate_systemd_timer(spec)
        assert not has_errors(issues)

    def test_empty_timer_name(self):
        spec = _make_systemd_timer_spec(
            timer={"timer_name": "", "on_calendar": "daily"},
        )
        issues = validate_systemd_timer(spec)
        assert has_errors(issues)

    def test_empty_on_calendar(self):
        spec = _make_systemd_timer_spec(
            timer={"timer_name": "x", "on_calendar": ""},
        )
        issues = validate_systemd_timer(spec)
        assert has_errors(issues)

    def test_empty_exec_start(self):
        spec = _make_systemd_timer_spec(
            service={"exec_start": ""},
        )
        issues = validate_systemd_timer(spec)
        assert has_errors(issues)


# ---------------------------------------------------------------------------
# Step Helpers
# ---------------------------------------------------------------------------


class TestTimerStepHelpers:
    def test_render_timer_unit(self):
        content = render_timer_unit(
            description="Test Timer",
            on_calendar="*-*-* 03:00:00",
            persistent=True,
            accuracy_sec="1min",
        )
        assert "[Timer]" in content
        assert "OnCalendar=*-*-* 03:00:00" in content
        assert "Persistent=true" in content
        assert "AccuracySec=1min" in content
        assert "WantedBy=timers.target" in content

    def test_render_timer_no_persistent(self):
        content = render_timer_unit(
            description="Test",
            on_calendar="daily",
            persistent=False,
        )
        assert "Persistent" not in content


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


class TestSystemdTimerPlanning:
    def test_plan_generates_timer_steps(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_systemd_timer_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        assert p.spec_kind == "systemd_timer"
        step_ids = [s.id for s in p.steps]
        assert "write_service_cleanup" in step_ids
        assert "write_timer_cleanup" in step_ids
        assert "systemd_daemon_reload" in step_ids
        assert "enable_start_cleanup_timer" in step_ids
        assert "verify_cleanup_timer_active" in step_ids

    def test_plan_service_is_oneshot(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_systemd_timer_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        svc_step = next(s for s in p.steps if s.id == "write_service_cleanup")
        assert "Type=oneshot" in svc_step.file_content

    def test_plan_timer_has_on_calendar(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_systemd_timer_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        timer_step = next(s for s in p.steps if s.id == "write_timer_cleanup")
        assert "OnCalendar=*-*-* 02:00:00" in timer_step.file_content

    def test_plan_has_inventory_steps(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_systemd_timer_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        inv_steps = [s for s in p.steps if "inventory" in s.tags]
        assert len(inv_steps) == 3
