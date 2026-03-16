"""Tests for SSH conf.d management."""

import pytest
from pathlib import Path

from nodeforge.local.ssh_config import (
    write_ssh_conf_d,
    remove_ssh_conf_d,
    ensure_include,
    backup_ssh_config,
)
from nodeforge.registry.local_paths import LocalPathsConfig, register_local_paths


@pytest.fixture(autouse=True)
def isolated_local_paths(tmp_path):
    """Override local paths to use tmp_path so tests never touch ~/.ssh."""
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "ssh" / "conf.d" / "nodeforge",
            wg_state_base=tmp_path / "wg" / "nodeforge",
        )
    )
    yield
    # Restore defaults after each test
    register_local_paths(LocalPathsConfig())


def test_write_ssh_conf_d_creates_file(tmp_path):
    conf_file = write_ssh_conf_d(
        host_name="myserver",
        address="1.2.3.4",
        user="deploy",
        port=2222,
        identity_file="~/.ssh/id_ed25519",
    )
    assert conf_file.exists()
    content = conf_file.read_text()
    assert "Host myserver" in content
    assert "HostName 1.2.3.4" in content
    assert "User deploy" in content
    assert "Port 2222" in content
    assert "IdentityFile" in content


def test_write_ssh_conf_d_is_idempotent(tmp_path):
    """Writing twice should not create duplicate entries."""
    for _ in range(2):
        write_ssh_conf_d("myserver", "1.2.3.4", "deploy", 2222)

    from nodeforge.registry.local_paths import get_local_paths

    conf_file = get_local_paths().ssh_conf_d_base / "myserver.conf"
    content = conf_file.read_text()
    assert content.count("Host myserver") == 1


def test_write_ssh_conf_d_has_comment_marker():
    write_ssh_conf_d("myserver", "1.2.3.4", "deploy", 2222)
    from nodeforge.registry.local_paths import get_local_paths

    conf_file = get_local_paths().ssh_conf_d_base / "myserver.conf"
    assert "# nodeforge managed: myserver" in conf_file.read_text()


def test_remove_ssh_conf_d():
    write_ssh_conf_d("myserver", "1.2.3.4", "deploy", 2222)
    from nodeforge.registry.local_paths import get_local_paths

    conf_file = get_local_paths().ssh_conf_d_base / "myserver.conf"
    assert conf_file.exists()
    remove_ssh_conf_d("myserver")
    assert not conf_file.exists()


def test_ensure_include_writes_glob(tmp_path):
    """ensure_include writes 'Include {conf_d_base}/*' — a single glob, not per-file."""
    from nodeforge.registry.local_paths import get_local_paths

    config = tmp_path / "ssh_config"
    config.touch()

    ensure_include(config)

    content = config.read_text()
    expected = f"Include {get_local_paths().ssh_conf_d_base}/*"
    assert expected in content


def test_ensure_include_is_idempotent(tmp_path):
    config = tmp_path / "ssh_config"
    config.touch()

    ensure_include(config)
    ensure_include(config)

    from nodeforge.registry.local_paths import get_local_paths

    expected = f"Include {get_local_paths().ssh_conf_d_base}/*"
    assert config.read_text().count(expected) == 1


def test_ensure_include_creates_config_if_missing(tmp_path):
    config = tmp_path / "new_config"
    assert not config.exists()
    ensure_include(config)
    assert config.exists()


def test_ensure_include_honours_custom_base(tmp_path):
    """Commercial addon path override propagates to the Include line."""
    custom_base = tmp_path / "mycompany" / "prod"
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=custom_base,
            wg_state_base=tmp_path / "wg",
        )
    )
    config = tmp_path / "ssh_config"
    config.touch()

    ensure_include(config)

    assert f"Include {custom_base}/*" in config.read_text()


def test_backup_ssh_config(tmp_path):
    config = tmp_path / "config"
    config.write_text("Host example\n  HostName example.com\n")

    backup = backup_ssh_config(config)
    assert backup is not None
    assert backup.exists()
    assert backup.read_text() == config.read_text()


def test_backup_ssh_config_no_file(tmp_path):
    config = tmp_path / "config"  # does not exist
    result = backup_ssh_config(config)
    assert result is None
