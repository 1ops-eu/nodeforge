# nodeforge Roadmap

This document tracks the planned evolution of `nodeforge` from its current v0.1 baseline through a production-ready v1.0 release.

The roadmap is organized around milestones. Each milestone corresponds to a meaningful capability jump. Future infrastructure and design decisions are captured in the RFC series below.

---

## Vision

Nodeforge is a **self-hosted infrastructure compiler** that turns human-readable YAML specs into **reviewable plans** and **deterministic execution**.

The product evolves in three deliberate stages:

1. **Bootstrap and validate** -- reliably harden fresh Linux servers
2. **Deploy and operate** -- manage real multi-service stacks on single hosts
3. **Compose and scale** -- reusable blueprints and light multi-host operations

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

## v0.3 -- Single-Host Compose Stacks

**Goal:** Enable deploying Docker Compose-based multi-service stacks on a single host,
managed entirely through nodeforge specs.

| Item | Description |
|---|---|
| `kind: file_template` | Render managed configuration files from Jinja2 templates and variables |
| `kind: compose_project` | Manage Docker Compose projects: upload compose file, pull, up, health check |
| Managed directories | Deterministic creation of project directories on the remote host |
| Compose health checks | Wait for container health after `docker compose up -d`; surface failures |

**New capabilities:**
- Rendered `.env` files, `docker-compose.yml` files, and arbitrary config from Jinja2 templates
- Change detection for rendered files (hash-based)
- Docker Compose validation (`docker compose config`) before apply
- Health-aware startup with configurable timeout and retry

**Acceptance criteria:**
- A fresh bootstrapped VPS can run a multi-container Compose stack (e.g., database + web app
  + reverse proxy) using only nodeforge-managed specs
- Template rendering is deterministic and reviewable in the plan
- Health check failures are surfaced clearly in apply output

---

## v0.4 -- UX + Spec Ergonomics

**Goal:** Make nodeforge pleasant enough for daily use in a real infra repository.

| Item | Description |
|---|---|
| `nodeforge version` | Print current version |
| `nodeforge update` | Self-update from GitHub Releases |
| Shell completion | Enable `typer` completion install |
| Spec dry-run diff | Show exactly what would change on the server before applying |
| Multiple YAML documents | Allow `---` documents in a single file |

**Acceptance criteria:**
- Plans are reviewable and stable
- One file can describe multiple resources
- Operators can inspect intended changes before execution

---

## v0.5 -- Stack Foundations + Addon Architecture

**Goal:** Introduce a first-class single-host stack model and the addon extension system.

| Item | Description |
|---|---|
| Addon registry | Formalize external addon discovery and lifecycle |
| Addon discovery | External addons register via `[project.entry-points."nodeforge.addons"]` |
| `kind: stack` | Group related resources into a single deployable application boundary |
| Apply ordering | Stack-aware dependency-ordered execution |
| Overlay / env-file layering | Multiple `.env` file layers with explicit precedence order (RFC 008) |

**Acceptance criteria:**
- Nodeforge can define stacks that group file_template + compose_project resources
- Stacks execute in dependency order

---

## v0.6 -- Operational Primitives

**Goal:** Make single-host stacks operationally safe and maintainable.

| Item | Description |
|---|---|
| `kind: systemd_unit` | Deploy and manage host-native systemd services |
| `kind: systemd_timer` | Deploy scheduled execution via systemd timers |
| `kind: backup_job` | Define host-local backup operations with retention semantics |
| Log rotation | Support log rotation policies |
| Resource policies | Encourage CPU/RAM limits, restart policies, volume mounts |

**New capabilities:**
- Timer-based recurring operations (reconcile, cleanup, scheduled jobs)
- PostgreSQL dump backups with timestamped naming and retention
- Restore metadata files
- systemd daemon-reload, enable, start lifecycle

**Acceptance criteria:**
- Timers can trigger local jobs or HTTP hooks
- Backup jobs can be installed and run predictably
- Rerun is idempotent -- unchanged units are not recreated

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

## v0.8 -- Multi-Host Light Operations

**Goal:** Support practical small-fleet workflows without requiring a full control plane.

| Item | Description |
|---|---|
| Multi-host inventory | Target multiple hosts via explicit list, tags, or role labels |
| Selectors | `role=worker`, `env=staging`, `stack=automation` |
| Sequential apply | Apply across selected hosts in order |
| Aggregated doctor/drift | Per-host validation with aggregated summary |
| Failure handling | Stop on first failure or continue through all hosts |

**Acceptance criteria:**
- A small fleet can be managed using one logical deployment command
- Results are aggregated and attributable per host
- Doctor/drift summaries available at fleet level

---

## v1.0 -- Production-Ready Release

**Goal:** Make nodeforge stable enough for unattended production use by independent operators.

| Item | Description |
|---|---|
| Stable spec schema | Commit to backwards-compatible format; document breaking change policy |
| Full test coverage | Unit + integration coverage for all compiler, plan, and runtime paths |
| Signed release artifacts | GPG-sign binaries; publish `.sig` files (RFC 003) |
| SHA-256 checksums | `checksums.txt` with every release |
| CONTRIBUTING.md | Contributor guide, PR process, local dev setup |
| CHANGELOG.md | Automated changelog from conventional commits |
| Docs site | Generated from README + per-spec reference docs |

**Acceptance criteria:**
- A second operator can reproduce a full stack deployment from docs + repo
- Upgrades and re-applies are reliable and idempotent
- All release artifacts are signed and verifiable

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

---

## Platform Scope

nodeforge runs on **Linux and macOS only**. Windows is not a supported client platform.

The target of every spec is always a remote Linux server (Debian/Ubuntu). nodeforge itself — the CLI that connects and applies changes — requires a Unix environment to manage local state correctly (SSH `conf.d`, WireGuard key material, POSIX paths).

**Future consideration (post-v1.0):** A lightweight Windows client could be built on top of a nodeforge API server. The API server would run on a Linux host, expose the compile-plan-apply pipeline over HTTP, and accept spec payloads from any platform. This eliminates the local-state complexity on the Windows side entirely. This is not scheduled and not in scope for v1.0.

---

## Guiding Principles

> **Plan is the single source of truth** -- what you review is exactly what executes.

> **Ship a real self-hosted stack first** -- prove the model on a single host before generalizing.

> **Composable specs that scale** -- from one VPS to a small fleet.

> **No vendor lock-in** -- self-hosted by default, no mandatory external services.

> **Operational safety over hidden magic** -- health checks, resource limits, and explicit failure handling.
