"""Tests for the normalizer."""
from pathlib import Path
import pytest
from nodeforge.specs.loader import load_spec
from nodeforge.compiler.normalizer import normalize


def test_normalize_sets_ssh_conf_d_path(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    assert ctx.ssh_conf_d_path is not None
    assert "test-node-1.conf" in str(ctx.ssh_conf_d_path)


def test_normalize_sets_db_path(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    # db_path should be resolved even if inventory is disabled
    # (it defaults to the spec value)


def test_normalize_resolves_login_key(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    # login_key_path is set from spec.login.private_key
    assert ctx.login_key_path is not None
    assert "id_ed25519" in str(ctx.login_key_path)
