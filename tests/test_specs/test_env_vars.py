"""Tests for environment variable resolution in spec files.

Tests the _resolve_env_vars() function and load_env_file() helper
directly, without requiring pydantic (they operate on raw dicts/strings).
"""

from __future__ import annotations

import os
import textwrap

import pytest

from nodeforge.specs.loader import _resolve_env_vars, load_env_file, SpecLoadError


# ------------------------------------------------------------------ #
# _resolve_env_vars — strict mode (default)
# ------------------------------------------------------------------ #


class TestResolveEnvVarsStrict:
    """Tests for _resolve_env_vars with strict=True (default)."""

    def test_simple_string_resolved(self, monkeypatch):
        monkeypatch.setenv("MY_HOST", "10.0.0.1")
        assert _resolve_env_vars("${MY_HOST}") == "10.0.0.1"

    def test_partial_string_resolved(self, monkeypatch):
        monkeypatch.setenv("MY_PORT", "8080")
        result = _resolve_env_vars("http://localhost:${MY_PORT}/api")
        assert result == "http://localhost:8080/api"

    def test_multiple_vars_in_one_string(self, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        monkeypatch.setenv("PORT", "443")
        result = _resolve_env_vars("${HOST}:${PORT}")
        assert result == "example.com:443"

    def test_nested_dict(self, monkeypatch):
        monkeypatch.setenv("ADDR", "192.168.1.1")
        monkeypatch.setenv("USR", "admin")
        data = {
            "host": {"address": "${ADDR}"},
            "login": {"user": "${USR}"},
        }
        result = _resolve_env_vars(data)
        assert result["host"]["address"] == "192.168.1.1"
        assert result["login"]["user"] == "admin"

    def test_list_values(self, monkeypatch):
        monkeypatch.setenv("KEY1", "/path/to/key1.pub")
        monkeypatch.setenv("KEY2", "/path/to/key2.pub")
        data = ["${KEY1}", "${KEY2}"]
        result = _resolve_env_vars(data)
        assert result == ["/path/to/key1.pub", "/path/to/key2.pub"]

    def test_non_string_values_unchanged(self):
        """Integers, booleans, None are returned as-is."""
        data = {"port": 22, "enabled": True, "extra": None}
        result = _resolve_env_vars(data)
        assert result == {"port": 22, "enabled": True, "extra": None}

    def test_no_vars_returns_unchanged(self):
        data = {"host": "192.168.1.1", "port": 22}
        result = _resolve_env_vars(data)
        assert result == {"host": "192.168.1.1", "port": 22}

    def test_missing_var_raises_error_with_field_path(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        data = {"host": {"address": "${MISSING_VAR}"}}
        with pytest.raises(SpecLoadError, match=r"host\.address") as exc_info:
            _resolve_env_vars(data)
        assert "MISSING_VAR" in str(exc_info.value)

    def test_missing_var_in_list_includes_index_in_path(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        data = {"keys": ["ok", "${MISSING_VAR}"]}
        with pytest.raises(SpecLoadError, match=r"keys\[1\]"):
            _resolve_env_vars(data)

    def test_error_message_format(self, monkeypatch):
        monkeypatch.delenv("NO_SUCH_VAR", raising=False)
        with pytest.raises(SpecLoadError) as exc_info:
            _resolve_env_vars({"top": "${NO_SUCH_VAR}"})
        msg = str(exc_info.value)
        assert "Unresolved variable '${NO_SUCH_VAR}'" in msg
        assert "in field 'top'" in msg
        assert "'NO_SUCH_VAR' is not set" in msg


# ------------------------------------------------------------------ #
# _resolve_env_vars — passthrough mode
# ------------------------------------------------------------------ #


class TestResolveEnvVarsPassthrough:
    """Tests for _resolve_env_vars with strict=False (passthrough)."""

    def test_missing_var_left_unchanged(self, monkeypatch):
        monkeypatch.delenv("UNDEFINED_VAR", raising=False)
        result = _resolve_env_vars("${UNDEFINED_VAR}", strict=False)
        assert result == "${UNDEFINED_VAR}"

    def test_defined_var_still_resolved(self, monkeypatch):
        monkeypatch.setenv("DEFINED", "hello")
        result = _resolve_env_vars("${DEFINED}", strict=False)
        assert result == "hello"

    def test_mixed_defined_and_undefined(self, monkeypatch):
        monkeypatch.setenv("HOST", "10.0.0.1")
        monkeypatch.delenv("PORT_PLACEHOLDER", raising=False)
        result = _resolve_env_vars("${HOST}:${PORT_PLACEHOLDER}", strict=False)
        assert result == "10.0.0.1:${PORT_PLACEHOLDER}"

    def test_nested_dict_passthrough(self, monkeypatch):
        monkeypatch.setenv("KNOWN", "value")
        monkeypatch.delenv("UNKNOWN", raising=False)
        data = {"a": "${KNOWN}", "b": "${UNKNOWN}"}
        result = _resolve_env_vars(data, strict=False)
        assert result["a"] == "value"
        assert result["b"] == "${UNKNOWN}"


# ------------------------------------------------------------------ #
# load_env_file
# ------------------------------------------------------------------ #


class TestLoadEnvFile:
    """Tests for the .env file loader."""

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
        f.write_text("export MY_KEY=my_value\n")
        env = load_env_file(f)
        assert env == {"MY_KEY": "my_value"}

    def test_comments_and_blanks_ignored(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("# This is a comment\n\nKEY=value\n  \n# Another comment\n")
        env = load_env_file(f)
        assert env == {"KEY": "value"}

    def test_value_with_equals_sign(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("CONNECTION=host=db port=5432\n")
        env = load_env_file(f)
        assert env["CONNECTION"] == "host=db port=5432"

    def test_empty_value(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("EMPTY=\n")
        env = load_env_file(f)
        assert env == {"EMPTY": ""}

    def test_whitespace_trimmed(self, tmp_path):
        f = tmp_path / ".env"
        f.write_text("  KEY  =  value  \n")
        env = load_env_file(f)
        assert env == {"KEY": "value"}


# ------------------------------------------------------------------ #
# load_spec with env_file integration
# ------------------------------------------------------------------ #

try:
    import pydantic  # noqa: F401

    _HAS_PYDANTIC = True
except ImportError:
    _HAS_PYDANTIC = False

_needs_pydantic = pytest.mark.skipif(not _HAS_PYDANTIC, reason="pydantic not installed")


@_needs_pydantic
class TestLoadSpecEnvFile:
    """Integration tests for load_spec() with --env-file support."""

    def test_env_file_vars_resolved_in_spec(self, tmp_path, monkeypatch):
        """Variables from .env file are used to resolve spec references."""
        env_f = tmp_path / ".env"
        env_f.write_text("MY_ADDR=10.0.0.99\n")

        spec_f = tmp_path / "spec.yaml"
        spec_f.write_text(
            textwrap.dedent("""\
            kind: service
            meta:
              name: test-svc
              description: env-file test
            host:
              name: node-1
              address: "${MY_ADDR}"
              os_family: debian
            login:
              user: admin
              private_key: ~/.ssh/id_ed25519
              port: 2222
            local:
              inventory:
                enabled: false
            checks: []
        """)
        )

        # Ensure the var is NOT in the process env
        monkeypatch.delenv("MY_ADDR", raising=False)

        spec = load_spec(spec_f, env_file=env_f)
        assert spec.host.address == "10.0.0.99"

    def test_env_file_does_not_override_existing_env(self, tmp_path, monkeypatch):
        """Existing environment variables take precedence over .env file."""
        env_f = tmp_path / ".env"
        env_f.write_text("MY_ADDR=from-file\n")

        monkeypatch.setenv("MY_ADDR", "from-env")

        spec_f = tmp_path / "spec.yaml"
        spec_f.write_text(
            textwrap.dedent("""\
            kind: service
            meta:
              name: test-svc
              description: env precedence test
            host:
              name: node-1
              address: "${MY_ADDR}"
              os_family: debian
            login:
              user: admin
              private_key: ~/.ssh/id_ed25519
              port: 2222
            local:
              inventory:
                enabled: false
            checks: []
        """)
        )

        spec = load_spec(spec_f, env_file=env_f)
        assert spec.host.address == "from-env"

    def test_env_file_not_found_raises_error(self, tmp_path):
        spec_f = tmp_path / "spec.yaml"
        spec_f.write_text("kind: service\n")
        with pytest.raises(SpecLoadError, match="Env file not found"):
            load_spec(spec_f, env_file=tmp_path / "missing.env")

    def test_passthrough_mode_with_load_spec(self, tmp_path, monkeypatch):
        """strict_env=False leaves unresolved vars in place (may fail schema)."""
        monkeypatch.delenv("UNSET_VAR", raising=False)

        spec_f = tmp_path / "spec.yaml"
        spec_f.write_text(
            textwrap.dedent("""\
            kind: service
            meta:
              name: test-svc
              description: "${UNSET_VAR}"
            host:
              name: node-1
              address: 10.0.0.1
              os_family: debian
            login:
              user: admin
              private_key: ~/.ssh/id_ed25519
              port: 2222
            local:
              inventory:
                enabled: false
            checks: []
        """)
        )

        # Passthrough mode should NOT raise during env var resolution
        spec = load_spec(spec_f, strict_env=False)
        assert spec.meta.description == "${UNSET_VAR}"
