# 01 — Admin User

Creates an admin user with sudo privileges and disables root SSH login. This is the minimum hardening step.

## What it does

1. Creates the `admin` user with sudo group membership
2. Disables direct root SSH login
3. Keeps password authentication enabled (no SSH keys deployed)
4. Writes SSH config and updates inventory

## Key settings

- `ssh.port: 22` — SSH stays on the default port
- `disable_root_login: true` — root cannot SSH in
- `disable_password_auth: false` — password login still allowed
- `pubkeys: []` — no SSH keys deployed (login via password)

## Goss verification

The accompanying `01-admin-user.goss.yaml` validates the expected server state after apply.
