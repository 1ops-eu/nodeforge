# nodeforge Roadmap

This document tracks the planned evolution of `nodeforge` from its current v0.2 baseline through a production-ready v1.0 release.

The roadmap is organized around milestones. Each milestone corresponds to a meaningful capability jump. Future infrastructure and design decisions are captured in the RFC series below.

**Architectural pivot (v0.3):** Starting with v0.3, nodeforge transitions from a client-driven remote orchestrator to a **server-local agent model**. The `nodeforge-agent` binary is installed as the first step of every bootstrap. The client becomes a thin transporter; the agent is the operator.

---

## Vision

Nodeforge is a **self-hosted infrastructure compiler** that turns human-readable YAML specs into **reviewable plans** and **deterministic execution**.

The product evolves in four deliberate stages:

1. **Bootstrap and validate** -- reliably harden fresh Linux servers *(done)*
2. **Agent pivot** -- move provisioning logic onto the target server *(v0.3)*
3. **Deploy and operate** -- manage real multi-service stacks on single hosts *(v0.4--v0.6)*
4. **Compose and scale** -- reusable blueprints and light multi-host operations *(v0.7--v0.8)*

---

## Current State -- v0.2 (baseline)

| Area | Status |
|---|---|
| `pip install` distribution | Done |
| Bootstrap spec (harden fresh Debian/Ubuntu) | Done |
| Service specs (PostgreSQL, Docker, containers, Nginx) | Done |
| Local inventory (SQLite) | Done |
| SSH lockout prevention gate | Done |
| Goss server verification | Done |
| Run logs | Done |
| Standalone binary builds (Linux amd64/arm64, macOS amd64/arm64) | Done |
| Docker image | Done |
| GitHub Actions release pipeline | Done |
| Smoke test suite (45 tests across 15 example specs) | Done |
| `ruff` + `black` CI enforcement | Done |
| PyPI publish workflow | Done |
| Pydantic `extra='forbid'` on all spec models | Done |

---

## v0.2 -- Hardening + CI Validation ✅

**Goal:** Make the existing tool stable enough to serve as the foundation for the next architectural steps.

| Item | Description | Status |
|---|---|---|
| Smoke test suite | Parametrized pytest suite (`tests/test_smoke/`) validates `validate`, `plan`, `docs` for all 15 example specs (45 tests) | Done |
| Linux ARM64 binary | `ubuntu-24.04-arm` runner in `release.yml` matrix | Done |
| macOS Intel + Apple Silicon split | Separate matrix entries for `macos-13` (Intel/amd64) and `macos-latest` (ARM/arm64) | Done |
| PyPI publish | `pypi.yml` workflow publishes the wheel on tag push | Done |
| `ruff` + `black` CI enforcement | `lint.yml` workflow runs on every push/PR to `main` and `feature/**` | Done |
| CI test workflow | `ci.yml` runs full pytest suite on Python 3.11 + 3.12 | Done |
| Pydantic strict mode | `extra='forbid'` on all spec models — catches typos and removed fields | Done |
| Nginx service kind | Native nginx support under `kind: service` (install, site config, checks) | Done |

**Beyond original scope:** v0.2 also delivered Pydantic strict mode enforcement across all spec models (which caught multiple schema drift issues in existing examples) and a full nginx service kind with schema, validation, planning, execution steps, health checks, inventory recording, 28 unit tests, and 2 example specs.

**Acceptance criteria:**
- All example specs validate and generate docs in CI -- **met** (45 smoke tests pass)
- Release assets are reliably produced for all target platforms -- **met** (4 binaries: linux-amd64, linux-arm64, macos-amd64, macos-arm64)
- PyPI release on tag -- **met** (`pypi.yml` workflow)

---

## v0.3 -- Agent Pivot + Compose Stacks

**Goal:** Introduce the server-local agent model and deliver Docker Compose stack management as the first agent-native workload.

This is the **architectural pivot release**. The `nodeforge-agent` binary becomes the operator on every managed server. The client CLI becomes a thin transporter.

### Agent Architecture

