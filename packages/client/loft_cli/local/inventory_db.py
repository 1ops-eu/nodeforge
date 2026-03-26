"""Local SQLite inventory database with versionize historization.

Uses Python's built-in sqlite3 — no native dependencies, works on all platforms.
The schema, temporal versioning pattern, and all queries are identical to the
former SQLCipher implementation; the commercial edition can swap in encryption
by replacing `import sqlite3` with `from sqlcipher3 import dbapi2 as sqlite3`
and adding the two PRAGMA key/cipher_compatibility calls in open().
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from loft_cli.local.ddl.bootstrap_tables import DOMAIN_TABLES
from loft_cli.local.ddl.versionize_system import VERSIONIZE_SYSTEM_DDLS


class InventoryDB:
    """Local SQLite inventory database with versionize historization."""

    DEFAULT_DB_PATH = "~/.loft-cli/inventory.db"

    def __init__(self, db_path: str | None = None) -> None:
        self._path = Path(db_path or self.DEFAULT_DB_PATH).expanduser()
        self._conn = None
        self._cursor = None

    # ------------------------------------------------------------------ #
    # Connection lifecycle
    # ------------------------------------------------------------------ #

    def open(self) -> None:
        """Open (or create) the SQLite database."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._cursor = self._conn.cursor()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None
            self._cursor = None

    def __enter__(self) -> InventoryDB:
        self.open()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Initialization
    # ------------------------------------------------------------------ #

    def initialize(self) -> None:
        """Create the versionize system + domain tables + activate historization.

        Idempotent — safe to call on an already-initialized database.
        """
        for ddl in VERSIONIZE_SYSTEM_DDLS:
            self._cursor.executescript(ddl)

        for table_name, table_ddl in DOMAIN_TABLES:
            self._cursor.executescript(table_ddl)
            self._versionize_table(table_name)

    def _versionize_table(self, table_name: str) -> None:
        """Activate versionize historization on a tv_* table."""
        result = self._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='vv' || SUBSTR(?, 3);",
            (table_name,),
        )
        if result.fetchone()[0] > 0:
            return

        self._cursor.executescript(
            f"INSERT INTO t_versionize_jobs (table_name) VALUES ('{table_name}');"
        )

        result = self._conn.execute(
            "SELECT view_ddl, trigger_insert_ddl, trigger_update_ddl, trigger_delete_ddl "
            "FROM t_versionize_ddl WHERE table_name = ?;",
            (table_name,),
        )
        ddl_row = result.fetchone()
        if ddl_row is None:
            raise RuntimeError(f"versionize trigger did not generate DDL for {table_name}")

        view_ddl, trigger_insert_ddl, trigger_update_ddl, trigger_delete_ddl = ddl_row

        self._cursor.executescript(view_ddl)
        self._cursor.executescript(trigger_insert_ddl)
        self._cursor.executescript(trigger_update_ddl)
        self._cursor.executescript(trigger_delete_ddl)

        self._cursor.executescript(
            f"DELETE FROM t_versionize_jobs WHERE table_name = '{table_name}';"
            f"DELETE FROM t_versionize_ddl WHERE table_name = '{table_name}';"
        )

    # ------------------------------------------------------------------ #
    # Server CRUD (via vv_server view)
    # ------------------------------------------------------------------ #

    def upsert_server(
        self,
        id: str,
        name: str,
        address: str,
        bootstrap_status: str,
        os_family: str = "",
        ssh_alias: str = "",
        ssh_host: str = "",
        ssh_user: str = "",
        ssh_port: int | None = None,
        ssh_identity_file: str = "",
        wireguard_enabled: bool = False,
        wireguard_interface: str = "",
        wireguard_address: str = "",
        changed_by: str = "loft-cli",
    ) -> None:
        """INSERT INTO vv_server — versionize trigger handles history."""
        self._conn.execute(
            """
            INSERT INTO vv_server (
                id, name, address, os_family, bootstrap_status,
                ssh_alias, ssh_host, ssh_user, ssh_port, ssh_identity_file,
                wireguard_enabled, wireguard_interface, wireguard_address,
                version_changed_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id,
                name,
                address,
                os_family,
                bootstrap_status,
                ssh_alias,
                ssh_host,
                ssh_user,
                ssh_port,
                ssh_identity_file,
                1 if wireguard_enabled else 0,
                wireguard_interface,
                wireguard_address,
                changed_by,
            ),
        )
        self._conn.commit()

    def get_server(self, server_id: str) -> dict | None:
        result = self._conn.execute("SELECT * FROM vv_server WHERE id = ?", (server_id,))
        row = result.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in result.description]
        return dict(zip(cols, row, strict=False))

    def list_servers(self) -> list[dict]:
        result = self._conn.execute("SELECT * FROM vv_server ORDER BY name")
        cols = [d[0] for d in result.description]
        return [dict(zip(cols, row, strict=False)) for row in result.fetchall()]

    # ------------------------------------------------------------------ #
    # Service CRUD (via vv_server_service view)
    # ------------------------------------------------------------------ #

    def upsert_service(
        self,
        server_id: str,
        service_type: str,
        service_name: str,
        status: str,
        metadata_json: str = "",
        changed_by: str = "loft-cli",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO vv_server_service (
                server_id, service_type, service_name, status, metadata_json,
                version_changed_by
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (server_id, service_type, service_name, status, metadata_json, changed_by),
        )
        self._conn.commit()

    def get_services(self, server_id: str) -> list[dict]:
        result = self._conn.execute(
            "SELECT * FROM vv_server_service WHERE server_id = ?", (server_id,)
        )
        cols = [d[0] for d in result.description]
        return [dict(zip(cols, row, strict=False)) for row in result.fetchall()]

    # ------------------------------------------------------------------ #
    # Run metadata (via vv_run view)
    # ------------------------------------------------------------------ #

    def record_run(
        self,
        id: str,
        kind: str,
        spec_hash: str,
        plan_hash: str,
        status: str,
        started_at: str,
        finished_at: str = "",
        server_id: str = "",
        metadata_json: str = "",
        changed_by: str = "loft-cli",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO vv_run (
                id, server_id, spec_hash, plan_hash, kind, status,
                started_at, finished_at, metadata_json, version_changed_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                id,
                server_id,
                spec_hash,
                plan_hash,
                kind,
                status,
                started_at,
                finished_at,
                metadata_json,
                changed_by,
            ),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> dict | None:
        result = self._conn.execute("SELECT * FROM vv_run WHERE id = ?", (run_id,))
        row = result.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in result.description]
        return dict(zip(cols, row, strict=False))

    def list_runs(self, server_id: str | None = None) -> list[dict]:
        if server_id:
            result = self._conn.execute(
                "SELECT * FROM vv_run WHERE server_id = ? ORDER BY started_at DESC",
                (server_id,),
            )
        else:
            result = self._conn.execute("SELECT * FROM vv_run ORDER BY started_at DESC")
        cols = [d[0] for d in result.description]
        return [dict(zip(cols, row, strict=False)) for row in result.fetchall()]
