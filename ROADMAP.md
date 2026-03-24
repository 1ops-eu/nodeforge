# nodeforge Roadmap

This document tracks the planned evolution of `nodeforge` from its current v0.2 baseline through a production-ready v1.0 release.

The roadmap is organized around milestones. Each milestone corresponds to a meaningful capability jump. Future infrastructure and design decisions are captured in the RFC series below.

**Architectural pivot (v0.3):** Starting with v0.3, nodeforge transitions from a client-driven remote orchestrator to a **server-local agent model**. The `nodeforge-agent` binary is installed as the first step of every bootstrap. The client becomes a thin transporter; the agent is the operator.

---

## Product Identity

**nodeforge** is a product by [1ops](https://1ops.eu). It is a **self-hosted infrastructure compiler** — an open-source tool that turns human-readable YAML specs into reviewable plans and deterministic execution on Linux servers.

**nodeforge is Layer 1.** It makes VMs ready and usable: bootstrap, harden, install services, deploy containers, manage configuration, verify state. Once nodeforge is done, the server is a functioning platform.

**nodeforge does not do Layer 2.** Application-level orchestration — configuring SaaS applications, importing workflows, seeding databases with business logic, wiring services together via API calls — belongs in a separate orchestration layer (e.g. n8n). The boundary: if the outcome depends only on OS/infrastructure state, it's nodeforge; if it depends on application runtime state, it's not.

### The Three Binaries

| Binary | Purpose | Runs on |
|---|---|---|
| `nodeforge` | Client CLI — validate, plan, docs, diff, apply, doctor, reconcile | Operator's machine (Linux, macOS, Windows) |
| `nodeforge-agent` | Server-side executor — receives plans, applies locally, tracks state | Target server (Linux only) |
| `nodeforge-agent` (companion mode, v0.8+) | Optional visual workflow as alternative to CLI | Operator's machine |

The client is the **transporter** — it parses specs, generates plans, and delivers them to the agent. The agent is the **operator** — it executes plans locally, tracks runtime state, enforces policy, and supports extensible job types.

### Agent Job Types

The nodeforge-agent executes **jobs**. Each job type is a distinct unit of work:

| Job type | Description | Available since |
|---|---|---|
| `apply` | Apply an infrastructure plan (the core nodeforge workflow) | v0.3 |
| `doctor` | Compare desired state against actual state | v0.5 |
| `reconcile` | Re-apply drifted resources | v0.5 |

The agent's job type system is **extensible via addons**. External packages (including commercial variants) can register additional job types through the `nodeforge.addons` entry_points mechanism. The agent provides the trusted execution surface — discovery of running services, Docker management, SQL execution against local databases, HTTP health checks — and addons define new job types that leverage these primitives.

This design means the agent is a **general-purpose on-machine operations agent**, not limited to infrastructure provisioning. However, the OSS agent ships only with infrastructure job types. The agent's built-in primitives (service discovery, Docker management, database connectivity, HTTP checks) are available to any addon, enabling higher-level workflows without rebuilding low-level capabilities.

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

## v0.5 -- Declarative Reconciliation + Policy Engine + Package Split ✅

**Goal:** Make the agent truly declarative (desired state vs. actual state), ship the policy engine in OSS core, and split the codebase into three clean packages.

### Reconciliation

| Item | Description | Status |
|---|---|---|
| Desired vs. runtime state comparison | Agent compares `desired-state.json` against `runtime-state.json` | Done |
| Partial apply | Only changed resources are applied — unchanged resources are skipped (hash-based) | Done |
| Drift detection | `nodeforge doctor <spec>` reports divergence between desired and actual state | Done |
| `nodeforge reconcile <spec>` | Bring server back to desired state by re-applying drifted resources | Done |
| Desired state storage | Agent persists last-applied plan to `/var/lib/nodeforge/desired/desired-state.json` | Done |

### Policy Engine (OSS Core)

| Item | Description | Status |
|---|---|---|
| Policy engine | Enforce `policy.yaml` rules: auto_apply, require_approval, deny | Done |
| Policy inert by default | No `policy.yaml` = no policy checks = agent executes what it's told | Done |
| Manual policy option | OSS users can optionally write their own `policy.yaml` to constrain the agent | Done |
| Temporary approvals | HMAC-SHA256 time-limited approval tokens for `require_approval` steps | Done |
| Policy integration in agent | Agent executor loads policy and evaluates each step before execution | Done |

### Stack Foundations

| Item | Description | Status |
|---|---|---|
| Addon registry | 7 open registries + `load_addons()` via entry_points | Done |
| Addon discovery | External addons register via `[project.entry-points."nodeforge.addons"]` | Done |
| `kind: stack` | Group related resources into a single deployable application boundary | Done |
| Apply ordering | Stack-aware dependency-ordered execution via topological sort | Done |
| Overlay / env-file layering | Multiple `--env-file` flags with explicit precedence order (RFC 008) | Done |

### Package Split (Monorepo)

| Item | Description | Status |
|---|---|---|
| `nodeforge-core` package | `plan/`, `specs/`, `registry/` (infrastructure), `utils/` — shared by client and agent | Done |
| `nodeforge` package | Client: `compiler/`, `runtime/`, `local/`, `logs/`, `checks/`, `addons/`, `cli.py` | Done |
| `nodeforge-agent` package | Agent: `executor.py`, `state.py`, `lock.py`, `paths.py`, `cli.py` | Done |
| Import boundaries enforced | Agent may not import from client; client may not import from agent | Done |
| Monorepo layout | All three packages under `packages/` in the same git repo | Done |

### Agent Binary Pipeline

| Item | Description | Status |
|---|---|---|
| Agent binary build script | `scripts/build_agent_binary.py` — PyInstaller build with only core + agent deps (no Fabric/sqlcipher/paramiko) | Done |
| Agent PyInstaller entrypoint | `scripts/agent_entrypoint.py` — delegates to `nodeforge_agent.cli:app` | Done |
| Release workflow: agent jobs | `release.yml` split into `build-client` and `build-agent` jobs; agent builds `nodeforge-agent-linux-{amd64,arm64}` | Done |
| Makefile target | `make build-agent-binary` for local agent binary builds | Done |
| Updater compatibility | `updater.py` `update_agent()` already expects `agent-{suffix}` assets in GitHub Releases — now produced by the pipeline | Done |

**New capabilities:**
- Doctor command (`nodeforge doctor`) compares desired plan against runtime state, writes doctor-result.json
- Reconcile command (`nodeforge reconcile`) re-applies only drifted resources
- Policy engine with per-step evaluation, fnmatch-based rule matching, AND logic for multi-condition rules
- HMAC-SHA256 approval tokens with configurable TTL for `require_approval` steps
- `kind: stack` schema with resources, dependency ordering, and circular dependency detection at validation time
- Stack planner with topological sort and step ID prefixing for traceability
- Repeatable `--env-file` CLI option for overlay layering; `env_files` parameter in loader
- Stack inventory recording (`record_stack_apply`) tracks each resource as a stack_resource entry
- Agent binary pipeline — `nodeforge-agent` standalone binaries (Linux amd64/arm64) built and published alongside client binaries in GitHub Releases
- Agent binary is minimal: only `nodeforge-core` + `nodeforge-agent` deps (no Fabric, sqlcipher, paramiko)

**Acceptance criteria:**
- `nodeforge apply` is safe to re-run at any time — only applies what changed -- **met** (hash-based idempotent skip)
- `nodeforge doctor` reports drift accurately -- **met** (compares desired plan hashes against runtime state)
- Policy engine is testable, auditable, and inert by default -- **met** (22 tests, no policy = no checks)
- Stacks group resources with dependency-ordered execution -- **met** (topological sort, circular dep detection)
- `pip install nodeforge-core` / `nodeforge` / `nodeforge-agent` each work independently -- **met** (three pyproject.toml, editable installs)
- Agent binary only includes agent + core code, not compiler/runtime/Fabric -- **met** (import boundaries enforced)
- Agent binary assets (`agent-linux-amd64`, `agent-linux-arm64`) produced in release pipeline -- **met** (`build-agent` job in `release.yml`)

---

## v0.6 -- Operational Primitives + Day-2 Operations

**Goal:** Make single-host stacks operationally safe, support post-bootstrap lifecycle management, and formalize the agent's service primitives so addons can build on them.

**Design principle:** nodeforge manages infrastructure resources — deterministic, auditable, and reviewable in the plan. Application-level orchestration (API calls with response chaining, workflow imports, data seeding) belongs in the orchestration layer (e.g. n8n). The boundary: if the outcome depends only on OS/infrastructure state, it's nodeforge; if it depends on application runtime state, it's not.

### Operational Primitives

| Item | Description |
|---|---|
| `kind: systemd_unit` | Deploy and manage host-native systemd services | Done |
| `kind: systemd_timer` | Deploy scheduled execution via systemd timers | Done |
| `kind: backup_job` | Define host-local backup operations with retention semantics | Done |
| Log rotation | Optional logrotate field on systemd_unit | Done |
| Resource policies | Encourage CPU/RAM limits, restart policies, volume mounts |

### Infrastructure Readiness

| Item | Description |
|---|---|
| `kind: http_check` | GET-only HTTP readiness probe with configurable retry, backoff, and timeout. Usable as a dependency gate in stacks. | Done |
| `kind: postgres_ensure` | Ensure PostgreSQL resources exist (users, databases, extensions, grants) on running instances. Structured declarations, no arbitrary SQL. | Done |

### Agent Service Primitives

The agent gains formalized **service primitives** — low-level capabilities for interacting with running services on the target machine. These primitives are used by built-in spec kinds (e.g. `postgres_ensure` uses the Postgres primitive) and are also available to external addons via the registry.

| Primitive | Capability | Used by |
|---|---|---|
| **Service discovery** | Enumerate running services: Docker containers (`docker ps`), host services (`systemctl`), listening ports. Produces a machine state snapshot. | `kind: stack` (dependency validation), addons |
| **Postgres executor** | Run structured SQL against a target PostgreSQL instance (host-installed or Docker container). Handles instance resolution when multiple Postgres instances exist. | `kind: postgres_ensure`, addons |
| **HTTP checker** | Make GET requests with retry, backoff, and timeout against local or container-exposed endpoints. | `kind: http_check`, addons |
| **Docker manager** | Container lifecycle (inspect, run, stop, rm), image pull, network and volume operations. Already exists in `runtime/steps/container.py` — formalized as a reusable primitive. | `kind: service` (containers), `kind: compose_project`, addons |

These primitives are **general-purpose building blocks**. In the OSS agent, they power built-in spec kinds. The addon system exposes them so external packages can define higher-level job types that leverage service discovery, database connectivity, and container management without reimplementing them.

### Day-2 Operations

| Item | Description |
|---|---|
| `nodeforge rotate-secret <spec> --secret <name>` | Rotate a managed secret (password_env), re-normalize, re-apply | Done |

**New capabilities:**
- Timer-based recurring operations (reconcile, cleanup, scheduled jobs)
- PostgreSQL dump backups with timestamped naming and retention
- systemd daemon-reload, enable, start lifecycle
- Secret rotation as a first-class operation
- GET-only HTTP readiness gates for stack dependency ordering
- Declarative PostgreSQL resource ensuring (users, databases, extensions) against running containers
- Formalized service primitives (service discovery, Postgres executor, HTTP checker, Docker manager) available to addons

**Acceptance criteria:**
- Timers can trigger local jobs
- Backup jobs can be installed and run predictably
- Rerun is idempotent — unchanged units are not recreated
- Secret rotation works end-to-end: generate → store → re-render → restart → verify
- `kind: http_check` can gate stack progression on a GET returning 200
- `kind: postgres_ensure` can ensure users, databases, and extensions exist idempotently on a running Postgres container — every action reviewable in the plan
- Service primitives are accessible via the addon registry and documented for external use

---

## v0.6.1 -- WireGuard Server Key Auto-Generation

**Goal:** Eliminate the manual `wg genkey` step by auto-generating the server private key when `private_key_file` is omitted.

| Item | Description |
|---|---|
| Auto-generate server keypair | When `wireguard.enabled: true` and `private_key_file` is omitted, generate the server Curve25519 private key via PyNaCl (same as client key) — no subprocess, fully cross-platform |
| Write-once server key | Auto-generated `private.key` in local state uses write-once semantics (same as `client.key`) — prevents accidental key rotation on re-runs |
| Validator update | `private_key_file` is no longer required when `wireguard.enabled: true`; omitting it triggers auto-generation |
| Backward compatible | Existing specs with explicit `private_key_file` behave identically to before |

**New capabilities:**
- Zero-step WireGuard setup: `wireguard.enabled: true` is all that's needed — both server and client keypairs are auto-managed
- Fully cross-platform key generation via PyNaCl (no `wg genkey` subprocess required)
- Stable server identity across re-runs via write-once local state

**Acceptance criteria:**
- `nodeforge apply` with `wireguard.enabled: true` and no `private_key_file` auto-generates the server key, deploys WireGuard, and produces a working `client.conf`
- Re-running reuses the same server key from local state
- Existing specs with explicit `private_key_file` are unaffected
- Works on Linux, macOS, and Windows (PyNaCl only, no shell subprocess)

---

## v0.6.2 -- Ubuntu 24.04 SSH Socket Activation Fix + Version Housekeeping

**Goal:** Fix bootstrap SSH port change on Ubuntu 24.04+ which uses systemd socket-activated sshd, and correct version reporting across all packages.

| Item | Description |
|---|---|
| Socket-aware `reload_sshd()` | Detect `ssh.socket` at runtime; use `systemctl daemon-reload && systemctl restart ssh.socket` on socket-activated systems (Ubuntu 24.04+) instead of `systemctl reload ssh`. Falls back to traditional reload on Ubuntu 22.04 / Debian |
| Socket-aware `enable_pubkey_auth()` | Same socket detection for the pubkey auth reload — ensures sshd picks up config changes on socket-activated systems |
| Robust `write_sshd_config_candidate()` | Use grep+sed+append pattern: if no `Port` line exists in `sshd_config` (common on Ubuntu 24.04 where defaults are implicit), append `Port <port>` instead of silently doing nothing |
| Cross-distro goss SSH enabled check | Replace `service ssh { enabled: true }` with a command check (`systemctl is-enabled ssh.socket \|\| ssh \|\| sshd`). The static `service` check fails on Ubuntu 24.04 where `ssh.service` is not enabled (only `ssh.socket` is). The command fallback chain works on socket-activated (Ubuntu 24.04+), traditional (Ubuntu 22.04, Debian), and Fedora/RHEL (`sshd`) systems |
| Fix `__version__` | `nodeforge_core.__init__.__version__` was stuck at `"0.4.0"` — `nodeforge version` reported the wrong version. Now reads `"0.6.2"` |
| Sync all `pyproject.toml` versions | Root workspace, core, client, and agent `pyproject.toml` files all bumped from `"0.6.0"` to `"0.6.2"` |

**Root cause:** Ubuntu 24.04 (Noble) ships with `ssh.socket` active by default. The `Port` directive in `sshd_config` is ignored for listening — systemd's socket unit controls port binding. Changing the port requires `systemctl daemon-reload` (triggers `sshd-socket-generator` to regenerate `ListenStream` from `sshd_config`) followed by `systemctl restart ssh.socket` to re-bind. The previous `systemctl reload ssh` only signaled the sshd process to re-read config, which has no effect on which port the socket listens on.

**Discovered via:** Manual bootstrap testing against a Hetzner Cloud server running Ubuntu 24.04. The SSH lockout prevention gate correctly caught the failure — admin login on the new port was unreachable because the socket was still bound to port 22.

**Acceptance criteria:**
- `nodeforge apply` bootstrap on Ubuntu 24.04 with socket-activated sshd successfully changes the SSH port and passes the lockout prevention gate
- Goss verification passes on both Ubuntu 24.04 (ssh.socket) and Ubuntu 22.04 (ssh.service)
- Bootstrap on Ubuntu 22.04 / Debian (traditional `ssh.service`) continues to work unchanged
- `nodeforge version` reports `0.6.2`
- `make dev && nodeforge version` shows `0.6.2`
- All unit tests pass including new socket-awareness assertions

**Architectural note — `detect_os` and multi-distro awareness:**

The v0.6.2 goss fix uses a command fallback chain that runs at `goss validate` time on the remote. This works because the SSH service naming is a small, bounded set (ssh.socket / ssh / sshd). However, once nodeforge supports multiple distributions (Fedora, RHEL, Arch, etc.), distro differences will compound across the entire pipeline — not just goss, but also the planner (package manager, service names, firewall provider) and the step builders.

At that point, `detect_os` needs to become a first-class concept:

1. **Today:** `detect_os` runs `cat /etc/os-release` and discards the output. It is a passive assertion step — if it fails, subsequent steps fail due to dependency ordering, but no code reads the result.
2. **Dead code:** `nodeforge_core/utils/os_detect.py` contains an `OSInfo` dataclass with a parser for `/etc/os-release` output. It is never imported anywhere.
3. **Missing:** There is no inter-step data bus (no Ansible-style `register:`/`set_fact:`). Steps cannot read previous step outputs. The Plan is fully static — baked at compile time with no late-binding.
4. **Goss is plan-time:** The goss YAML is generated by the planner (no remote access), embedded as `file_content` in the plan, then uploaded verbatim during apply. The generator cannot access runtime-discovered OS info.

**Future path (when multi-distro lands):** Wire `detect_os` output into an `ExecutionContext` that the executor populates after step 1. Either (a) introduce a two-phase apply where goss is regenerated after OS detection, or (b) generate goss YAML on the remote using a shipped template + the detected OS. The existing `os_detect.py` utility already has the parser — it just needs to be connected.

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

## Binary Distribution Architecture

nodeforge ships two standalone binaries:

| Binary | Targets | Contents | Build Script |
|---|---|---|---|
| `nodeforge` | Linux amd64/arm64, macOS amd64/arm64 | Client + core (includes Fabric, paramiko, sqlcipher3) | `scripts/build_binary.py` |
| `nodeforge-agent` | Linux amd64/arm64 only | Agent + core (minimal — no Fabric, no sqlcipher, no paramiko) | `scripts/build_agent_binary.py` |

Both binaries are built via PyInstaller and published as GitHub Release assets. The client binary includes `nodeforge update` (self-update) and `nodeforge agent-update <host>` (remote agent update). The `updater.py` module downloads the correct platform-specific asset from the latest GitHub Release.

### Future: OSS-to-Pro Upgrade Path

The Pro variant (`nodeforge-pro`) is a separate binary distributed from self-hosted infrastructure (Minio/S3-compatible, bootstrapped with nodeforge itself). The upgrade flow is planned but not yet built:

| Item | Description | Target |
|---|---|---|
| `nodeforge upgrade-to-pro --token <TOKEN>` | CLI command that downloads the Pro binary from a presigned URL and replaces the OSS binary | pro-v0.1 |
| Presigned URL support in updater | `updater.py` gains a `download_from_url()` path alongside the existing GitHub Releases path | pro-v0.1 |
| Localhost callback upgrade | Browser-to-localhost handoff (like Spotify auth) — platform sends upgrade token to companion | pro-v0.2 |
| Self-hosted binary hosting | API endpoint returns presigned S3/Minio URLs; no private GitHub Releases | pro-v0.1 |
| Auto-install agent during apply | Client automatically installs/updates the agent binary on the target server as part of `nodeforge apply` | v0.6 |

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

> **Agent is the trusted execution surface** -- one agent per server, extensible via addons. Infrastructure provisioning is the core job type; the agent's service primitives are available to addons for higher-level workflows.

> **nodeforge is Layer 1** -- it makes VMs ready and usable. Application-level configuration (Layer 2) is out of scope for nodeforge OSS but enabled by the agent's extensible job type system.
