"""Tests for cross-field validation logic."""

from loft_cli_core.specs.bootstrap_schema import BootstrapSpec
from loft_cli_core.specs.validators import has_errors, validate_bootstrap


def _make_spec(**overrides) -> BootstrapSpec:
    base = {
        "kind": "bootstrap",
        "meta": {"name": "test"},
        "host": {"name": "n1", "address": "1.2.3.4"},
    }
    base.update(overrides)
    return BootstrapSpec.model_validate(base)


def test_disable_password_auth_requires_pubkeys():
    spec = _make_spec(ssh={"port": 2222, "disable_password_auth": True})
    issues = validate_bootstrap(spec)
    assert has_errors(issues)
    assert any("pubkey" in i.message for i in issues)


def test_disable_password_auth_with_pubkeys_is_ok():
    spec = _make_spec(
        ssh={"port": 2222, "disable_password_auth": True},
        admin_user={"name": "admin", "pubkeys": ["~/.ssh/id_ed25519.pub"]},
    )
    issues = validate_bootstrap(spec)
    assert not has_errors(issues)


def test_wireguard_enabled_requires_config():
    spec = _make_spec(wireguard={"enabled": True})
    issues = validate_bootstrap(spec)
    assert has_errors(issues)
    error_fields = [i.field for i in issues if i.severity == "error"]
    assert "wireguard.private_key_file" not in error_fields  # auto-generated when omitted
    assert "wireguard.endpoint" in error_fields
    assert "wireguard.address" in error_fields
    assert "wireguard.peer_address" in error_fields


def test_wireguard_disabled_no_errors():
    spec = _make_spec()
    issues = validate_bootstrap(spec)
    # Only possible warning is ssh.port same as login port
    errors = [i for i in issues if i.severity == "error"]
    assert not errors


def test_invalid_ssh_port():
    spec = _make_spec(ssh={"port": 0})
    issues = validate_bootstrap(spec)
    assert has_errors(issues)
    assert any("port" in i.field for i in issues)
