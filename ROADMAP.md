# nodeforge Roadmap

This document tracks the planned evolution of `nodeforge` from its current v0.1 baseline through commercial readiness.

The roadmap is organized around milestones. Each milestone corresponds to a meaningful capability jump. Future infrastructure and policy decisions are captured in the RFC series below.

---

## Current State — v0.1 (now)

| Area | Status |
|---|---|
| `pip install` distribution | Done |
| Bootstrap spec (harden fresh Debian/Ubuntu) | Done |
| Service specs (PostgreSQL, Docker, containers) | Done |
| Encrypted local inventory (SQLCipher) | Done |
| SSH lockout prevention gate | Done |
| Goss server verification | Done |
| Run logs | Done |
| Standalone binary builds (Linux, macOS, Windows) | Infrastructure ready (RFC 001/002) |
| Docker image | Infrastructure ready (RFC 001/002) |
| GitHub Actions release pipeline | Infrastructure ready (RFC 001/002) |

---

## v0.2 — Hardening + CI validation

| Item | Description |
|---|---|
| Smoke test suite | Validate `validate`, `plan`, `docs` commands against all example specs in CI — no live host needed |
| Linux ARM64 binary | Add `ubuntu-latest` ARM runner to `release.yml` matrix |
| macOS Intel + Apple Silicon split | Separate matrix entries for `macos-13` (Intel) and `macos-latest` (ARM) |
| Windows ZIP | Package `nodeforge.exe` + a README into a `.zip` asset alongside the raw `.exe` |
| PyPI publish | Add a `pypi.yml` workflow to publish the wheel to PyPI on tag |
| `ruff` + `black` CI enforcement | Add a `lint.yml` workflow that runs on every push/PR |

---

## v0.3 — Platform coverage + UX

| Item | Description |
|---|---|
| Windows binary stabilization | Validate `sqlcipher3` Windows build path; document or replace with SQLite fallback for inventory |
| `nodeforge update` command | Self-update from GitHub Releases |
| Shell completion | Enable `typer` completion install (`nodeforge --install-completion`) |
| `nodeforge version` command | Print current version, linked to `__version__` in `nodeforge/__init__.py` |
| Spec dry-run diff | Show exactly what would change on the server before applying |
| Multiple spec kinds in one file | Allow `---` YAML documents in a single file |

---

## v1.0 — Production-ready release

| Item | Description |
|---|---|
| Stable spec schema | Commit to backwards-compatible spec format; document breaking change policy |
| Full test coverage | Unit + integration coverage for all compiler, plan, and runtime paths |
| Signed release artifacts | GPG-sign binaries; publish `.sig` files alongside each release asset (RFC 003) |
| SHA-256 checksums | `checksums.txt` published with every release (already in release.yml) |
| CONTRIBUTING.md | Contributor guide, PR process, local dev setup |
| CHANGELOG.md | Automated changelog from conventional commits |
| Docs site | Generated from existing README + per-spec reference docs |

---

## v2.0 — Open-core / Commercial readiness

| Item | Description |
|---|---|
| Open-core packaging model | Separate community and enterprise feature sets (RFC 004) |
| Plugin / extension architecture | Allow third-party spec types and executors (RFC 005) |
| Private registry support | Publish enterprise images to private GHCR/ECR/ACR registries |
| License enforcement | Optional feature-flag / license-key system for enterprise builds |
| Multi-host specs | Apply a single spec to a fleet of servers |
| Audit trail export | Export run logs + inventory snapshots to external systems |

---

## RFC Series

| RFC | Title | Status |
|---|---|---|
| RFC 001 | Distribution and Release Strategy | Adopted (this repo) |
| RFC 002 | Concrete Implementation Blueprint | Adopted (this repo) |
| RFC 003 | Release Signing and Artifact Integrity | Planned — v1.0 |
| RFC 004 | Commercial / Open-Core Packaging Strategy | Planned — v2.0 |
| RFC 005 | Plugin / Extension Architecture | Planned — v2.0 |
| RFC 006 | Cross-platform Smoke Testing and QA Gates | Planned — v0.2 |

---

## Guiding Principle

> Track source in Git, publish binaries in GitHub Releases, publish container images in a registry.
>
> Plan is the single source of truth — what you review is exactly what executes.
