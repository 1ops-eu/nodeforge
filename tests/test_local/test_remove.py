"""Tests for host removal orchestration."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from nodeforge.local.remove import remove_host
from nodeforge_core.registry.local_paths import LocalPathsConfig, register_local_paths


@pytest.fixture(autouse=True)
def isolated_local_paths(tmp_path):
    """Override local paths so tests never touch real state."""
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=tmp_path / "ssh" / "conf.d" / "nodeforge",
            wg_state_base=tmp_path / "wg" / "nodeforge",
        )
    )
    yield
    register_local_paths(LocalPathsConfig())


def _setup_wg_state(tmp_path, host_name="testhost"):
    """Create fake WireGuard state files for a host."""
    from nodeforge_core.registry.local_paths import get_local_paths

    wg_dir = get_local_paths().wg_state_base / host_name
    wg_dir.mkdir(parents=True)
    (wg_dir / "private.key").write_text("fake-key\n")
    (wg_dir / "client.conf").write_text("[Interface]\nPrivateKey = fake\n")
    (wg_dir / "metadata.json").write_text(json.dumps({"host_name": host_name}))
    return wg_dir


def _setup_ssh_conf(tmp_path, host_name="testhost"):
    """Create a fake SSH conf.d entry for a host."""
    from nodeforge_core.registry.local_paths import get_local_paths

    conf_dir = get_local_paths().ssh_conf_d_base
    conf_dir.mkdir(parents=True, exist_ok=True)
    conf_file = conf_dir / f"{host_name}.conf"
    conf_file.write_text(
        f"# nodeforge managed: {host_name}\nHost {host_name}\n  HostName 1.2.3.4\n"
    )
    return conf_file


class TestRemoveHost:
    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "Tunnel not active"))
    def test_removes_wireguard_state(self, _mock_down, tmp_path):
        wg_dir = _setup_wg_state(tmp_path)
        assert wg_dir.exists()

        console = MagicMock()
        results = remove_host("testhost", console=console)

        assert not wg_dir.exists()
        wg_result = next(r for r in results if r["action"] == "wireguard_state")
        assert wg_result["status"] == "ok"

    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "Tunnel not active"))
    def test_removes_ssh_config(self, _mock_down, tmp_path):
        _setup_ssh_conf(tmp_path)
        from nodeforge_core.registry.local_paths import get_local_paths

        conf_file = get_local_paths().ssh_conf_d_base / "testhost.conf"
        assert conf_file.exists()

        console = MagicMock()
        results = remove_host("testhost", console=console)

        assert not conf_file.exists()
        ssh_result = next(r for r in results if r["action"] == "ssh_config")
        assert ssh_result["status"] == "ok"

    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "Tunnel not active"))
    def test_skips_missing_wireguard_state(self, _mock_down, tmp_path):
        console = MagicMock()
        results = remove_host("nonexistent", console=console)

        wg_result = next(r for r in results if r["action"] == "wireguard_state")
        assert wg_result["status"] == "skipped"

    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "Tunnel wg-test is down"))
    def test_calls_tunnel_down(self, mock_down, tmp_path):
        console = MagicMock()
        remove_host("testhost", console=console)

        mock_down.assert_called_once_with("testhost")

        # Just verify the mock was called — the result from the first call
        # already confirmed the tunnel_down action was included
        remove_host("testhost", console=MagicMock())
        # Instead, just verify via the first call's results
        assert mock_down.called

    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "not active"))
    def test_returns_all_four_actions(self, _mock_down, tmp_path):
        """remove_host should always return results for all 4 actions."""
        console = MagicMock()
        results = remove_host("testhost", console=console)

        actions = {r["action"] for r in results}
        assert "tunnel_down" in actions
        assert "wireguard_state" in actions
        assert "ssh_config" in actions
        assert "inventory" in actions

    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "not active"))
    def test_handles_tunnel_down_error_gracefully(self, _mock_down, tmp_path):
        """Even if tunnel_down raises, other actions should still run."""
        _mock_down.side_effect = RuntimeError("wg-quick exploded")

        console = MagicMock()
        results = remove_host("testhost", console=console)

        tunnel_result = next(r for r in results if r["action"] == "tunnel_down")
        assert tunnel_result["status"] == "error"
        # Other actions should still be present
        assert len(results) == 4

    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "not active"))
    def test_inventory_skipped_when_no_record(self, _mock_down, tmp_path):
        """When there's no inventory record, status should be 'skipped'."""
        import os

        from nodeforge.local.inventory_db import InventoryDB

        # Create and initialize a fresh DB so the table exists
        db_path = str(tmp_path / "test_inventory.db")
        db = InventoryDB(db_path=db_path)
        db.open()
        db.initialize()
        db.close()

        with patch.dict(os.environ, {"NODEFORGE_DB_PATH": db_path}):
            console = MagicMock()
            results = remove_host("testhost", console=console)

        inv_result = next(r for r in results if r["action"] == "inventory")
        assert inv_result["status"] == "skipped"

    @patch("nodeforge.local.tunnel.tunnel_down", return_value=(True, "not active"))
    def test_creates_console_if_none(self, _mock_down, tmp_path):
        """If console=None, remove_host should create one internally."""
        results = remove_host("testhost", console=None)
        # Should not raise and should return results
        assert len(results) == 4
