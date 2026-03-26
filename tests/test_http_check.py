"""Tests for http_check kind -- schema, validation, and planning."""

import pytest
from pydantic import ValidationError

from loft_cli_core.specs.http_check_schema import (
    HttpCheckConfig,
    HttpCheckLoginBlock,
    HttpCheckSpec,
)
from loft_cli_core.specs.validators import has_errors, validate_http_check

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_check_spec(**overrides) -> HttpCheckSpec:
    base = {
        "kind": "http_check",
        "meta": {"name": "test-hc", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "check": {
            "url": "http://localhost:8080/health",
        },
    }
    base.update(overrides)
    return HttpCheckSpec.model_validate(base)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestHttpCheckSchema:
    def test_check_config_defaults(self):
        cfg = HttpCheckConfig(url="http://localhost/health")
        assert cfg.expected_status == 200
        assert cfg.retries == 5
        assert cfg.interval == 3
        assert cfg.timeout == 10

    def test_check_config_custom(self):
        cfg = HttpCheckConfig(
            url="https://example.com/ready",
            expected_status=204,
            retries=20,
            interval=10,
            timeout=30,
        )
        assert cfg.expected_status == 204
        assert cfg.retries == 20

    def test_login_defaults(self):
        login = HttpCheckLoginBlock()
        assert login.user == "admin"
        assert login.port == 2222
        assert login.private_key == "~/.ssh/id_ed25519"
        assert login.password is None

    def test_spec_round_trip(self):
        spec = _make_http_check_spec()
        assert spec.kind == "http_check"
        assert spec.check.url == "http://localhost:8080/health"
        assert spec.check.expected_status == 200
        assert spec.checks == []

    def test_spec_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_http_check_spec(extra_field="nope")

    def test_check_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_http_check_spec(check={"url": "http://x", "bogus": True})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestHttpCheckValidation:
    def test_valid_spec(self):
        spec = _make_http_check_spec()
        issues = validate_http_check(spec)
        assert not has_errors(issues)

    def test_empty_url(self):
        spec = _make_http_check_spec(check={"url": ""})
        issues = validate_http_check(spec)
        assert has_errors(issues)
        assert any("URL must not be empty" in str(i) for i in issues)

    def test_invalid_url_scheme(self):
        spec = _make_http_check_spec(check={"url": "ftp://example.com"})
        issues = validate_http_check(spec)
        assert has_errors(issues)
        assert any("http://" in str(i) for i in issues)

    def test_invalid_status(self):
        spec = _make_http_check_spec(check={"url": "http://x", "expected_status": 999})
        issues = validate_http_check(spec)
        assert has_errors(issues)

    def test_zero_retries(self):
        spec = _make_http_check_spec(check={"url": "http://x", "retries": 0})
        issues = validate_http_check(spec)
        assert has_errors(issues)

    def test_negative_interval(self):
        spec = _make_http_check_spec(check={"url": "http://x", "interval": -1})
        issues = validate_http_check(spec)
        assert has_errors(issues)

    def test_zero_timeout(self):
        spec = _make_http_check_spec(check={"url": "http://x", "timeout": 0})
        issues = validate_http_check(spec)
        assert has_errors(issues)


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


class TestHttpCheckPlanning:
    def test_plan_generates_gate_step(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_http_check_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        assert p.spec_kind == "http_check"
        gate_steps = [s for s in p.steps if s.gate]
        assert len(gate_steps) == 1
        assert gate_steps[0].id == "http_check_gate"
        assert "http_check:" in gate_steps[0].command
        assert "http://localhost:8080/health" in gate_steps[0].command

    def test_plan_has_preflight(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_http_check_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        preflight = [s for s in p.steps if "preflight" in s.tags]
        assert len(preflight) == 1

    def test_plan_has_inventory_steps(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_http_check_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        inv_steps = [s for s in p.steps if "inventory" in s.tags]
        assert len(inv_steps) == 3

    def test_plan_no_inventory_when_disabled(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_http_check_spec(local={"inventory": {"enabled": False}})
        ctx = normalize(spec)
        p = plan(ctx)

        inv_steps = [s for s in p.steps if "inventory" in s.tags]
        assert len(inv_steps) == 0
