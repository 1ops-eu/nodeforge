"""PostgreSQL installation and configuration commands.

IMPORTANT — Fabric sudo() compatibility:
  See bootstrap.py module docstring for details.  Functions here follow
  the same pattern: compound commands are wrapped in ``bash -c '...'``
  so Fabric's ``sudo()`` elevates the entire operation.

PGDG Repository:
  Ubuntu/Debian ship a single PostgreSQL version per release (e.g. PG 14
  on Ubuntu 22.04).  To install any other version we add the official
  PostgreSQL Global Development Group (PGDG) apt repository first.  The
  planner emits these steps unconditionally — adding the repo is
  idempotent and ensures the exact requested version is always available.
"""

from __future__ import annotations

# ── PGDG Repository setup ───────────────────────────────────────────


def install_pgdg_prerequisites() -> str:
    """Install packages required to add the PGDG apt repository."""
    return "DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates gnupg"


def add_pgdg_signing_key() -> str:
    """Import the PGDG apt repository signing key.

    Downloads the key and stores it in ``/usr/share/keyrings/`` for use
    with signed-by apt sources (the modern approach replacing apt-key).
    Wrapped in ``bash -c`` because of the pipe.
    """
    return (
        "bash -c '"
        "install -d /usr/share/postgresql-common/pgdg && "
        "curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc "
        "--fail https://www.postgresql.org/media/keys/ACCC4CF8.asc"
        "'"
    )


def add_pgdg_source_list() -> str:
    """Add the PGDG apt repository source list.

    Uses the signed-by mechanism with the key installed by
    ``add_pgdg_signing_key()``.  Wrapped in ``bash -c`` because of the
    redirect (``>``).
    """
    return (
        "bash -c '"
        'echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] '
        'https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" '
        "> /etc/apt/sources.list.d/pgdg.list"
        "'"
    )


# ── PostgreSQL installation and management ───────────────────────────


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
    # Use double quotes for bash -c so SQL single quotes (PASSWORD '...')
    # pass through safely.  Inner double quotes escaped with backslash.
    return (
        f'bash -c "sudo -u postgres psql -c \\"{sql}\\" 2>/dev/null || echo Role_may_already_exist"'
    )


def create_database(name: str, owner: str) -> str:
    if owner:
        sql = f"CREATE DATABASE {name} OWNER {owner};"
    else:
        sql = f"CREATE DATABASE {name};"
    return (
        f'bash -c "sudo -u postgres psql -c \\"{sql}\\" 2>/dev/null '
        f'|| echo Database_may_already_exist"'
    )


def postgres_ready_check() -> str:
    return "pg_isready"
