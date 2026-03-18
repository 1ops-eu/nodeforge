"""PostgreSQL installation and configuration commands."""

from __future__ import annotations


def install_postgres(version: str) -> str:
    return f"DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-{version}"


def configure_listen(addresses: list[str]) -> str:
    addr_value = ", ".join(addresses)
    return (
        f"sed -i \"s/^#\\?listen_addresses.*/listen_addresses = '{addr_value}'/\" "
        f"/etc/postgresql/*/main/postgresql.conf"
    )


def enable_postgres() -> str:
    return "systemctl enable --now postgresql"


def create_role(name: str, password: str) -> str:
    if password:
        sql = f"CREATE ROLE {name} WITH LOGIN PASSWORD '{password}';"
    else:
        sql = f"CREATE ROLE {name} WITH LOGIN;"
    return f"sudo -u postgres psql -c \"{sql}\" 2>/dev/null || echo 'Role may already exist'"


def create_database(name: str, owner: str) -> str:
    if owner:
        sql = f"CREATE DATABASE {name} OWNER {owner};"
    else:
        sql = f"CREATE DATABASE {name};"
    return f"sudo -u postgres psql -c \"{sql}\" 2>/dev/null || echo 'Database may already exist'"


def postgres_ready_check() -> str:
    return "pg_isready"
