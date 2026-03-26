# Bootstrap with Environment Variables Example

Demonstrates the `${env:VAR}` and `${VAR:-default}` syntax for injecting environment variables into spec fields.

## What it does

Uses environment variable resolution to parameterize:
- `host.address` — from `$SERVER_IP`
- `login.private_key` — from `$SSH_KEY_PATH` with fallback to `~/.ssh/id_ed25519`
- `admin_user.name` — from `$ADMIN_USER` with fallback to `deploy`
- `admin_user.pubkeys` — from `$ADMIN_PUBKEY` with fallback to `~/.ssh/id_ed25519.pub`

## Usage

```bash
export SERVER_IP=203.0.113.10
export ADMIN_USER=deploy

loft-cli validate examples/bootstrap-env-vars/bootstrap-env-vars.yaml
loft-cli plan examples/bootstrap-env-vars/bootstrap-env-vars.yaml
loft-cli apply examples/bootstrap-env-vars/bootstrap-env-vars.yaml
```

## Variable Resolution Syntax

| Syntax | Meaning |
|---|---|
| `${VAR}` | Bare env var lookup (shorthand for `${env:VAR}`) |
| `${env:VAR}` | Explicit env var lookup |
| `${VAR:-default}` | Env var with default fallback |
| `${file:/path}` | Read file contents |

## Notes

- In strict mode (default), unresolved variables without defaults cause an error with the exact field path
- Use `--no-strict-env` to leave unresolved tokens unchanged (useful for dry-run previews)