| Item | Description |
|---|---|
| `nodeforge-agent` binary | Separate binary installed on the target server as the first step of bootstrap |
| Agent-first bootstrap | Client connects via SSH, uploads agent + desired state, invokes `nodeforge-agent bootstrap`, disconnects. Agent operates locally. |
| Transport abstraction | Fabric wrapped behind `Transport` protocol: `connect()`, `upload()`, `exec()`, `download()` |
| Server-side state | `/etc/nodeforge/` (config), `/var/lib/nodeforge/` (runtime state, locks, secrets), `/var/log/nodeforge/` (logs) |
| Local secret generation | Agent generates `.env` values and service secrets on the target server |
| Runtime state tracking | `runtime-state.json` records applied state (hashes, timestamps, versions) |
| Mutation locking | Lock file in `/var/lib/nodeforge/locks/` — one mutation at a time |

### Compose Stacks (first agent-native workload)

| Item | Description |
|---|---|
| `kind: file_template` | Render managed configuration files from Jinja2 templates and variables |
| `kind: compose_project` | Manage Docker Compose projects: upload compose file, pull, up, health check |
| Managed directories | Deterministic creation of project directories on the target server |
| Compose health checks | Wait for container health after `docker compose up -d`; surface failures |

**New capabilities:**
- Agent-local execution — SSH restart during bootstrap is a non-event
- Rendered `.env` files, `docker-compose.yml` files, and arbitrary config from Jinja2 templates
- Change detection for rendered files (hash-based)
- Docker Compose validation (`docker compose config`) before apply
- Health-aware startup with configurable timeout and retry
- Secrets generated and stored on the target server, never round-tripped through the client

**Acceptance criteria:**
- Bootstrap installs agent as first step; all subsequent operations run locally on the server
- A fresh bootstrapped VPS can run a multi-container Compose stack using only nodeforge-managed specs
- Template rendering is deterministic and reviewable in the plan
- Health check failures are surfaced clearly in apply output
- Client CLI works as a thin transporter (upload, invoke, retrieve status)

---

## v0.4 -- Logic Migration + UX ✅

**Goal:** Complete the migration of all spec kinds to agent-side execution, and improve daily-use ergonomics.

### Logic Migration

| Item | Description | Status |
|---|---|---|
| All spec kinds via agent | Bootstrap, service (PostgreSQL, Nginx, Docker, containers), file_template, compose_project — all execute through the agent | Done |
| Server-side plan/apply | Plan generation and apply run on the agent, not the client | Done |
| Idempotent re-apply | Agent skips unchanged resources on re-apply (hash-based content comparison) | Done |
| Deprecate old Fabric path | Mark the direct-Fabric execution path as deprecated (`DeprecationWarning` on `ssh_session=`) | Done |

### UX Improvements

| Item | Description | Status |
|---|---|---|
| `nodeforge version` | Print current version (client + agent via `--host`) | Done |
| `nodeforge update` | Self-update client from GitHub Releases; `nodeforge agent-update <host>` for the agent | Done |
| Shell completion | Enable `typer` completion (`add_completion=True`) | Done |
| Spec dry-run diff | `nodeforge diff` shows exactly what would change on the server before applying | Done |
| Multiple YAML documents | `yaml.safe_load_all()` with `---` separator support; backward-compatible | Done |

**New capabilities:**
- Transport protocol abstraction (`Transport` protocol decouples executor from Fabric)
- Agent executor with subprocess-based local execution
- Mutation locking via `fcntl.flock` (one apply at a time)
- Runtime state tracking with atomic save (`runtime-state.json`)
- Agent binary entry point (`nodeforge-agent apply|status|version`)
- Agent detection and auto/manual mode selection (`--mode auto|agent|client`)
- Dry-run diff with added/changed/unchanged/always-run classification
- Multi-document YAML with per-document error reporting

**Acceptance criteria:**
- All existing spec kinds execute through the agent — no direct Fabric orchestration for provisioning steps -- **met**
- `nodeforge apply` is idempotent — re-running produces no changes if state matches -- **met**
- Plans are reviewable and stable -- **met**
- Operators can inspect intended changes before execution (`nodeforge diff`) -- **met**

---

## v0.5 -- Declarative Reconciliation + Policy Engine + Package Split

**Goal:** Make the agent truly declarative (desired state vs. actual state), ship the policy engine in OSS core, and split the codebase into three clean packages.

### Reconciliation

| Item | Description |
|---|---|
| Desired vs. runtime state comparison | Agent compares `desired-state.yaml` against `runtime-state.json` |
| Partial apply | Only changed resources are applied — unchanged resources are skipped |
| Drift detection | `nodeforge doctor <host>` reports divergence between desired and actual state |
| `nodeforge reconcile <host>` | Bring server back to desired state |

