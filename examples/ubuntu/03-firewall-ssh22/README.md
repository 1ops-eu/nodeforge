# 03 — Firewall, SSH on Port 22

Builds on 02: enables UFW firewall with SSH-only inbound policy on the default port 22.

## What it does

1. All hardening from 01 + 02
2. Enables UFW firewall
3. Sets default deny incoming policy
4. Allows only SSH (port 22) inbound

## Key settings

- `firewall.provider: ufw`
- `firewall.ssh_only: true` — only SSH port is allowed
- `ssh.port: 22` — SSH stays on the default port

## Goss verification

The accompanying `03-firewall-ssh22.goss.yaml` validates the expected server state after apply.
