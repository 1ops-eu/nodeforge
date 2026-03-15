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

## Current State -- v0.1 (baseline)

| Area | Status |
|---|---|
| `pip install` distribution | Done |
| Bootstrap spec (harden fresh Debian/Ubuntu) | Done |
| Service specs (PostgreSQL, Docker, containers) | Done |
| Local inventory (SQLite) | Done |
| SSH lockout prevention gate | Done |
| Goss server verification | Done |
| Run logs | Done |
| Standalone binary builds (Linux, macOS, Windows) | Infrastructure ready (RFC 001/002) |
| Docker image | Infrastructure ready (RFC 001/002) |
| GitHub Actions release pipeline | Infrastructure ready (RFC 001/002) |

---

## v0.2 -- Hardening + CI Validation

**Goal:** Make the existing tool stable enough to serve as the foundation for the next architectural steps.

| Item | Description |
|---|---|
| Smoke test suite | Validate `validate`, `plan`, `docs` commands against all example specs in CI -- no live host needed |
| Linux ARM64 binary | Add ARM runner to `release.yml` matrix |
| macOS Intel + Apple Silicon split | Separate matrix entries for `macos-13` (Intel) and `macos-latest` (ARM) |
| Windows ZIP | Package `nodeforge.exe` + README into a `.zip` asset |
| PyPI publish | `pypi.yml` workflow to publish the wheel on tag |
| `ruff` + `black` CI enforcement | `lint.yml` workflow on every push/PR |

**Acceptance criteria:**
- All example specs validate and generate docs in CI
- Release assets are reliably produced for all target platforms
- PyPI release on tag

---

## v0.3 -- UX + Spec Ergonomics

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

## v0.4 -- Stack Foundations

**Goal:** Introduce a first-class single-host stack model. This is the foundation for deploying real production stacks.

| Item | Description |
|---|---|
| `kind: stack` | Group related resources into a single deployable application boundary |
| `kind: file_template` | Render managed configuration files from templates and variables |
| Managed directories | Deterministic runtime directory layout |
| Apply ordering | Stack-aware dependency-ordered execution |

**New capabilities:**
- Rendered `.env` files, reverse proxy configs, helper scripts, compose files
- Change detection for rendered files
- Variable interpolation in templates
- Stack-level shared variables inherited by child resources

**Acceptance criteria:**
- Nodeforge can reproducibly materialize all config needed for a multi-service stack on a host

---

## v0.5 -- Docker Compose Runtime

**Goal:** Make Docker Compose a first-class single-host runtime target.

| Item | Description |
|---|---|
| `kind: compose_project` | Represent a Docker Compose project managed by nodeforge |
| Compose validation | `docker compose config` before apply |
| Health-aware startup | Wait for container health checks after `up -d` |
| Structured runtime logs | Capture Compose output for run records |

**Acceptance criteria:**
- A fresh VPS can be bootstrapped and can run PostgreSQL + a web application + a reverse proxy using only nodeforge-managed specs
- Health failures are surfaced clearly

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
| RFC 006 | Cross-Platform Smoke Testing and QA Gates | Planned | v0.2 |
| RFC 007 | Single-Host Stack Runtime Model | Planned | v0.4--v0.6 |
| RFC 012 | Light Blueprints and Stack Composition | Planned | v0.7 |
| RFC 013 | Multi-Host Light Operations | Planned | v0.8 |

---

## Guiding Principles

> **Plan is the single source of truth** -- what you review is exactly what executes.

> **Ship a real self-hosted stack first** -- prove the model on a single host before generalizing.

> **Composable specs that scale** -- from one VPS to a small fleet.

> **No vendor lock-in** -- self-hosted by default, no mandatory external services.

> **Operational safety over hidden magic** -- health checks, resource limits, and explicit failure handling.