### Policy Engine (OSS Core)

| Item | Description |
|---|---|
| Policy engine | Enforce `policy.yaml` rules: auto_apply, require_approval, deny |
| Policy inert by default | No `policy.yaml` = no policy checks = agent executes what it's told |
| Manual policy option | OSS users can optionally write their own `policy.yaml` to constrain the agent |
| Temporary approvals | One-off critical operations with auto-expiring approval tokens |

### Stack Foundations

| Item | Description |
|---|---|
| Addon registry | Formalize external addon discovery and lifecycle |
| Addon discovery | External addons register via `[project.entry-points."nodeforge.addons"]` |
| `kind: stack` | Group related resources into a single deployable application boundary |
| Apply ordering | Stack-aware dependency-ordered execution |
| Overlay / env-file layering | Multiple `.env` file layers with explicit precedence order (RFC 008) |

### Package Split (Monorepo)

| Item | Description |
|---|---|
| `nodeforge-core` package | `plan/`, `specs/`, `registry/` (infrastructure), `utils/` — shared by client and agent |
| `nodeforge` package | Client: `compiler/`, `runtime/`, `local/`, `logs/`, `checks/`, `addons/`, `cli.py` |
| `nodeforge-agent` package | Agent: `executor.py`, `state.py`, `lock.py`, `paths.py`, `cli.py`, `installer.py` |
| Import boundaries enforced | Agent may not import from client; client may not import from agent |
| Monorepo layout | All three packages under `packages/` in the same git repo |

**Acceptance criteria:**
- `nodeforge apply` is safe to re-run at any time — only applies what changed
- `nodeforge doctor` reports drift accurately
- Policy engine is testable, auditable, and inert by default
- Stacks group resources with dependency-ordered execution
- `pip install nodeforge-core` / `nodeforge` / `nodeforge-agent` each work independently
- Agent binary only includes agent + core code, not compiler/runtime/Fabric

---

## v0.6 -- Operational Primitives + Day-2 Operations

**Goal:** Make single-host stacks operationally safe and support post-bootstrap lifecycle management.

### Operational Primitives

| Item | Description |
|---|---|
| `kind: systemd_unit` | Deploy and manage host-native systemd services |
| `kind: systemd_timer` | Deploy scheduled execution via systemd timers |
| `kind: backup_job` | Define host-local backup operations with retention semantics |
| Log rotation | Support log rotation policies |
| Resource policies | Encourage CPU/RAM limits, restart policies, volume mounts |

### Day-2 Operations

| Item | Description |
|---|---|
| `nodeforge rotate-secret <host> <name>` | Rotate a managed secret, re-render dependent config, restart dependent services |
| Feature toggles | Enable/disable modules through desired state changes |
| Config updates | Update domains, proxy rules, integration tokens without full re-provision |

**New capabilities:**
- Timer-based recurring operations (reconcile, cleanup, scheduled jobs)
- PostgreSQL dump backups with timestamped naming and retention
- systemd daemon-reload, enable, start lifecycle
- Secret rotation as a first-class operation

**Acceptance criteria:**
- Timers can trigger local jobs or HTTP hooks
- Backup jobs can be installed and run predictably
- Rerun is idempotent — unchanged units are not recreated
- Secret rotation works end-to-end: generate → store → re-render → restart → verify

---

## v0.7 -- Light Blueprints

**Goal:** Introduce reusable composition primitives for common stack patterns.

| Item | Description |
|---|---|
| `kind: blueprint` | Package a reusable set of resources, defaults, and variables |
| Include semantics | Local and repo-relative includes |
| Parameterization | Required and optional inputs with defaults |
| Official building blocks | First reusable stack fragments |

**Candidate blueprints:**
- `secure-docker-host`
- `reverse-proxy-caddy`
- `postgres-backup-pack`
- `systemd-timer-pack`

**Design principles:**
- Blueprints expand into normal resources during planning
- Operators still see the final concrete plan (no opaque magic bundles)
- Circular includes are rejected at validation time

**Acceptance criteria:**
- Nodeforge can define and expand blueprints
- Expanded plans remain explicit and reviewable
- Official stack fragments can be published and reused

---

