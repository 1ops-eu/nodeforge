"""Tests for the addon-overridable local paths registry."""

import pytest
from pathlib import Path

from nodeforge.registry.local_paths import (
    LocalPathsConfig,
    register_local_paths,
    get_local_paths,
)


@pytest.fixture(autouse=True)
def restore_defaults():
    """Always restore default paths after each test."""
    yield
    register_local_paths(LocalPathsConfig())


def test_defaults_are_nodeforge_namespaced():
    paths = get_local_paths()
    assert "nodeforge" in str(paths.ssh_conf_d_base)
    assert "nodeforge" in str(paths.wg_state_base)


def test_ssh_conf_d_base_default_ends_with_nodeforge():
    paths = get_local_paths()
    assert paths.ssh_conf_d_base.name == "nodeforge"
    assert paths.ssh_conf_d_base.parent.name == "conf.d"


def test_wg_state_base_default_ends_with_nodeforge():
    paths = get_local_paths()
    assert paths.wg_state_base.name == "nodeforge"


def test_register_replaces_config(tmp_path):
    custom = LocalPathsConfig(
        ssh_conf_d_base=tmp_path / "mycompany" / "ssh",
        wg_state_base=tmp_path / "mycompany" / "wg",
    )
    register_local_paths(custom)
    active = get_local_paths()
    assert active.ssh_conf_d_base == tmp_path / "mycompany" / "ssh"
    assert active.wg_state_base == tmp_path / "mycompany" / "wg"


def test_last_registration_wins(tmp_path):
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "first",
            wg_state_base=tmp_path / "first_wg",
        )
    )
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "second",
            wg_state_base=tmp_path / "second_wg",
        )
    )
    assert get_local_paths().ssh_conf_d_base == tmp_path / "second"


def test_ssh_config_uses_active_paths(tmp_path):
    """ssh_config.py reads get_local_paths() at call time — override is picked up."""
    custom_base = tmp_path / "mycompany" / "conf.d" / "nodeforge"
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=custom_base,
            wg_state_base=tmp_path / "wg",
        )
    )

    from nodeforge.local.ssh_config import write_ssh_conf_d

    conf_file = write_ssh_conf_d("testhost", "1.2.3.4", "admin", 22)

    assert conf_file.parent == custom_base
    assert conf_file.name == "testhost.conf"


def test_wireguard_store_uses_active_paths(tmp_path):
    """wireguard_store.py reads get_local_paths() at call time."""
    custom_base = tmp_path / "mycompany" / "wg"
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "ssh",
            wg_state_base=custom_base,
        )
    )

    from nodeforge.local.wireguard_store import save_wireguard_state

    host_dir = save_wireguard_state(
        host_name="testhost",
        spec_name="test-spec",
        private_key="8IReoXMQH73MyHqq0PKq7jl1md08E5Cd4wfQf31qXHw=",
        public_key="rka+MruYoGYyPaDsjem2kHWxBl59PKUFspMef8GSQng=",
        wg_conf_content="[Interface]\nAddress = 10.0.0.1/24\n",
        interface="wg0",
        address="10.0.0.1/24",
        endpoint="1.2.3.4:51820",
        allowed_ips=["10.0.0.2/32"],
        persistent_keepalive=25,
    )

    assert host_dir.parent == custom_base
    assert host_dir.name == "testhost"
