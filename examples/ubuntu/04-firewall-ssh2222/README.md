# 04 — Firewall, SSH on Port 2222

Builds on 03: moves SSH to non-standard port 2222 and updates UFW rules accordingly.

## What it does

1. All hardening from 01 + 02 + 03
2. Reconfigures SSH daemon to listen on port 2222
3. Updates UFW to allow port 2222 instead of 22
4. After bootstrap, SSH is only accessible on port 2222

## Key settings

- `ssh.port: 2222` — SSH moves to non-standard port
- `login.port: 22` — initial login is still on port 22 (before change)

## SSH lockout prevention

The GATE step `verify_admin_login_on_new_port` verifies that the admin user can log in on port 2222 before disabling root access. If the gate fails, root login is preserved.

## Goss verification

The accompanying `04-firewall-ssh2222.goss.yaml` validates the expected server state after apply.