## v0.8 -- Companion App + Multi-Host Light Operations

**Goal:** Ship the optional companion app and support practical small-fleet workflows.

### Companion App (OSS)

| Item | Description |
|---|---|
| Companion binary | Optional install for users who prefer a visual workflow over CLI |
| Localhost HTTP listener | Companion listens on `localhost:19532` for requests |
| Credential prompt UI | Focused dialog for entering credentials during bootstrap |
| WireGuard detection | Detect WireGuard installation, prompt to install if missing, manage config |
| Cross-platform auto-start | `systemd --user` (Linux), LaunchAgent (macOS) |
| Credential store interface | Pluggable `CredentialStore` protocol with built-in transient + `.env` backends |

### Multi-Host Light Operations

| Item | Description |
|---|---|
| Multi-host inventory | Target multiple hosts via explicit list, tags, or role labels |
| Selectors | `role=worker`, `env=staging`, `stack=automation` |
| Sequential apply | Apply across selected hosts in order |
| Aggregated doctor/drift | Per-host validation with aggregated summary |
| Failure handling | Stop on first failure or continue through all hosts |

**Acceptance criteria:**
- Companion app works on Linux and macOS as an optional alternative to CLI
- A small fleet can be managed using one logical deployment command
- Results are aggregated and attributable per host
- Doctor/drift summaries available at fleet level

---

## v1.0 -- Production-Ready Release

**Goal:** Make nodeforge stable enough for unattended production use by independent operators.

| Item | Description |
|---|---|
| Stable spec schema | Commit to backwards-compatible format; document breaking change policy |
| Full test coverage | Unit + integration coverage for all compiler, plan, agent, and runtime paths |
| Signed release artifacts | GPG-sign binaries; publish `.sig` files (RFC 003) |
| SHA-256 checksums | `checksums.txt` with every release |
| OS keychain credential store | macOS Keychain, GNOME Keyring, Windows Credential Manager integration |
| CONTRIBUTING.md | Contributor guide, PR process, local dev setup |
| CHANGELOG.md | Automated changelog from conventional commits |
| Docs site | Generated from README + per-spec reference docs |

**Acceptance criteria:**
- A second operator can reproduce a full stack deployment from docs + repo
- Upgrades and re-applies are reliable and idempotent
- All release artifacts are signed and verifiable
- Agent and client version compatibility is enforced

---

## RFC Series

| RFC | Title | Status | Target |
|---|---|---|---|
| RFC 001 | Distribution and Release Strategy | Adopted | v0.1 |
| RFC 002 | Concrete Implementation Blueprint | Adopted | v0.1 |
| RFC 003 | Release Signing and Artifact Integrity | Planned | v1.0 |
| RFC 006 | Cross-Platform Smoke Testing and QA Gates | Adopted | v0.2 |
| RFC 007 | Single-Host Stack Runtime Model | Planned | v0.3--v0.6 |
| RFC 008 | Overlay / Env-File Layering for Value Resolution | Planned | v0.5 |
| RFC 012 | Light Blueprints and Stack Composition | Planned | v0.7 |
| RFC 013 | Multi-Host Light Operations | Planned | v0.8 |
| RFC 014 | Agent Architecture and Bootstrap Sequence | **New** | v0.3 |
| RFC 015 | Policy Engine Design | **New** | v0.5 |
| RFC 016 | Companion App and Credential Store | **New** | v0.8 |

---

## Platform Scope

### Client (CLI + optional companion)

nodeforge client runs on **Linux, macOS, and Windows**.

- Linux and macOS: full support (CLI + companion)
- Windows: companion support targeted for v1.0+; CLI works where Python is available

### Agent (target server)

The target of every spec is always a **remote Linux server (Debian/Ubuntu)**. The `nodeforge-agent` binary runs on the target server and performs all provisioning locally.

---

## Guiding Principles

> **Plan is the single source of truth** -- what you review is exactly what executes.

> **Client is the transporter, agent is the operator** -- agent installed as first step.

> **Ship a real self-hosted stack first** -- prove the model on a single host before generalizing.

> **Composable specs that scale** -- from one VPS to a small fleet.

> **No vendor lock-in** -- self-hosted by default, no mandatory external services.

> **Policy engine is open source** -- auditable by anyone, activated by configuration.

> **Operational safety over hidden magic** -- health checks, resource limits, and explicit failure handling.
