"""Tests for secret rotation module."""

import os

from nodeforge.runtime.secret_rotation import (
    SecretRef,
    find_secret_refs,
    generate_password,
    rotate_secret,
)
from nodeforge_core.specs.postgres_ensure_schema import PostgresEnsureSpec


def _make_pg_spec(**overrides) -> PostgresEnsureSpec:
    base = {
        "kind": "postgres_ensure",
        "meta": {"name": "test-pg", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "users": [{"name": "app_user", "password_env": "APP_DB_PASSWORD"}],
        "databases": [{"name": "app_db", "owner": "app_user"}],
    }
    base.update(overrides)
    return PostgresEnsureSpec.model_validate(base)


class TestFindSecretRefs:
    def test_finds_password_env_in_postgres_ensure(self):
        spec = _make_pg_spec()
        refs = find_secret_refs(spec)
        assert len(refs) == 1
        assert refs[0].env_var == "APP_DB_PASSWORD"
        assert refs[0].kind == "postgres_ensure"

    def test_no_refs_when_no_password_env(self):
        spec = _make_pg_spec(users=[{"name": "app_user"}])
        refs = find_secret_refs(spec)
        assert len(refs) == 0

    def test_multiple_users_with_password_env(self):
        spec = _make_pg_spec(
            users=[
                {"name": "u1", "password_env": "PW1"},
                {"name": "u2", "password_env": "PW2"},
            ]
        )
        refs = find_secret_refs(spec)
        assert len(refs) == 2
        assert {r.env_var for r in refs} == {"PW1", "PW2"}


class TestGeneratePassword:
    def test_default_length(self):
        pw = generate_password()
        assert len(pw) == 32

    def test_custom_length(self):
        pw = generate_password(length=16)
        assert len(pw) == 16

    def test_passwords_are_unique(self):
        passwords = {generate_password() for _ in range(10)}
        assert len(passwords) == 10


class TestRotateSecret:
    def test_rotate_sets_env_var(self):
        spec = _make_pg_spec()
        result = rotate_secret(spec, "APP_DB_PASSWORD", "new-pw")
        assert result.new_value == "new-pw"
        assert os.environ["APP_DB_PASSWORD"] == "new-pw"
        assert len(result.refs_found) == 1
        assert result.error is None

    def test_rotate_generates_password_if_none(self):
        spec = _make_pg_spec()
        result = rotate_secret(spec, "APP_DB_PASSWORD")
        assert len(result.new_value) == 32
        assert os.environ["APP_DB_PASSWORD"] == result.new_value

    def test_rotate_unknown_secret(self):
        spec = _make_pg_spec()
        result = rotate_secret(spec, "NONEXISTENT_SECRET")
        assert result.error is not None
        assert "No references" in result.error

    def test_rotate_returns_matching_refs(self):
        spec = _make_pg_spec()
        result = rotate_secret(spec, "APP_DB_PASSWORD", "val")
        assert all(isinstance(r, SecretRef) for r in result.refs_found)
