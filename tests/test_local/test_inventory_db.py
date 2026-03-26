"""Tests for the SQLite inventory database."""

from __future__ import annotations

import pytest

from loft_cli.local.inventory_db import InventoryDB


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_inventory.db")
    db = InventoryDB(db_path=db_path)
    db.open()
    db.initialize()
    yield db
    db.close()


def test_initialize_creates_tables(db):
    """After init, vv_server view should exist."""
    result = db._conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='vv_server'"
    )
    assert result.fetchone()[0] == 1


def test_initialize_creates_all_views(db):
    """All three domain views should exist after init."""
    for view in ("vv_server", "vv_server_service", "vv_run"):
        result = db._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name=?", (view,)
        )
        assert result.fetchone()[0] == 1, f"View {view} not found"


def test_upsert_server(db):
    db.upsert_server(
        id="srv-1",
        name="test-server",
        address="10.0.0.1",
        bootstrap_status="bootstrapped",
        ssh_user="deploy",
        ssh_port=2222,
    )
    server = db.get_server("srv-1")
    assert server is not None
    assert server["name"] == "test-server"
    assert server["bootstrap_status"] == "bootstrapped"
    assert server["ssh_user"] == "deploy"


def test_list_servers(db):
    db.upsert_server(id="s1", name="alpha", address="1.1.1.1", bootstrap_status="bootstrapped")
    db.upsert_server(id="s2", name="beta", address="2.2.2.2", bootstrap_status="bootstrapped")
    servers = db.list_servers()
    assert len(servers) == 2
    assert {s["name"] for s in servers} == {"alpha", "beta"}


def test_upsert_service(db):
    db.upsert_service(
        server_id="srv-1",
        service_type="postgres",
        service_name="postgresql-16",
        status="active",
    )
    services = db.get_services("srv-1")
    assert len(services) == 1
    assert services[0]["service_type"] == "postgres"


def test_record_run(db):
    db.record_run(
        id="run-001",
        kind="bootstrap",
        spec_hash="abc123",
        plan_hash="def456",
        status="success",
        started_at="2026-03-14T10:00:00Z",
        finished_at="2026-03-14T10:05:00Z",
        server_id="srv-1",
    )
    run = db.get_run("run-001")
    assert run is not None
    assert run["kind"] == "bootstrap"
    assert run["status"] == "success"


def test_initialize_is_idempotent(tmp_path):
    """Calling initialize() twice should not raise."""
    db_path = str(tmp_path / "idempotent.db")
    db = InventoryDB(db_path=db_path)
    db.open()
    db.initialize()
    db.initialize()
    db.close()


def test_context_manager(tmp_path):
    db_path = str(tmp_path / "ctx.db")
    with InventoryDB(db_path=db_path) as db:
        db.initialize()
        db.upsert_server(id="x", name="x", address="0.0.0.0", bootstrap_status="bootstrapped")
    assert db._conn is None
