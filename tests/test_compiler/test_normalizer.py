"""Tests for the normalizer."""

import pytest

from nodeforge.compiler.normalizer import normalize
from nodeforge_core.registry.local_paths import LocalPathsConfig, register_local_paths
from nodeforge_core.specs.loader import load_spec


@pytest.fixture(autouse=True)
def restore_defaults():
    yield
    register_local_paths(LocalPathsConfig())


def test_normalize_sets_ssh_conf_d_path(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    assert ctx.ssh_conf_d_path is not None
    assert "test-node-1.conf" in str(ctx.ssh_conf_d_path)


def test_normalize_ssh_conf_d_path_uses_nodeforge_subdir(bootstrap_yaml):
    """Default base is ~/.ssh/conf.d/nodeforge/ — not the old ~/.ssh/conf.d/."""
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    assert ctx.ssh_conf_d_path is not None
    assert "nodeforge" in str(ctx.ssh_conf_d_path)


def test_normalize_ssh_conf_d_path_honours_custom_base(bootstrap_yaml, tmp_path):
    """Addon override: deeper path propagates through normalize()."""
    custom_base = tmp_path / "mycompany" / "project1" / "ssh"
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=custom_base,
            wg_state_base=tmp_path / "wg",
        )
    )
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    assert ctx.ssh_conf_d_path is not None
    assert ctx.ssh_conf_d_path.parent == custom_base


def test_normalize_sets_db_path(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    assert ctx.db_path is not None


def test_normalize_resolves_login_key(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    assert ctx.login_key_path is not None
    assert "id_ed25519" in str(ctx.login_key_path)


def test_normalize_derives_wireguard_public_key(tmp_path):
    """When a valid WireGuard private key is supplied, public key is derived via PyNaCl."""
    import textwrap

    # Write a real WireGuard private key to a temp file
    priv = "8IReoXMQH73MyHqq0PKq7jl1md08E5Cd4wfQf31qXHw="
    expected_pub = "rka+MruYoGYyPaDsjem2kHWxBl59PKUFspMef8GSQng="
    key_file = tmp_path / "wg.key"
    key_file.write_text(priv)

    spec_yaml = tmp_path / "spec.yaml"
    spec_yaml.write_text(textwrap.dedent(f"""
        kind: bootstrap
        meta:
          name: wg-test
          description: ""
        host:
          name: wg-node
          address: 192.168.1.1
        wireguard:
          enabled: true
          interface: wg0
          address: 10.0.0.1/24
          private_key_file: "{key_file}"
          endpoint: "192.168.1.1:51820"
          peer_address: "10.0.0.2/32"
    """))

    spec = load_spec(spec_yaml)
    ctx = normalize(spec)

    assert ctx.wireguard_private_key == priv
    assert ctx.wireguard_public_key == expected_pub
    # Client key pair must be auto-generated (non-empty, valid base64)
    import base64

    assert ctx.wg_client_private_key
    assert ctx.wg_client_public_key
    base64.b64decode(ctx.wg_client_private_key)  # must be valid base64
    base64.b64decode(ctx.wg_client_public_key)
