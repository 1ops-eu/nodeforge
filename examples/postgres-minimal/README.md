# Postgres Minimal Example

Installs PostgreSQL 16 with default settings. No roles or databases are created.

## What it does

1. Installs PostgreSQL 16 from apt
2. Configures listen addresses to localhost only (default)
3. Enables and starts the PostgreSQL systemd service
4. Verifies readiness via `pg_isready`

## Usage

```bash
loft-cli validate examples/postgres-minimal/postgres-minimal.yaml
loft-cli plan examples/postgres-minimal/postgres-minimal.yaml
loft-cli apply examples/postgres-minimal/postgres-minimal.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222

## Notes

- This is the simplest PostgreSQL setup. For role/database creation, see `examples/postgres.yaml`.
- The `create_role` and `create_database` fields are omitted — only the PostgreSQL service is installed and started.
