# Bootstrap with WireGuard Restricted Peers Example

Demonstrates the most locked-down bootstrap configuration: SSH access is restricted to only the registered WireGuard peer IP on the WireGuard interface.

## What it does

1. Hardens the server (admin user, SSH keys, firewall)
2. Sets up WireGuard VPN (`wg0` on `10.10.0.0/24`)
3. Restricts SSH to the WireGuard interface only (`registered_peers_only: true`)
4. After bootstrap, SSH is only accessible from `10.10.0.2` on the `wg0` interface

## Security Model

```
Internet ──X──> SSH (blocked on all interfaces)
WireGuard VPN ──> SSH (only from 10.10.0.2 on wg0)
```

With `registered_peers_only: true`, the UFW rule restricts SSH to both:
- The WireGuard interface (`in on wg0`)
- The specific peer IP (`from 10.10.0.2`)

Without `registered_peers_only`, SSH would be allowed from any IP on the WireGuard interface.

## Usage

```bash
nodeforge validate examples/bootstrap-wireguard-restricted/bootstrap-wireguard-restricted.yaml
nodeforge plan examples/bootstrap-wireguard-restricted/bootstrap-wireguard-restricted.yaml
nodeforge apply examples/bootstrap-wireguard-restricted/bootstrap-wireguard-restricted.yaml
```

## Prerequisites

- A fresh server with root SSH access
- WireGuard server private key at `.secrets/wg.key` (relative to spec directory)
- `~/.ssh/id_ed25519.pub` exists locally

## Notes

- The `registered_peers_only` flag requires `wireguard.enabled: true` to have any effect
- This is the recommended production configuration for maximum security
