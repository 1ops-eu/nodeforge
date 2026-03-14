"""Tests for SSH conf.d management."""
from pathlib import Path
import pytest

from nodeforge.local.ssh_config import (
    write_ssh_conf_d,
    remove_ssh_conf_d,
    ensure_include,
    backup_ssh_config,
)


def test_write_ssh_conf_d_creates_file(tmp_path):
    conf_file = write_ssh_conf_d(
        host_name="myserver",
        address="1.2.3.4",
        user="deploy",
        port=2222,
        identity_file="~/.ssh/id_ed25519",
        conf_d_base=tmp_path,
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
        write_ssh_conf_d("myserver", "1.2.3.4", "deploy", 2222, conf_d_base=tmp_path)

    conf_file = tmp_path / "myserver.conf"
    content = conf_file.read_text()
    assert content.count("Host myserver") == 1


def test_write_ssh_conf_d_has_comment_marker(tmp_path):
    write_ssh_conf_d("myserver", "1.2.3.4", "deploy", 2222, conf_d_base=tmp_path)
    conf_file = tmp_path / "myserver.conf"
    assert "# nodeforge managed: myserver" in conf_file.read_text()


def test_remove_ssh_conf_d(tmp_path):
    write_ssh_conf_d("myserver", "1.2.3.4", "deploy", 2222, conf_d_base=tmp_path)
    remove_ssh_conf_d("myserver", conf_d_base=tmp_path)
    assert not (tmp_path / "myserver.conf").exists()


def test_ensure_include_adds_line(tmp_path):
    config = tmp_path / "config"
    config.touch()
    conf_d_file = tmp_path / "myserver.conf"
    conf_d_file.touch()

    ensure_include(conf_d_file, config_path=config)

    content = config.read_text()
    assert f"Include {conf_d_file}" in content


def test_ensure_include_is_idempotent(tmp_path):
    config = tmp_path / "config"
    config.touch()
    conf_d_file = tmp_path / "myserver.conf"

    ensure_include(conf_d_file, config_path=config)
    ensure_include(conf_d_file, config_path=config)

    content = config.read_text()
    assert content.count(f"Include {conf_d_file}") == 1


def test_backup_ssh_config(tmp_path):
    config = tmp_path / "config"
    config.write_text("Host example\n  HostName example.com\n")

    backup = backup_ssh_config(config_path=config)
    assert backup is not None
    assert backup.exists()
    assert backup.read_text() == config.read_text()


def test_backup_ssh_config_no_file(tmp_path):
    config = tmp_path / "config"  # does not exist
    result = backup_ssh_config(config_path=config)
    assert result is None
