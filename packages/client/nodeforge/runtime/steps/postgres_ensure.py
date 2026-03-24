"""SQL command generators for kind: postgres_ensure steps.

Generates idempotent psql commands for ensuring PostgreSQL resources exist.
All commands are wrapped for execution via shell (directly or docker exec).
"""

from __future__ import annotations


def _psql_wrap(sql: str, *, conn_host: str, conn_port: int, admin_user: str,
               docker_exec: str | None = None, database: str = "postgres") -> str:
    """Wrap a SQL statement in a psql command, optionally via docker exec."""
    escaped_sql = sql.replace("'", "'\\''")
    if docker_exec:
        return (
            f"docker exec {docker_exec} psql -U {admin_user} -d {database} "
            f"-c '{escaped_sql}'"
        )
    # Use Unix socket via sudo to avoid TCP password auth (scram-sha-256).
    # The SSH admin user has NOPASSWD sudo (nodeforge bootstrap invariant).
    return f"sudo -u {admin_user} psql -d {database} -c '{escaped_sql}'"


def ensure_user_cmd(
    name: str, password: str | None, *,
    conn_host: str, conn_port: int, admin_user: str,
    docker_exec: str | None = None,
) -> str:
    """Generate command to ensure a PostgreSQL user exists."""
    if password:
        sql = (
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{name}') THEN "
            f"CREATE ROLE {name} LOGIN PASSWORD '{password}'; "
            f"ELSE ALTER ROLE {name} PASSWORD '{password}'; "
            f"END IF; END $$;"
        )
    else:
        sql = (
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{name}') THEN "
            f"CREATE ROLE {name} LOGIN; "
            f"END IF; END $$;"
        )
    return _psql_wrap(sql, conn_host=conn_host, conn_port=conn_port,
                      admin_user=admin_user, docker_exec=docker_exec)


def ensure_database_cmd(
    name: str, owner: str, *,
    conn_host: str, conn_port: int, admin_user: str,
    docker_exec: str | None = None,
) -> str:
    """Generate command to ensure a PostgreSQL database exists."""
    # createdb is idempotent-ish: check existence first
    check = f"SELECT 1 FROM pg_database WHERE datname='{name}'"
    if docker_exec:
        return (
            f"docker exec {docker_exec} bash -c "
            f"\"psql -U {admin_user} -tc \\\"{check}\\\" | grep -q 1 "
            f"|| createdb -U {admin_user} -O {owner} {name}\""
        )
    return (
        f"sudo -u {admin_user} bash -c "
        f"\"psql -tc \\\"{check}\\\" | grep -q 1 "
        f"|| createdb -O {owner} {name}\""
    )


def ensure_extension_cmd(
    name: str, database: str, *,
    conn_host: str, conn_port: int, admin_user: str,
    docker_exec: str | None = None,
) -> str:
    """Generate command to ensure a PostgreSQL extension is installed."""
    sql = f"CREATE EXTENSION IF NOT EXISTS {name};"
    return _psql_wrap(sql, conn_host=conn_host, conn_port=conn_port,
                      admin_user=admin_user, docker_exec=docker_exec,
                      database=database)


def ensure_grant_cmd(
    privilege: str, on_database: str, to_user: str, *,
    conn_host: str, conn_port: int, admin_user: str,
    docker_exec: str | None = None,
) -> str:
    """Generate command to grant a privilege."""
    sql = f"GRANT {privilege} ON DATABASE {on_database} TO {to_user};"
    return _psql_wrap(sql, conn_host=conn_host, conn_port=conn_port,
                      admin_user=admin_user, docker_exec=docker_exec)


def pg_isready_cmd(
    *, conn_host: str, conn_port: int, admin_user: str,
    docker_exec: str | None = None,
) -> str:
    """Generate command to check PostgreSQL readiness."""
    if docker_exec:
        return f"docker exec {docker_exec} pg_isready -U {admin_user}"
    return f"sudo -u {admin_user} pg_isready"
