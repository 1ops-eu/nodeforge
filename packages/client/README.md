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
    ssh_config.py       ~/.ssh/conf.d/ fragment management
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
