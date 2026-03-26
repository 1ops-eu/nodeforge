"""Tests for postgres_ensure kind -- schema, validation, step helpers, and planning."""

import pytest
from pydantic import ValidationError

from loft_cli.runtime.steps.postgres_ensure import (
    ensure_database_cmd,
    ensure_extension_cmd,
    ensure_grant_cmd,
    ensure_user_cmd,
    pg_isready_cmd,
)
from loft_cli_core.specs.postgres_ensure_schema import (
    PgConnection,
    PgDatabase,
    PgExtension,
    PgGrant,
    PgUser,
    PostgresEnsureSpec,
)
from loft_cli_core.specs.validators import has_errors, validate_postgres_ensure

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_postgres_ensure_spec(**overrides) -> PostgresEnsureSpec:
    base = {
        "kind": "postgres_ensure",
        "meta": {"name": "test-pg", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "users": [{"name": "app_user"}],
        "databases": [{"name": "app_db", "owner": "app_user"}],
    }
    base.update(overrides)
    return PostgresEnsureSpec.model_validate(base)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestPostgresEnsureSchema:
    def test_connection_defaults(self):
        conn = PgConnection()
        assert conn.host == "localhost"
        assert conn.port == 5432
        assert conn.admin_user == "postgres"
        assert conn.docker_exec is None

    def test_user_model(self):
        u = PgUser(name="app")
        assert u.name == "app"
        assert u.password_env is None

    def test_database_model(self):
        d = PgDatabase(name="mydb")
        assert d.owner == "postgres"

    def test_extension_model(self):
        e = PgExtension(name="uuid-ossp", database="mydb")
        assert e.name == "uuid-ossp"

    def test_grant_model(self):
        g = PgGrant(privilege="ALL", on_database="mydb", to_user="app")
        assert g.privilege == "ALL"

    def test_spec_round_trip(self):
        spec = _make_postgres_ensure_spec()
        assert spec.kind == "postgres_ensure"
        assert len(spec.users) == 1
        assert len(spec.databases) == 1

    def test_spec_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_postgres_ensure_spec(extra_field="nope")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestPostgresEnsureValidation:
    def test_valid_spec(self):
        spec = _make_postgres_ensure_spec()
        issues = validate_postgres_ensure(spec)
        assert not has_errors(issues)

    def test_empty_spec(self):
        spec = _make_postgres_ensure_spec(users=[], databases=[])
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)

    def test_empty_user_name(self):
        spec = _make_postgres_ensure_spec(users=[{"name": ""}])
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)

    def test_duplicate_user_names(self):
        spec = _make_postgres_ensure_spec(users=[{"name": "app"}, {"name": "app"}])
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)

    def test_empty_database_name(self):
        spec = _make_postgres_ensure_spec(databases=[{"name": ""}])
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)

    def test_duplicate_database_names(self):
        spec = _make_postgres_ensure_spec(databases=[{"name": "db"}, {"name": "db"}])
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)

    def test_empty_extension_name(self):
        spec = _make_postgres_ensure_spec(extensions=[{"name": "", "database": "db"}])
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)

    def test_empty_extension_database(self):
        spec = _make_postgres_ensure_spec(extensions=[{"name": "ext", "database": ""}])
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)

    def test_empty_grant_fields(self):
        spec = _make_postgres_ensure_spec(
            grants=[{"privilege": "", "on_database": "db", "to_user": "u"}]
        )
        issues = validate_postgres_ensure(spec)
        assert has_errors(issues)


# ---------------------------------------------------------------------------
# Step Helpers
# ---------------------------------------------------------------------------


class TestPostgresEnsureStepHelpers:
    def test_ensure_user_no_password(self):
        cmd = ensure_user_cmd(
            "app",
            None,
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
        )
        assert "CREATE ROLE app LOGIN" in cmd
        assert "psql" in cmd

    def test_ensure_user_with_password(self):
        cmd = ensure_user_cmd(
            "app",
            "secret",
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
        )
        assert "PASSWORD" in cmd

    def test_ensure_user_docker_exec(self):
        cmd = ensure_user_cmd(
            "app",
            None,
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
            docker_exec="pg-container",
        )
        assert "docker exec pg-container" in cmd

    def test_ensure_database(self):
        cmd = ensure_database_cmd(
            "mydb",
            "app",
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
        )
        assert "createdb" in cmd
        assert "mydb" in cmd
        assert "-O app" in cmd

    def test_ensure_extension(self):
        cmd = ensure_extension_cmd(
            "uuid-ossp",
            "mydb",
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
        )
        assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in cmd

    def test_ensure_grant(self):
        cmd = ensure_grant_cmd(
            "ALL",
            "mydb",
            "app",
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
        )
        assert "GRANT ALL ON DATABASE mydb TO app" in cmd

    def test_pg_isready(self):
        cmd = pg_isready_cmd(
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
        )
        assert "pg_isready" in cmd

    def test_pg_isready_docker(self):
        cmd = pg_isready_cmd(
            conn_host="localhost",
            conn_port=5432,
            admin_user="postgres",
            docker_exec="pg",
        )
        assert "docker exec pg" in cmd


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


class TestPostgresEnsurePlanning:
    def test_plan_generates_pg_steps(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_postgres_ensure_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        assert p.spec_kind == "postgres_ensure"
        step_ids = [s.id for s in p.steps]
        assert "pg_isready_gate" in step_ids
        assert "ensure_user_app_user" in step_ids
        assert "ensure_database_app_db" in step_ids

    def test_plan_gate_step(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_postgres_ensure_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        gate = next(s for s in p.steps if s.id == "pg_isready_gate")
        assert gate.gate is True

    def test_plan_with_extensions_and_grants(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_postgres_ensure_spec(
            extensions=[{"name": "uuid-ossp", "database": "app_db"}],
            grants=[{"privilege": "ALL", "on_database": "app_db", "to_user": "app_user"}],
        )
        ctx = normalize(spec)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "ensure_extension_uuid-ossp_on_app_db" in step_ids
        assert "grant_all_app_db_to_app_user" in step_ids

    def test_plan_has_inventory_steps(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_postgres_ensure_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        inv_steps = [s for s in p.steps if "inventory" in s.tags]
        assert len(inv_steps) == 3

    def test_plan_docker_exec_connection(self):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan

        spec = _make_postgres_ensure_spec(
            connection={"docker_exec": "pg-container", "admin_user": "postgres"}
        )
        ctx = normalize(spec)
        p = plan(ctx)

        user_step = next(s for s in p.steps if s.id == "ensure_user_app_user")
        assert "docker exec pg-container" in user_step.command
