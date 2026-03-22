"""Tests for env-file overlay layering (RFC 008)."""

import os
import textwrap

import pytest

from nodeforge_core.specs.loader import SpecLoadError, load_env_file, load_spec


class TestLoadEnvFile:
    def test_basic_key_value(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("FOO=bar\nBAZ=qux\n")
        env = load_env_file(f)
        assert env == {"FOO": "bar", "BAZ": "qux"}

    def test_quoted_values(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("SINGLE='hello'\nDOUBLE=\"world\"\n")
        env = load_env_file(f)
        assert env == {"SINGLE": "hello", "DOUBLE": "world"}

    def test_export_prefix_stripped(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("export KEY=value\n")
        env = load_env_file(f)
        assert env == {"KEY": "value"}

    def test_comments_and_blanks_ignored(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("# comment\n\nKEY=val\n")
        env = load_env_file(f)
        assert env == {"KEY": "val"}


class TestEnvFileOverlayLayering:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        """Remove test env vars before each test."""
        for key in ("LAYER_A", "LAYER_B", "LAYER_C", "EXISTING_VAR"):
            monkeypatch.delenv(key, raising=False)

    def _make_spec(self, tmp_path, var_name="LAYER_A"):
        spec_file = tmp_path / "test.yaml"
        spec_file.write_text(textwrap.dedent("""\
            kind: bootstrap
            meta:
              name: env-test
            host:
              name: node1
              address: 10.0.0.1
            admin_user:
              name: admin
              pubkeys: []
            ssh:
              port: 2222
            login:
              user: root
              port: 22
            local:
              inventory:
                enabled: false
        """))
        return spec_file

    def test_single_env_file(self, tmp_path, monkeypatch):
        env1 = tmp_path / "a.env"
        env1.write_text("LAYER_A=from_a\n")
        spec_file = self._make_spec(tmp_path)

        load_spec(spec_file, env_files=[env1])
        assert os.environ.get("LAYER_A") == "from_a"

    def test_later_files_override_earlier(self, tmp_path, monkeypatch):
        env1 = tmp_path / "a.env"
        env1.write_text("LAYER_A=from_a\n")
        env2 = tmp_path / "b.env"
        env2.write_text("LAYER_A=from_b\n")
        spec_file = self._make_spec(tmp_path)

        # Clear any leftover
        monkeypatch.delenv("LAYER_A", raising=False)
        load_spec(spec_file, env_files=[env1, env2])
        assert os.environ.get("LAYER_A") == "from_b"

    def test_os_environ_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXISTING_VAR", "from_os")
        env1 = tmp_path / "a.env"
        env1.write_text("EXISTING_VAR=from_file\n")
        spec_file = self._make_spec(tmp_path, var_name="EXISTING_VAR")

        load_spec(spec_file, env_files=[env1])
        # os.environ.setdefault should not override existing value
        assert os.environ.get("EXISTING_VAR") == "from_os"

    def test_missing_env_file_raises(self, tmp_path):
        spec_file = self._make_spec(tmp_path)
        with pytest.raises(SpecLoadError, match="Env file not found"):
            load_spec(spec_file, env_files=[tmp_path / "nonexistent.env"])

    def test_env_file_and_env_files_combined(self, tmp_path, monkeypatch):
        """When both env_file and env_files are given, env_file comes first."""
        single = tmp_path / "single.env"
        single.write_text("LAYER_A=from_single\n")
        multi = tmp_path / "multi.env"
        multi.write_text("LAYER_A=from_multi\nLAYER_B=only_multi\n")
        spec_file = self._make_spec(tmp_path)

        monkeypatch.delenv("LAYER_A", raising=False)
        monkeypatch.delenv("LAYER_B", raising=False)
        load_spec(spec_file, env_file=single, env_files=[multi])
        # multi.env comes after single.env in the merge, so its values win
        assert os.environ.get("LAYER_A") == "from_multi"
        assert os.environ.get("LAYER_B") == "only_multi"
