# Example 1.5b: WireGuard — Auto-Generated Server Key

This example demonstrates WireGuard setup without a manually-created `private_key_file`.

## What it does

- Configures the remote server as a WireGuard VPN hub (same as `05-wireguard`)
- **Server key pair is auto-generated** by nodeforge via PyNaCl on first apply
- No `wg genkey` subprocess needed — fully cross-platform
- Key is persisted locally with write-once semantics: `~/.wg/nodeforge/{host}/private.key`
- Re-runs reuse the same server key (stable server identity)

## Difference from `05-wireguard`

| | `05-wireguard` | `05b-wireguard-auto-key` |
|---|---|---|
| `private_key_file` | Required | Omitted |
| Key generation | Manual (`wg genkey`) | Auto (PyNaCl, first apply) |
| Key storage | Your `.secrets/` dir | `~/.wg/nodeforge/{host}/private.key` |

## Usage

```bash
nodeforge validate 05b-wireguard-auto-key.yaml
nodeforge plan    05b-wireguard-auto-key.yaml
nodeforge apply   05b-wireguard-auto-key.yaml
```

After apply, the full WireGuard state is available under:

```
~/.wg/nodeforge/ubuntu-node-1/
  private.key   — server private key (write-once)
  public.key    — server public key
  wg0.conf      — server wg-quick config
  client.key    — client private key (write-once)
  client.conf   — client wg-quick config (use with: wg-quick up client.conf)
  metadata.json — interface/peer summary
```
