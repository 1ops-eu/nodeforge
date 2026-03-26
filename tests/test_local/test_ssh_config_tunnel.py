"""Tests for SSH config tunnel_comment and VPN IP injection (v0.6.3).

When WireGuard is enabled, write_ssh_conf_d should:
- Accept and include a tunnel_comment line
- The executor should pass the VPN IP as HostName instead of public IP
"""

from __future__ import annotations

import pytest

from loft_cli.local.ssh_config import write_ssh_conf_d
from loft_cli_core.registry.local_paths import LocalPathsConfig, register_local_paths


@pytest.fixture(autouse=True)
def isolated_local_paths(tmp_path):
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "ssh" / "conf.d" / "loft-cli",
            wg_state_base=tmp_path / "wg" / "loft-cli",
        )
    )
    yield
    register_local_paths(LocalPathsConfig())


class TestTunnelComment:
    def test_tunnel_comment_included(self, tmp_path):
        """When tunnel_comment is provided, it should appear in the config."""
        conf_file = write_ssh_conf_d(
            host_name="wg-host",
            address="10.10.0.1",
            user="deploy",
            port=2222,
            tunnel_comment="# Requires: loft-cli tunnel up wg-host",
        )
        content = conf_file.read_text()
        assert "# Requires: loft-cli tunnel up wg-host" in content

    def test_tunnel_comment_is_second_line(self, tmp_path):
        """Tunnel comment should be the second line (after the managed marker)."""
        conf_file = write_ssh_conf_d(
            host_name="wg-host",
            address="10.10.0.1",
            user="deploy",
            port=2222,
            tunnel_comment="# Requires: loft-cli tunnel up wg-host",
        )
        lines = conf_file.read_text().splitlines()
        assert lines[0] == "# loft-cli managed: wg-host"
        assert lines[1] == "# Requires: loft-cli tunnel up wg-host"

    def test_no_tunnel_comment_without_param(self, tmp_path):
        """When tunnel_comment is None, no extra comment line should appear."""
        conf_file = write_ssh_conf_d(
            host_name="plain-host",
            address="1.2.3.4",
            user="admin",
            port=2222,
        )
        content = conf_file.read_text()
        assert "Requires:" not in content
        lines = content.splitlines()
        # Line 0: managed marker, Line 1: Host block
        assert lines[1].startswith("Host ")

    def test_vpn_ip_as_hostname(self, tmp_path):
        """When WireGuard is enabled, HostName should be the VPN IP."""
        conf_file = write_ssh_conf_d(
            host_name="wg-host",
            address="10.10.0.1",  # VPN IP, not public IP
            user="deploy",
            port=2222,
            tunnel_comment="# Requires: loft-cli tunnel up wg-host",
        )
        content = conf_file.read_text()
        assert "HostName 10.10.0.1" in content
        # Should NOT contain the public IP
        assert "HostName 203.0.113.10" not in content

    def test_tunnel_comment_with_identity_file(self, tmp_path):
        """tunnel_comment should work alongside identity_file."""
        conf_file = write_ssh_conf_d(
            host_name="wg-host",
            address="10.10.0.1",
            user="deploy",
            port=2222,
            identity_file="~/.ssh/id_ed25519",
            tunnel_comment="# Requires: loft-cli tunnel up wg-host",
        )
        content = conf_file.read_text()
        assert "# Requires:" in content
        assert "IdentityFile" in content
        assert "HostName 10.10.0.1" in content
