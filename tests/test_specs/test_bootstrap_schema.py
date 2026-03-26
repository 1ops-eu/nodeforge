"""Tests for bootstrap YAML spec loading and validation."""

import pytest

from loft_cli_core.specs.bootstrap_schema import BootstrapSpec
from loft_cli_core.specs.loader import SpecLoadError, load_spec


def test_load_valid_bootstrap(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    assert isinstance(spec, BootstrapSpec)
    assert spec.kind == "bootstrap"
    assert spec.meta.name == "test-node"
    assert spec.host.address == "192.168.1.100"
    assert spec.ssh.port == 2222


def test_load_missing_file(tmp_path):
    with pytest.raises(SpecLoadError, match="not found"):
        load_spec(tmp_path / "nonexistent.yaml")


def test_load_invalid_kind(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("kind: unknown\nmeta:\n  name: test\n")
    with pytest.raises(SpecLoadError, match="Unknown spec kind"):
        load_spec(f)


def test_load_not_a_mapping(tmp_path):
    f = tmp_path / "list.yaml"
    f.write_text("- item1\n- item2\n")
    with pytest.raises(SpecLoadError, match="mapping"):
        load_spec(f)


def test_defaults_applied(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    assert spec.login.user == "root"
    assert spec.firewall.provider == "ufw"
    assert spec.admin_user.name == "admin"


def test_env_var_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_TEST_HOST", "10.0.0.1")
    f = tmp_path / "env.yaml"
    f.write_text(
        "kind: bootstrap\n"
        "meta:\n  name: env-test\n"
        "host:\n  name: n1\n  address: ${MY_TEST_HOST}\n"
    )
    spec = load_spec(f)
    assert spec.host.address == "10.0.0.1"


def test_missing_env_var_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    f = tmp_path / "missing_env.yaml"
    f.write_text(
        "kind: bootstrap\n" "meta:\n  name: t\n" "host:\n  name: n\n  address: ${MISSING_VAR}\n"
    )
    with pytest.raises(SpecLoadError, match="MISSING_VAR"):
        load_spec(f)
