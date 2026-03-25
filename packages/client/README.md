# nodeforge (client)

> CLI tool that safely bootstraps Linux servers from YAML specs — compiling specs into reviewable plans, generating ops docs, and executing via the server-side agent.

`nodeforge` is the client package. It provides the `nodeforge` CLI command, the three-phase compiler pipeline, transport abstraction for remote execution, local state management, and self-update capabilities.

---

## Installation

```bash
pip install nodeforge
```

Or as part of the monorepo development setup:

```bash
pip install -e packages/core -e packages/client
```

---

## Dependencies

- `nodeforge-core>=0.5.0` -- shared models, specs, registries
- `typer[all]>=0.9.0` -- CLI framework with shell completion
- `fabric>=3.2` -- SSH transport (paramiko under the hood)
- `rich>=13.0` -- terminal formatting and progress
- `requests>=2.31` -- GitHub API calls (self-update, agent-update)
- `pynacl>=1.5` -- Curve25519 key derivation (WireGuard)

### Dev dependencies

`pytest`, `pytest-mock`, `pyfakefs`, `ruff`, `black`, `build`, `pyinstaller`

---

## Module Structure

```
nodeforge/
  __init__.py           Re-exports __version__ from nodeforge-core
  _builtins.py          Registers built-in spec kinds via entry_points
  agent_installer.py    Agent detection and installation on target servers
  cli.py                Typer CLI entry point — all user-facing commands
  updater.py            Self-update (client) and agent-update from GitHub Releases
  compiler/
    __init__.py
    normalizer.py       Phase 2: resolve paths, keys, secrets into NormalizedContext
    parser.py           Phase 1: YAML loading + spec hydration (delegates to core loader)
    planner.py          Phase 3: generate Plan (list of Steps) from spec + context
  runtime/
    __init__.py
    agent_transport.py  AgentTransport — upload plan, invoke agent, retrieve result
    executor.py         Executor — iterates Steps, dispatches via handler registry
    fabric_transport.py FabricTransport — direct SSH execution (legacy, deprecated)
    ssh.py              SSH session management helpers
    transport.py        Transport protocol — connect(), upload(), exec(), download()
    steps/
      __init__.py
      bootstrap.py      Step builders for bootstrap kind (user, SSH, firewall, etc.)
      compose.py        Step builders for compose_project kind
      container.py      Step builders for Docker container service
      docker.py         Step builders for Docker installation service
      file_template.py  Step builders for file_template kind
      nginx.py          Step builders for Nginx service
      postgres.py       Step builders for PostgreSQL service
      wireguard.py      Step builders for WireGuard VPN
      systemd.py        Step builders for systemd_unit and systemd_timer kinds
      backup.py         Step builders for backup_job kind (script generator)
      postgres_ensure.py Step builders for postgres_ensure kind (SQL generators)
  local/
    __init__.py
    ddl/                SQLite DDL scripts for inventory schema
    inventory.py        High-level inventory operations
    inventory_db.py     Low-level SQLite inventory access (with versionize historization)
    keys.py             SSH key generation (ed25519)
    remove.py           Host removal orchestration (tunnel + WG state + SSH config + inventory)
    ssh_config.py       ~/.ssh/conf.d/ fragment management (with tunnel_comment support)
    tunnel.py           WireGuard tunnel management — up, down, status via wg-quick
    wireguard_store.py  WireGuard key material storage (~/.wg/nodeforge/)
  checks/
    __init__.py
    compose.py          Docker Compose health check
    container.py        Docker container health check
    http.py             HTTP endpoint check
    nginx.py            Nginx service check
    ports.py            Port reachability check
    postgres.py         PostgreSQL connection check
    ssh.py              SSH connectivity check
    wireguard.py        WireGuard interface check
  logs/
    __init__.py
    reader.py           Read past run logs
    writer.py           Write JSON run logs to ~/.nodeforge/runs/
  addons/
    __init__.py
    goss/               Built-in addon: Goss server-state verification
```

---

## Compiler Pipeline

The compiler transforms YAML specs into executable Plans in three phases:

```
YAML file
  └─ Parse (parser.py)         Load YAML, resolve ${} tokens, hydrate Pydantic model
       └─ Normalize (normalizer.py)  Resolve paths, read keys, derive WireGuard pubkeys
            └─ Plan (planner.py)     Generate ordered list of Steps with dependencies
```

Each phase dispatches by `kind` through the registry system. The output is a `Plan` object — an immutable data structure that drives docs, diff, and apply.

---

## Transport Protocol

The `Transport` protocol (`transport.py`) decouples the executor from any specific SSH library:

```python
class Transport(Protocol):
    def connect(self) -> None: ...
    def upload(self, local_path: str, remote_path: str) -> None: ...
    def exec(self, command: str) -> ExecResult: ...
    def download(self, remote_path: str, local_path: str) -> None: ...
    def close(self) -> None: ...
```

Two implementations:

| Transport | Description | Status |
|---|---|---|
| `AgentTransport` | Uploads plan + agent binary, invokes `nodeforge-agent apply`, retrieves result | **Primary** (default) |
| `FabricTransport` | Executes each step via individual SSH commands | **Legacy** (deprecated) |

Mode selection: `--mode auto` (default) tries agent first, falls back to client. `--mode agent` forces agent. `--mode client` forces Fabric.

---

## CLI Commands

