# Bootstrap with Password Login Example

Demonstrates bootstrapping a server using root password authentication instead of an SSH key.

## What it does

1. Connects to the server using root password (from `$ROOT_PASSWORD` env var)
2. Creates an admin user with SSH key-based authentication
3. Disables root login and password authentication
4. After bootstrap, only key-based SSH access is allowed

## Usage

```bash
export ROOT_PASSWORD="your-root-password"

nodeforge validate examples/bootstrap-password-login/bootstrap-password-login.yaml
nodeforge plan examples/bootstrap-password-login/bootstrap-password-login.yaml
nodeforge apply examples/bootstrap-password-login/bootstrap-password-login.yaml
```

## Prerequisites

- A fresh server with root password login enabled (common with cloud providers)
- `~/.ssh/id_ed25519.pub` exists locally (will be installed as admin user's authorized key)

## Notes

- The `login.password` field is used for initial root login only
- After bootstrap, password auth is disabled (`disable_password_auth: true`)
- The password is resolved from an environment variable to avoid storing secrets in the spec file
