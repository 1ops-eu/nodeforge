"""Tests for WireGuard tunnel management — up, down, status."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from nodeforge.local.tunnel import (
    _client_conf_path,
    _get_active_interfaces,
    _host_dir,
    _interface_name,
    _is_interface_active,
    tunnel_down,
    tunnel_status,
    tunnel_up,
)
from nodeforge_core.registry.local_paths import LocalPathsConfig, register_local_paths


@pytest.fixture(autouse=True)
def isolated_local_paths(tmp_path):
    """Override local paths to use tmp_path so tests never touch real state."""
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "ssh" / "conf.d" / "nodeforge",
            wg_state_base=tmp_path / "wg" / "nodeforge",
        )
    )
    yield
    register_local_paths(LocalPathsConfig())


# ------------------------------------------------------------------ #
# _interface_name
# ------------------------------------------------------------------ #


class TestInterfaceName:
    def test_simple_name(self):
        assert _interface_name("node1") == "wg-node1"

    def test_truncates_to_15_chars(self):
        """Linux interface names are limited to 15 characters."""
        result = _interface_name("very-long-hostname-here")
        assert len(result) <= 15
        assert result == "wg-very-long-ho"

    def test_exactly_12_char_host(self):
        """wg- prefix (3) + 12 char host = 15, exactly at limit."""
        result = _interface_name("123456789012")
        assert result == "wg-123456789012"
        assert len(result) == 15

    def test_short_host(self):
        result = _interface_name("a")
        assert result == "wg-a"


# ------------------------------------------------------------------ #
# _host_dir / _client_conf_path
# ------------------------------------------------------------------ #


class TestPaths:
    def test_host_dir_under_wg_state_base(self, tmp_path):
        d = _host_dir("myhost")
        assert d.name == "myhost"
        assert "wg" in str(d)

    def test_client_conf_path(self, tmp_path):
        p = _client_conf_path("myhost")
        assert p.name == "client.conf"
        assert p.parent.name == "myhost"


# ------------------------------------------------------------------ #
# tunnel_up
# ------------------------------------------------------------------ #


class TestTunnelUp:
    def _setup_client_conf(self, tmp_path, host_name="testhost"):
        """Create a minimal client.conf for testing."""
        host_dir = _host_dir(host_name)
        host_dir.mkdir(parents=True, exist_ok=True)
        conf = host_dir / "client.conf"
        conf.write_text("[Interface]\nPrivateKey = test\n")
        conf.chmod(0o600)
        return conf

    def test_no_client_conf_returns_failure(self):
        ok, msg = tunnel_up("nonexistent-host")
        assert not ok
        assert "No client.conf found" in msg

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=True)
    def test_already_active_returns_success(self, _mock_active, tmp_path):
        self._setup_client_conf(tmp_path)
        ok, msg = tunnel_up("testhost")
        assert ok
        assert "already active" in msg

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=False)
    @patch("subprocess.run")
    def test_successful_up(self, mock_run, _mock_active, tmp_path):
        self._setup_client_conf(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        ok, msg = tunnel_up("testhost")

        assert ok
        assert "is up" in msg
        mock_run.assert_called_once()
        # Verify wg-quick was called with sudo
        args = mock_run.call_args[0][0]
        assert args[0] == "sudo"
        assert args[1] == "wg-quick"
        assert args[2] == "up"

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=False)
    @patch("subprocess.run")
    def test_failed_up(self, mock_run, _mock_active, tmp_path):
        self._setup_client_conf(tmp_path)
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some error")

        ok, msg = tunnel_up("testhost")

        assert not ok
        assert "some error" in msg

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=False)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_wg_quick_not_found(self, _mock_run, _mock_active, tmp_path):
        self._setup_client_conf(tmp_path)
        ok, msg = tunnel_up("testhost")
        assert not ok
        assert "wg-quick not found" in msg

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=False)
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("wg-quick", 30))
    def test_timeout(self, _mock_run, _mock_active, tmp_path):
        self._setup_client_conf(tmp_path)
        ok, msg = tunnel_up("testhost")
        assert not ok
        assert "timed out" in msg

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=False)
    @patch("subprocess.run")
    def test_temp_conf_cleaned_up(self, mock_run, _mock_active, tmp_path):
        """The temporary interface config file should be cleaned up."""
        self._setup_client_conf(tmp_path)
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        tunnel_up("testhost")

        host_dir = _host_dir("testhost")
        iface = _interface_name("testhost")
        temp_conf = host_dir / f"{iface}.conf"
        assert not temp_conf.exists(), "Temporary interface config should be cleaned up"


# ------------------------------------------------------------------ #
# tunnel_down
# ------------------------------------------------------------------ #


class TestTunnelDown:
    def _setup_client_conf(self, host_name="testhost"):
        """Create a minimal client.conf for testing."""
        host_dir = _host_dir(host_name)
        host_dir.mkdir(parents=True, exist_ok=True)
        conf = host_dir / "client.conf"
        conf.write_text("[Interface]\nPrivateKey = test\n")
        conf.chmod(0o600)
        return conf

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=False)
    def test_not_active_returns_success(self, _mock_active):
        ok, msg = tunnel_down("testhost")
        assert ok
        assert "not active" in msg

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=True)
    @patch("subprocess.run")
    def test_successful_down_with_client_conf(self, mock_run, _mock_active):
        """When client.conf exists, wg-quick down is called with temp config path."""
        self._setup_client_conf()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, msg = tunnel_down("testhost")
        assert ok
        assert "is down" in msg
        # Verify wg-quick was called with a full path (not bare interface name)
        args = mock_run.call_args[0][0]
        assert args[0] == "sudo"
        assert args[1] == "wg-quick"
        assert args[2] == "down"
        assert "/" in args[3]  # full path, not bare iface name

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=True)
    @patch("subprocess.run")
    def test_falls_back_to_ip_link_del_when_wg_quick_fails(self, mock_run, _mock_active):
        """If wg-quick down fails, ip link del is tried as fallback."""
        self._setup_client_conf()
        # First call (wg-quick down) fails, second call (ip link del) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="config error"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        ok, msg = tunnel_down("testhost")
        assert ok
        assert "ip link del fallback" in msg
        assert mock_run.call_count == 2

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=True)
    @patch("subprocess.run")
    def test_ip_link_del_when_no_client_conf(self, mock_run, _mock_active):
        """When client.conf is missing, skip wg-quick and use ip link del."""
        # Don't create client.conf — simulates removed host
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        ok, msg = tunnel_down("testhost")
        assert ok
        assert "ip link del fallback" in msg
        # Only one call — ip link del (no wg-quick attempt)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:3] == ["sudo", "ip", "link"]

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=True)
    @patch("subprocess.run")
    def test_both_methods_fail(self, mock_run, _mock_active):
        """When both wg-quick and ip link del fail, returns failure."""
        self._setup_client_conf()
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="wg-quick error"),
            MagicMock(returncode=1, stdout="", stderr="ip link error"),
        ]
        ok, msg = tunnel_down("testhost")
        assert not ok
        assert "ip link error" in msg

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=True)
    @patch("subprocess.run")
    def test_temp_conf_cleaned_up(self, mock_run, _mock_active):
        """The temporary interface config file should be cleaned up after down."""
        self._setup_client_conf()
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        tunnel_down("testhost")
        host_dir = _host_dir("testhost")
        iface = _interface_name("testhost")
        temp_conf = host_dir / f"{iface}.conf"
        assert not temp_conf.exists(), "Temporary interface config should be cleaned up"

    @patch("nodeforge.local.tunnel._is_interface_active", return_value=True)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_wg_quick_not_found(self, _mock_run, _mock_active):
        ok, msg = tunnel_down("testhost")
        assert not ok
        assert "wg-quick not found" in msg


# ------------------------------------------------------------------ #
# tunnel_status
# ------------------------------------------------------------------ #


class TestTunnelStatus:
    def test_empty_when_no_state_dir(self, tmp_path):
        hosts = tunnel_status()
        assert hosts == []

    @patch("nodeforge.local.tunnel._get_active_interfaces", return_value=set())
    def test_lists_hosts_from_metadata(self, _mock_active, tmp_path):
        """Should discover hosts from metadata.json files."""
        from nodeforge_core.registry.local_paths import get_local_paths

        base = get_local_paths().wg_state_base
        host_dir = base / "myhost"
        host_dir.mkdir(parents=True)
        metadata = {
            "host_name": "myhost",
            "address": "10.10.0.1/24",
            "endpoint": "1.2.3.4:51820",
            "peer_address": "10.10.0.2/32",
            "deployed_at": "2026-01-01T00:00:00",
        }
        (host_dir / "metadata.json").write_text(json.dumps(metadata))

        hosts = tunnel_status()

        assert len(hosts) == 1
        assert hosts[0]["host_name"] == "myhost"
        assert hosts[0]["vpn_ip"] == "10.10.0.1"
        assert hosts[0]["endpoint"] == "1.2.3.4:51820"
        assert hosts[0]["active"] is False

    @patch("nodeforge.local.tunnel._get_active_interfaces")
    def test_marks_active_interface(self, mock_active, tmp_path):
        """Active interface should be detected."""
        from nodeforge_core.registry.local_paths import get_local_paths

        iface = _interface_name("myhost")
        mock_active.return_value = {iface}

        base = get_local_paths().wg_state_base
        host_dir = base / "myhost"
        host_dir.mkdir(parents=True)
        metadata = {
            "address": "10.10.0.1/24",
            "endpoint": "1.2.3.4:51820",
            "peer_address": "10.10.0.2/32",
            "deployed_at": "",
        }
        (host_dir / "metadata.json").write_text(json.dumps(metadata))

        hosts = tunnel_status()
        assert hosts[0]["active"] is True

    @patch("nodeforge.local.tunnel._get_active_interfaces", return_value=set())
    def test_skips_dirs_without_metadata(self, _mock_active, tmp_path):
        """Directories without metadata.json should be skipped."""
        from nodeforge_core.registry.local_paths import get_local_paths

        base = get_local_paths().wg_state_base
        (base / "no-metadata-host").mkdir(parents=True)

        hosts = tunnel_status()
        assert hosts == []

    @patch("nodeforge.local.tunnel._get_active_interfaces", return_value=set())
    def test_skips_invalid_json(self, _mock_active, tmp_path):
        """Corrupt metadata.json should be skipped gracefully."""
        from nodeforge_core.registry.local_paths import get_local_paths

        base = get_local_paths().wg_state_base
        host_dir = base / "badhost"
        host_dir.mkdir(parents=True)
        (host_dir / "metadata.json").write_text("not valid json{{{")

        hosts = tunnel_status()
        assert hosts == []


# ------------------------------------------------------------------ #
# _is_interface_active / _get_active_interfaces
# ------------------------------------------------------------------ #


class TestLowLevelHelpers:
    @patch("subprocess.run")
    def test_is_interface_active_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert _is_interface_active("wg-test") is True

    @patch("subprocess.run")
    def test_is_interface_active_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert _is_interface_active("wg-test") is False

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_is_interface_active_no_wg(self, _mock_run):
        assert _is_interface_active("wg-test") is False

    @patch("subprocess.run")
    def test_get_active_interfaces(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="wg-host1 wg-host2\n")
        result = _get_active_interfaces()
        assert result == {"wg-host1", "wg-host2"}

    @patch("subprocess.run")
    def test_get_active_interfaces_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = _get_active_interfaces()
        assert result == set()  # strip().split() on "" gives []

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_get_active_interfaces_no_wg(self, _mock_run):
        result = _get_active_interfaces()
        assert result == set()
