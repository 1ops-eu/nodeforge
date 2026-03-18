# 02 — SSH Key, No Password

Builds on 01: deploys the admin user's SSH public key and disables password authentication.

## What it does

1. Creates the `admin` user with sudo
2. Deploys `~/.ssh/id_ed25519.pub` to admin's `authorized_keys`
3. Disables root login and password authentication
4. After bootstrap, only key-based SSH access works

## Key settings

- `disable_password_auth: true` — password login is disabled
- `pubkeys: [~/.ssh/id_ed25519.pub]` — public key is deployed

## Security note

Once password auth is disabled, losing the SSH private key means losing access to the server. The SSH lockout prevention gate verifies admin login before making this change.

## Goss verification

The accompanying `02-ssh-key-no-password.goss.yaml` validates the expected server state after apply.
