"""Tests for WireGuard local state storage."""

import json
import pytest
from pathlib import Path

from nodeforge.local.wireguard_store import save_wireguard_state
from nodeforge.registry.local_paths import LocalPathsConfig, register_local_paths


# Known WireGuard test key pair (Curve25519, base64)
_PRIVATE_KEY = "8IReoXMQH73MyHqq0PKq7jl1md08E5Cd4wfQf31qXHw="
_PUBLIC_KEY = "rka+MruYoGYyPaDsjem2kHWxBl59PKUFspMef8GSQng="
_WG_CONF = """\
[Interface]
Address = 10.10.0.1/24
PrivateKey = 8IReoXMQH73MyHqq0PKq7jl1md08E5Cd4wfQf31qXHw=

[Peer]
PublicKey = rka+MruYoGYyPaDsjem2kHWxBl59PKUFspMef8GSQng=
Endpoint = 192.168.56.10:51820
AllowedIPs = 10.10.0.2/32
PersistentKeepalive = 25
"""


@pytest.fixture(autouse=True)
def isolated_local_paths(tmp_path):
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "ssh" / "conf.d" / "nodeforge",
            wg_state_base=tmp_path / "wg" / "nodeforge",
        )
    )
    yield
    register_local_paths(LocalPathsConfig())


def _save(tmp_path, host_name="ubuntu-node-1"):
    return save_wireguard_state(
        host_name=host_name,
        spec_name="ubuntu-05-wireguard",
        private_key=_PRIVATE_KEY,
        public_key=_PUBLIC_KEY,
        wg_conf_content=_WG_CONF,
        interface="wg0",
        address="10.10.0.1/24",
        endpoint="192.168.56.10:51820",
        allowed_ips=["10.10.0.2/32"],
        persistent_keepalive=25,
    )


def test_creates_host_directory(tmp_path):
    host_dir = _save(tmp_path)
    assert host_dir.is_dir()
    assert host_dir.name == "ubuntu-node-1"


def test_host_dir_under_wg_state_base(tmp_path):
    from nodeforge.registry.local_paths import get_local_paths

    host_dir = _save(tmp_path)
    assert host_dir.parent == get_local_paths().wg_state_base


def test_private_key_file(tmp_path):
    host_dir = _save(tmp_path)
    key_file = host_dir / "private.key"
    assert key_file.exists()
    assert _PRIVATE_KEY in key_file.read_text()
    assert oct(key_file.stat().st_mode)[-3:] == "600"


def test_public_key_file(tmp_path):
    host_dir = _save(tmp_path)
    key_file = host_dir / "public.key"
    assert key_file.exists()
    assert _PUBLIC_KEY in key_file.read_text()
    assert oct(key_file.stat().st_mode)[-3:] == "644"


def test_wg_conf_file(tmp_path):
    host_dir = _save(tmp_path)
    conf_file = host_dir / "wg0.conf"
    assert conf_file.exists()
    assert "[Interface]" in conf_file.read_text()
    assert "10.10.0.1/24" in conf_file.read_text()
    assert oct(conf_file.stat().st_mode)[-3:] == "600"


def test_metadata_json_fields(tmp_path):
    host_dir = _save(tmp_path)
    meta = json.loads((host_dir / "metadata.json").read_text())

    assert meta["host_name"] == "ubuntu-node-1"
    assert meta["spec_name"] == "ubuntu-05-wireguard"
    assert meta["interface"] == "wg0"
    assert meta["address"] == "10.10.0.1/24"
    assert meta["endpoint"] == "192.168.56.10:51820"
    assert meta["allowed_ips"] == ["10.10.0.2/32"]
    assert meta["persistent_keepalive"] == 25
    assert meta["public_key"] == _PUBLIC_KEY
    assert "deployed_at" in meta
    # deployed_at must be a valid ISO8601 timestamp
    from datetime import datetime

    datetime.fromisoformat(meta["deployed_at"])


def test_is_idempotent(tmp_path):
    """Calling twice overwrites cleanly — no duplicates or errors."""
    _save(tmp_path)
    _save(tmp_path)
    host_dir = _save(tmp_path)
    assert (host_dir / "private.key").exists()


def test_custom_wg_state_base(tmp_path):
    """Commercial addon override: deeper nested base path."""
    custom_base = tmp_path / "mycompany" / "project1"
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "ssh",
            wg_state_base=custom_base,
        )
    )
    host_dir = _save(tmp_path)
    assert host_dir.parent == custom_base
    assert (host_dir / "private.key").exists()