| Command | Description |
|---|---|
| `validate <spec>` | Parse and validate a spec file |
| `plan <spec>` | Show the execution plan |
| `docs <spec>` | Generate Markdown ops guide |
| `diff <spec>` | Show what would change on the server |
| `apply <spec>` | Execute the plan (supports `--dry-run`, `--mode`) |
| `doctor <spec>` | Detect drift between desired and actual state |
| `reconcile <spec>` | Re-apply only drifted resources |
| `tunnel up <host>` | Bring up a WireGuard tunnel for a host |
| `tunnel down <host>` | Tear down a WireGuard tunnel for a host |
| `tunnel status` | List all hosts with WireGuard tunnel status |
| `remove <host>` | Remove all local state for a decommissioned host |
| `version` | Print client version (add `--host` for agent version) |
| `update` | Self-update client from GitHub Releases |
| `agent-update <host>` | Update agent binary on a remote host |
| `inspect run <id>` | Inspect a past execution run |
| `inventory list` | List all servers in local inventory |
| `inventory show <id>` | Show server details |
| `rotate-secret <spec>` | Rotate a secret (password_env) and re-apply |

---

## Self-Update and Agent Update

`updater.py` handles binary updates:

- **`nodeforge update`** — downloads the latest client binary from GitHub Releases (matches platform suffix), replaces the running binary
- **`nodeforge agent-update <host>`** — downloads the latest agent binary, uploads it to the remote server, replaces the running agent

The updater looks for assets matching patterns like `nodeforge-linux-amd64` (client) and `agent-linux-amd64` (agent) in the latest GitHub Release.

---

## WireGuard Tunnel Lifecycle (v0.6.3)

When `wireguard.enabled: true`, the bootstrap planner inserts a **tunnel safety gate** between `allow_ssh_on_wireguard` and `delete_open_ssh_rule`:

1. `allow_ssh_on_wireguard` — adds UFW rule allowing SSH on WireGuard interface
2. `verify_ssh_over_wireguard_tunnel` — **GATE**: brings up the local WireGuard tunnel, verifies SSH through the VPN IP, tears down the tunnel
3. `delete_open_ssh_rule` — removes the open-to-all SSH rule (only if gate passed)

If the gate fails, the open SSH rule is **not** deleted — the server remains accessible via its public IP.

### SSH Config Integration

When WireGuard is enabled, the SSH config fragment uses the server's **VPN IP** as `HostName` instead of the public address. A comment is added noting the tunnel dependency:

```
# nodeforge managed: myhost
# Requires: nodeforge tunnel up myhost
Host myhost
  HostName 10.10.0.1
  User deploy
  Port 2222
```

### Tunnel Management (`tunnel.py`)

`nodeforge tunnel` subcommands manage client-side WireGuard tunnels via `wg-quick`:

- **`tunnel up <host>`** — creates a temporary config from `~/.wg/nodeforge/{host}/client.conf`, invokes `sudo wg-quick up`
- **`tunnel down <host>`** — recreates the temporary config and invokes `sudo wg-quick down`; falls back to `sudo ip link del` if the config is missing or `wg-quick` fails
- **`tunnel status`** — scans `~/.wg/nodeforge/*/metadata.json`, cross-references with `wg show interfaces`

Interface names use `wg-{host}` (truncated to 15 chars — Linux interface name limit).

#### Client-Side Prerequisites

WireGuard tunnel commands (`tunnel up`, `tunnel down`, and the tunnel safety gate during `apply`) require:

1. **`wireguard-tools`** installed on the local machine (provides `wg` and `wg-quick`)
2. **Passwordless `sudo`** for `wg`, `wg-quick`, and `ip` — these commands manage network interfaces and require root privileges. Without passwordless sudo, `wg-quick` will hang waiting for a password prompt and time out after 30 seconds.

To grant passwordless sudo for WireGuard commands only:

```bash
# /etc/sudoers.d/wireguard-nodeforge
%sudo ALL=(ALL) NOPASSWD: /usr/bin/wg, /usr/bin/wg-quick, /usr/sbin/ip
```

```bash
sudo visudo -f /etc/sudoers.d/wireguard-nodeforge
```

### Host Removal (`remove.py`)

`nodeforge remove <host>` tears down all local state in four steps:

1. Tear down active WireGuard tunnel (if running)
2. Remove WireGuard local state (`~/.wg/nodeforge/{host}/`)
3. Remove SSH conf.d entry (`~/.ssh/conf.d/nodeforge/{host}.conf`)
4. Mark inventory record as decommissioned

---

## Built-in Addon Registration

`_builtins.py` registers all built-in spec kinds (bootstrap, service, file_template, compose_project, stack, http_check, systemd_unit, systemd_timer, backup_job, postgres_ensure) via the `nodeforge.addons` entry_points group. This happens automatically when the package is imported — no explicit registration calls needed from user code.

---

## Import Boundary

`nodeforge` (client) may import from:
- `nodeforge_core` (shared models, specs, registries)
- Standard library
- Third-party dependencies (fabric, requests, pynacl, etc.)

`nodeforge` must **never** import from `nodeforge_agent`. The client and agent are independent consumers of core.

---

## Binary Build

The client binary is built with PyInstaller:

```bash
make build-binary
# or: python scripts/build_binary.py
```

The client binary includes Fabric, paramiko, sqlcipher3, and all core + client code. It requires `libsqlcipher-dev` (Linux) or `brew install sqlcipher` (macOS) on the build host.

Output: `dist/nodeforge`
