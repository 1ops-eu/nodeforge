"""Tests for the value resolver registry (nodeforge/registry/resolvers.py)."""

from __future__ import annotations

import pytest

from nodeforge.registry.resolvers import (
    _RESOLVER_REGISTRY,
    register_resolver,
    get_resolver,
    list_resolvers,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _isolated_registry(monkeypatch):
    """Monkeypatch the registry dict to be empty for the duration of a test."""
    monkeypatch.setattr("nodeforge.registry.resolvers._RESOLVER_REGISTRY", {})


# ------------------------------------------------------------------ #
# register_resolver / get_resolver
# ------------------------------------------------------------------ #


class TestRegisterAndGet:
    def test_register_and_retrieve(self, monkeypatch):
        _isolated_registry(monkeypatch)
        fn = lambda key: "resolved"
        register_resolver("test", fn)
        assert get_resolver("test") is fn

    def test_unknown_prefix_returns_none(self, monkeypatch):
        _isolated_registry(monkeypatch)
        assert get_resolver("nonexistent") is None

    def test_overwrite_existing_resolver(self, monkeypatch):
        _isolated_registry(monkeypatch)
        fn1 = lambda key: "first"
        fn2 = lambda key: "second"
        register_resolver("x", fn1)
        register_resolver("x", fn2)
        assert get_resolver("x") is fn2

    def test_resolver_is_callable(self, monkeypatch):
        _isolated_registry(monkeypatch)
        register_resolver("echo", lambda key: key.upper())
        resolver = get_resolver("echo")
        assert resolver("hello") == "HELLO"

    def test_resolver_returning_none(self, monkeypatch):
        _isolated_registry(monkeypatch)
        register_resolver("empty", lambda key: None)
        resolver = get_resolver("empty")
        assert resolver("anything") is None

    def test_multiple_prefixes_independent(self, monkeypatch):
        _isolated_registry(monkeypatch)
        register_resolver("a", lambda key: f"a:{key}")
        register_resolver("b", lambda key: f"b:{key}")
        assert get_resolver("a")("x") == "a:x"
        assert get_resolver("b")("x") == "b:x"


# ------------------------------------------------------------------ #
# list_resolvers
# ------------------------------------------------------------------ #


class TestListResolvers:
    def test_empty_registry(self, monkeypatch):
        _isolated_registry(monkeypatch)
        assert list_resolvers() == []

    def test_single_resolver(self, monkeypatch):
        _isolated_registry(monkeypatch)
        register_resolver("only", lambda key: None)
        assert list_resolvers() == ["only"]

    def test_multiple_resolvers_sorted(self, monkeypatch):
        _isolated_registry(monkeypatch)
        register_resolver("z", lambda key: None)
        register_resolver("a", lambda key: None)
        register_resolver("m", lambda key: None)
        assert list_resolvers() == ["a", "m", "z"]

    def test_returns_list_not_view(self, monkeypatch):
        _isolated_registry(monkeypatch)
        result = list_resolvers()
        assert isinstance(result, list)


# ------------------------------------------------------------------ #
# Built-in resolvers registered after load_addons()
# ------------------------------------------------------------------ #


class TestBuiltinResolvers:
    """Integration tests for the built-in 'env' and 'file' resolvers.

    These tests call load_addons() to ensure the resolvers are registered,
    but use the resolver functions through the public API.
    """

    def test_env_resolver_registered(self):
        from nodeforge.registry import load_addons

        load_addons()
        assert get_resolver("env") is not None

    def test_file_resolver_registered(self):
        from nodeforge.registry import load_addons

        load_addons()
        assert get_resolver("file") is not None

    def test_env_resolver_reads_os_environ(self, monkeypatch):
        from nodeforge.registry import load_addons

        load_addons()
        monkeypatch.setenv("NF_TEST_KEY", "test-value-xyz")
        resolver = get_resolver("env")
        assert resolver("NF_TEST_KEY") == "test-value-xyz"

    def test_env_resolver_returns_none_for_missing(self, monkeypatch):
        from nodeforge.registry import load_addons

        load_addons()
        monkeypatch.delenv("NF_DEFINITELY_NOT_SET", raising=False)
        resolver = get_resolver("env")
        assert resolver("NF_DEFINITELY_NOT_SET") is None

    def test_file_resolver_reads_file(self, tmp_path):
        from nodeforge.registry import load_addons

        load_addons()
        key_file = tmp_path / "key.pub"
        key_file.write_text("ssh-ed25519 AAAA...publickey\n")
        resolver = get_resolver("file")
        assert resolver(str(key_file)) == "ssh-ed25519 AAAA...publickey"

    def test_file_resolver_strips_trailing_newline(self, tmp_path):
        from nodeforge.registry import load_addons

        load_addons()
        f = tmp_path / "value.txt"
        f.write_text("myvalue\n")
        resolver = get_resolver("file")
        assert resolver(str(f)) == "myvalue"

    def test_file_resolver_returns_none_for_missing(self, tmp_path):
        from nodeforge.registry import load_addons

        load_addons()
        resolver = get_resolver("file")
        assert resolver(str(tmp_path / "nonexistent.txt")) is None

    def test_both_builtin_prefixes_appear_in_list(self):
        from nodeforge.registry import load_addons

        load_addons()
        resolvers = list_resolvers()
        assert "env" in resolvers
        assert "file" in resolvers
