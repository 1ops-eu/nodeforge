# WireGuard Tunnel Lifecycle Example

Demonstrates the full WireGuard tunnel lifecycle introduced in v0.6.3:

1. **SSH-over-tunnel safety gate** — during bootstrap, loft-cli verifies SSH connectivity through the WireGuard tunnel before removing the open SSH firewall rule
2. **SSH config points through tunnel** — `~/.ssh/conf.d/loft-cli/tunnel-demo-1.conf` uses the VPN IP (`10.10.0.1`) as `HostName`, with a comment noting the tunnel dependency
3. **`loft-cli tunnel` CLI** — manage the client-side WireGuard tunnel after bootstrap
4. **`loft-cli remove`** — clean up all local state when decommissioning

## What Happens During Apply

```
1. Bootstrap server (admin user, SSH hardening, firewall)
2. Install and configure WireGuard (wg0 on 10.10.0.0/24)
3. Allow SSH on WireGuard interface (ufw rule for peer 10.10.0.2)
4. ** TUNNEL SAFETY GATE **
   a. Bring up local WireGuard tunnel (wg-quick up)
   b. Verify SSH works through VPN: deploy@10.10.0.1:2222
   c. If verification fails → open SSH rule is NOT deleted, server stays accessible
   d. If verification passes → tunnel is torn down, proceed to step 5
5. Delete the open-to-all SSH rule (SSH now only via WireGuard)
6. Write local SSH config with VPN IP as HostName
```

## After Bootstrap

The generated SSH config at `~/.ssh/conf.d/loft-cli/tunnel-demo-1.conf`:

```
# loft-cli managed: tunnel-demo-1
# Requires: loft-cli tunnel up tunnel-demo-1
Host tunnel-demo-1
  HostName 10.10.0.1
  User deploy
  Port 2222
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
```

## Managing the Tunnel

```bash
# Bring up the tunnel (required before SSH)
loft-cli tunnel up tunnel-demo-1

# Check tunnel status for all hosts
loft-cli tunnel status

# SSH through the tunnel
ssh tunnel-demo-1

# Tear down the tunnel
loft-cli tunnel down tunnel-demo-1
```

## Decommissioning

```bash
# Remove all local state (tunnel, WG keys, SSH config, inventory)
loft-cli remove tunnel-demo-1

# Skip confirmation prompt
loft-cli remove tunnel-demo-1 --force
```

## Usage

```bash
loft-cli validate examples/wireguard-tunnel-lifecycle/wireguard-tunnel-lifecycle.yaml
loft-cli plan examples/wireguard-tunnel-lifecycle/wireguard-tunnel-lifecycle.yaml
loft-cli apply examples/wireguard-tunnel-lifecycle/wireguard-tunnel-lifecycle.yaml
```

## Prerequisites

- A fresh server with root SSH access at 203.0.113.50
- `wg-quick` installed locally (part of `wireguard-tools`)
- `~/.ssh/id_ed25519.pub` exists locally
- Passwordless `sudo` for `wg`, `wg-quick`, and `ip` on the local machine (see below)

### Passwordless sudo for WireGuard

loft-cli runs `wg-quick` and `ip` via `sudo` to manage local tunnel interfaces.
Without passwordless sudo these commands hang on the password prompt and time out.

```bash
# /etc/sudoers.d/wireguard-loft-cli
%sudo ALL=(ALL) NOPASSWD: /usr/bin/wg, /usr/bin/wg-quick, /usr/sbin/ip
```

```bash
sudo visudo -f /etc/sudoers.d/wireguard-loft-cli
```

## Notes

- WireGuard server keys are auto-generated (no `private_key_file` needed)
- Client keys are also auto-generated and stored at `~/.wg/loft-cli/tunnel-demo-1/`
- The tunnel safety gate prevents SSH lockout: if the tunnel doesn't work, the open SSH rule stays
- `registered_peers_only: true` means SSH is restricted to peer IP `10.10.0.2` on `wg0`
