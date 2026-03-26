# PostgreSQL Ensure Example

Ensure PostgreSQL resources exist on a running instance.

## What it does

1. Connects to the target server via SSH
2. Verifies PostgreSQL is accepting connections
3. Ensures the specified users exist (creates if missing)
4. Ensures the specified databases exist (creates if missing)
5. Ensures extensions are installed in the target databases
6. Applies privilege grants

## Usage

```bash
export APP_DB_PASSWORD="secure-password-here"
loft-cli validate examples/postgres-ensure/postgres-ensure.yaml
loft-cli plan examples/postgres-ensure/postgres-ensure.yaml
loft-cli apply examples/postgres-ensure/postgres-ensure.yaml
```

## Connection Modes

- **Docker exec**: Set `connection.docker_exec` to the container name
- **Host/port**: Use `connection.host` and `connection.port` for direct connection

## Notes

- Every action is a discrete, reviewable plan step
- No arbitrary SQL -- only structured declarations (users, databases, extensions, grants)
- User passwords are resolved from environment variables at plan time
- All operations are idempotent -- safe to re-run
