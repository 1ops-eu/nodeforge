"""Tests for the addon-overridable local paths registry."""

from pathlib import Path

import pytest

from loft_cli_core.registry.local_paths import (
    LocalPathsConfig,
    get_local_paths,
    register_local_paths,
)


@pytest.fixture(autouse=True)
def restore_defaults():
    """Always restore default paths after each test."""
    yield
    register_local_paths(LocalPathsConfig())


def test_defaults_are_loft_cli_namespaced():
    paths = get_local_paths()
    assert "loft-cli" in str(paths.ssh_conf_d_base)
    assert "loft-cli" in str(paths.wg_state_base)


def test_ssh_conf_d_base_default_ends_with_loft_cli():
    paths = get_local_paths()
    assert paths.ssh_conf_d_base.name == "loft-cli"
    assert paths.ssh_conf_d_base.parent.name == "conf.d"


def test_wg_state_base_default_ends_with_loft_cli():
    paths = get_local_paths()
    assert paths.wg_state_base.name == "loft-cli"


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
    custom_base = tmp_path / "mycompany" / "conf.d" / "loft-cli"
    register_local_paths(
        LocalPathsConfig(
            ssh_conf_d_base=custom_base,
            wg_state_base=tmp_path / "wg",
        )
    )

    from loft_cli.local.ssh_config import write_ssh_conf_d

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

    from loft_cli.local.wireguard_store import save_wireguard_state

    host_dir = save_wireguard_state(
        host_name="testhost",
        spec_name="test-spec",
        private_key="8IReoXMQH73MyHqq0PKq7jl1md08E5Cd4wfQf31qXHw=",
        public_key="rka+MruYoGYyPaDsjem2kHWxBl59PKUFspMef8GSQng=",
        wg_conf_content="[Interface]\nAddress = 10.0.0.1/24\n",
        client_private_key="YBpTFhe3OaFHJgqKetv3mCFrHRNSAMTXFIe2wEq1LWE=",
        client_public_key="ABC123clientpubkey==",
        client_conf_content="[Interface]\nPrivateKey = test\n",
        interface="wg0",
        address="10.0.0.1/24",
        endpoint="1.2.3.4:51820",
        peer_address="10.0.0.2/32",
        persistent_keepalive=25,
    )

    assert host_dir.parent == custom_base
    assert host_dir.name == "testhost"


# ------------------------------------------------------------------ #
# state_dir tests
# ------------------------------------------------------------------ #


class TestStateDir:
    """Tests for LOFT_CLI_STATE_DIR and state_dir field."""

    def test_defaults_without_state_dir(self):
        """When no state_dir is set, defaults are the standard paths."""
        paths = LocalPathsConfig(state_dir=None)
        assert paths.ssh_conf_d_base == Path("~/.ssh/conf.d/loft-cli").expanduser()
        assert paths.wg_state_base == Path("~/.wg/loft-cli").expanduser()
        assert paths.inventory_db_path == Path("~/.loft-cli/inventory.db").expanduser()
        assert paths.log_dir == Path("~/.loft-cli/runs").expanduser()

    def test_state_dir_derives_all_paths(self, tmp_path):
        """When state_dir is set, all paths derive from it."""
        paths = LocalPathsConfig(state_dir=tmp_path / "mystate")
        assert paths.ssh_conf_d_base == tmp_path / "mystate" / "ssh" / "conf.d"
        assert paths.wg_state_base == tmp_path / "mystate" / "wg"
        assert paths.inventory_db_path == tmp_path / "mystate" / "inventory.db"
        assert paths.log_dir == tmp_path / "mystate" / "runs"

    def test_env_var_sets_state_dir(self, tmp_path, monkeypatch):
        """LOFT_CLI_STATE_DIR env var becomes the state_dir."""
        monkeypatch.setenv("LOFT_CLI_STATE_DIR", str(tmp_path / "envstate"))
        paths = LocalPathsConfig()
        assert paths.state_dir == tmp_path / "envstate"
        assert paths.inventory_db_path == tmp_path / "envstate" / "inventory.db"
        assert paths.log_dir == tmp_path / "envstate" / "runs"

    def test_explicit_field_overrides_state_dir(self, tmp_path):
        """Explicit field values take priority over state_dir derivation."""
        custom_ssh = tmp_path / "custom_ssh"
        custom_db = tmp_path / "custom.db"
        paths = LocalPathsConfig(
            state_dir=tmp_path / "mystate",
            ssh_conf_d_base=custom_ssh,
            inventory_db_path=custom_db,
        )
        # Explicitly set fields win
        assert paths.ssh_conf_d_base == custom_ssh
        assert paths.inventory_db_path == custom_db
        # Un-set fields still derive from state_dir
        assert paths.wg_state_base == tmp_path / "mystate" / "wg"
        assert paths.log_dir == tmp_path / "mystate" / "runs"

    def test_register_state_dir_affects_get_local_paths(self, tmp_path):
        """Registering a config with state_dir changes get_local_paths()."""
        register_local_paths(LocalPathsConfig(state_dir=tmp_path / "registered"))
        active = get_local_paths()
        assert active.log_dir == tmp_path / "registered" / "runs"
        assert active.inventory_db_path == tmp_path / "registered" / "inventory.db"

    def test_env_var_unset_gives_none(self, monkeypatch):
        """When LOFT_CLI_STATE_DIR is not set, state_dir is None."""
        monkeypatch.delenv("LOFT_CLI_STATE_DIR", raising=False)
        paths = LocalPathsConfig()
        assert paths.state_dir is None

    def test_log_dir_default(self):
        """Default log_dir is ~/.loft-cli/runs."""
        paths = LocalPathsConfig(state_dir=None)
        assert paths.log_dir == Path("~/.loft-cli/runs").expanduser()

    def test_inventory_db_path_default(self):
        """Default inventory_db_path is ~/.loft-cli/inventory.db."""
        paths = LocalPathsConfig(state_dir=None)
        assert paths.inventory_db_path == Path("~/.loft-cli/inventory.db").expanduser()


class TestLogModulesUseLocalPaths:
    """Verify logs/writer.py and logs/reader.py use get_local_paths().log_dir."""

    def test_writer_uses_registered_log_dir(self, tmp_path):
        """write_log() defaults to the registered log_dir, not hardcoded path."""
        register_local_paths(LocalPathsConfig(state_dir=tmp_path / "logtest"))
        from loft_cli.logs.writer import _default_log_dir

        assert _default_log_dir() == tmp_path / "logtest" / "runs"

    def test_reader_uses_registered_log_dir(self, tmp_path):
        """list_logs() / find_log() default to the registered log_dir."""
        register_local_paths(LocalPathsConfig(state_dir=tmp_path / "logtest"))
        from loft_cli.logs.reader import _default_log_dir

        assert _default_log_dir() == tmp_path / "logtest" / "runs"

    def test_reader_list_logs_empty_custom_dir(self, tmp_path):
        """list_logs() returns [] when the custom log_dir doesn't exist yet."""
        register_local_paths(LocalPathsConfig(state_dir=tmp_path / "empty"))
        from loft_cli.logs.reader import list_logs

        assert list_logs() == []

    def test_reader_find_log_none_custom_dir(self, tmp_path):
        """find_log() returns None when the custom log_dir doesn't exist yet."""
        register_local_paths(LocalPathsConfig(state_dir=tmp_path / "empty"))
        from loft_cli.logs.reader import find_log

        assert find_log("nonexistent") is None
