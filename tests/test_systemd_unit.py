"""Tests for systemd_unit kind -- schema, validation, step helpers, and planning."""

import pytest
from pydantic import ValidationError

from nodeforge.runtime.steps.systemd import (
    daemon_reload,
    enable_unit,
    is_active,
    render_logrotate_config,
    render_service_unit,
    restart_unit,
)
from nodeforge_core.specs.systemd_unit_schema import (
    SystemdUnitConfig,
    SystemdUnitLoginBlock,
    SystemdUnitSpec,
)
from nodeforge_core.specs.validators import has_errors, validate_systemd_unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_systemd_unit_spec(**overrides) -> SystemdUnitSpec:
    base = {
        "kind": "systemd_unit",
        "meta": {"name": "test-su", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "unit": {
            "unit_name": "myapp",
            "exec_start": "/usr/local/bin/myapp serve",
        },
    }
    base.update(overrides)
    return SystemdUnitSpec.model_validate(base)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestSystemdUnitSchema:
    def test_unit_config_defaults(self):
        cfg = SystemdUnitConfig(unit_name="app", exec_start="/bin/app")
        assert cfg.user == "root"
        assert cfg.group == "root"
        assert cfg.restart == "on-failure"
        assert cfg.restart_sec == 5
        assert cfg.type == "simple"
        assert cfg.wanted_by == "multi-user.target"
        assert cfg.after == ["network.target"]

    def test_login_defaults(self):
        login = SystemdUnitLoginBlock()
        assert login.user == "admin"
        assert login.port == 2222

    def test_spec_round_trip(self):
        spec = _make_systemd_unit_spec()
        assert spec.kind == "systemd_unit"
        assert spec.unit.unit_name == "myapp"
        assert spec.logrotate is None

    def test_spec_with_logrotate(self):
        spec = _make_systemd_unit_spec(
            logrotate={"enabled": True, "path": "/var/log/app/*.log"}
        )
        assert spec.logrotate.enabled is True
        assert spec.logrotate.path == "/var/log/app/*.log"

    def test_spec_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_systemd_unit_spec(extra_field="nope")

    def test_unit_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_systemd_unit_spec(
                unit={"unit_name": "x", "exec_start": "/bin/x", "bogus": True}
            )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestSystemdUnitValidation:
    def test_valid_spec(self):
        spec = _make_systemd_unit_spec()
        issues = validate_systemd_unit(spec)
        assert not has_errors(issues)

    def test_empty_unit_name(self):
        spec = _make_systemd_unit_spec(
            unit={"unit_name": "", "exec_start": "/bin/x"}
        )
        issues = validate_systemd_unit(spec)
        assert has_errors(issues)

    def test_empty_exec_start(self):
        spec = _make_systemd_unit_spec(
            unit={"unit_name": "x", "exec_start": ""}
        )
        issues = validate_systemd_unit(spec)
        assert has_errors(issues)

    def test_invalid_restart(self):
        spec = _make_systemd_unit_spec(
            unit={"unit_name": "x", "exec_start": "/bin/x", "restart": "invalid"}
        )
        issues = validate_systemd_unit(spec)
        assert has_errors(issues)

    def test_invalid_type(self):
        spec = _make_systemd_unit_spec(
            unit={"unit_name": "x", "exec_start": "/bin/x", "type": "invalid"}
        )
        issues = validate_systemd_unit(spec)
        assert has_errors(issues)

    def test_logrotate_empty_path(self):
        spec = _make_systemd_unit_spec(
            logrotate={"enabled": True, "path": ""}
        )
        issues = validate_systemd_unit(spec)
        assert has_errors(issues)

    def test_logrotate_invalid_frequency(self):
        spec = _make_systemd_unit_spec(
            logrotate={"enabled": True, "path": "/var/log/*.log", "frequency": "hourly"}
        )
        issues = validate_systemd_unit(spec)
        assert has_errors(issues)


# ---------------------------------------------------------------------------
# Step Helpers
# ---------------------------------------------------------------------------


class TestSystemdStepHelpers:
    def test_render_service_unit(self):
        content = render_service_unit(
            description="Test App",
            exec_start="/bin/app",
            user="app",
            group="app",
            restart="always",
            restart_sec=10,
            after=["network.target"],
            service_type="simple",
            wanted_by="multi-user.target",
        )
        assert "[Unit]" in content
        assert "Description=Test App" in content
        assert "ExecStart=/bin/app" in content
        assert "User=app" in content
        assert "Restart=always" in content
        assert "RestartSec=10" in content
        assert "[Install]" in content
        assert "WantedBy=multi-user.target" in content

    def test_render_service_unit_with_env(self):
        content = render_service_unit(
            description="App",
            exec_start="/bin/app",
            environment={"FOO": "bar", "BAZ": "qux"},
            service_type="simple",
        )
        assert "Environment=BAZ=qux" in content
        assert "Environment=FOO=bar" in content

    def test_render_logrotate_config(self):
        content = render_logrotate_config(
            name="app",
            path="/var/log/app/*.log",
            rotate=7,
            frequency="daily",
            compress=True,
        )
        assert "/var/log/app/*.log {" in content
        assert "daily" in content
        assert "rotate 7" in content
        assert "compress" in content

    def test_daemon_reload(self):
        assert daemon_reload() == "systemctl daemon-reload"

    def test_enable_unit(self):
        assert enable_unit("myapp") == "systemctl enable myapp"

    def test_restart_unit(self):
        assert restart_unit("myapp") == "systemctl restart myapp"

    def test_is_active(self):
        assert is_active("myapp") == "systemctl is-active myapp"


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


class TestSystemdUnitPlanning:
    def test_plan_generates_unit_steps(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_systemd_unit_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        assert p.spec_kind == "systemd_unit"
        step_ids = [s.id for s in p.steps]
        assert "write_unit_myapp" in step_ids
        assert "systemd_daemon_reload" in step_ids
        assert "enable_myapp" in step_ids
        assert "restart_myapp" in step_ids
        assert "verify_myapp_active" in step_ids

    def test_plan_unit_file_content(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_systemd_unit_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        write_step = next(s for s in p.steps if s.id == "write_unit_myapp")
        assert "[Unit]" in write_step.file_content
        assert "ExecStart=/usr/local/bin/myapp serve" in write_step.file_content

    def test_plan_with_logrotate(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_systemd_unit_spec(
            logrotate={"enabled": True, "path": "/var/log/app/*.log"}
        )
        ctx = normalize(spec)
        p = plan(ctx)

        lr_steps = [s for s in p.steps if "logrotate" in s.tags]
        assert len(lr_steps) == 1
        assert "/var/log/app/*.log" in lr_steps[0].file_content

    def test_plan_without_logrotate(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_systemd_unit_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        lr_steps = [s for s in p.steps if "logrotate" in s.tags]
        assert len(lr_steps) == 0

    def test_plan_has_inventory_steps(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_systemd_unit_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        inv_steps = [s for s in p.steps if "inventory" in s.tags]
        assert len(inv_steps) == 3
