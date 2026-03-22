# nodeforge/compiler/ — Three-Phase Compilation Pipeline

This package implements the core compilation pipeline that transforms a YAML spec into an executable plan. The pipeline runs in three deterministic phases:

```
Phase 1: Parse     (parser.py)     YAML file -> typed Pydantic model
Phase 2: Normalize (normalizer.py) model -> NormalizedContext (resolved paths, keys, derived values)
Phase 3: Plan      (planner.py)    NormalizedContext -> ordered list of Steps
```

---

## Files

| File | Phase | Purpose |
|---|---|---|
| `parser.py` | 1 | Loads YAML spec file into a typed model via `load_spec()`. Threads `strict_env` and `env_file` options through to the loader for environment variable resolution. |
| `normalizer.py` | 2 | Resolves all file paths (spec-relative), reads SSH key contents, derives WireGuard key pairs via PyNaCl, renders Jinja2 templates at plan time, reads compose files, applies `state_dir` overrides, and produces a `NormalizedContext` dataclass. |
| `planner.py` | 3 | Converts a `NormalizedContext` into an ordered `Plan` of `Step` objects with dependency tracking, gate enforcement, and hash computation. |
| `__init__.py` | — | Empty package marker. |

---

## Phase 1: Parse (`parser.py`)

Entry point: `parse(spec_path, *, strict_env=True, env_file=None) -> AnySpec`

- Delegates to `specs/loader.py` which handles YAML loading, `${VAR}` resolution, registry lookup of the `kind` field, and Pydantic model validation.
- The `strict_env` flag controls whether unresolved env vars raise an error or pass through.
- The `env_file` option loads a `.env` file before resolving.

---

## Phase 2: Normalize (`normalizer.py`)

Entry point: `normalize(spec, spec_dir=None) -> NormalizedContext`

The normalizer resolves everything that requires filesystem or environment access:

- **Path resolution**: `login.private_key`, `admin_user.pubkeys`, `wireguard.private_key_file` — all resolved via `resolve_path()` which prefers spec-relative paths.
- **Key reading**: SSH public key file contents, WireGuard private key file contents.
- **Key derivation**: WireGuard public keys derived from private keys via PyNaCl (Curve25519).
- **Client key generation**: auto-generates a WireGuard client Curve25519 key pair; reuses persisted key on re-runs for stable peer identity.
- **Template rendering**: Jinja2 templates are rendered at plan time using `StrictUndefined`; rendered content and SHA-256 hashes stored in `NormalizedContext.rendered_templates` and `template_hashes`.
- **Compose file reading**: static compose files are read from disk and stored in `NormalizedContext.compose_file_content`.
- **State directory**: applies `NODEFORGE_STATE_DIR` or `local.state_dir` override before resolving any local paths.
- **Inventory path**: resolves `db_path` respecting the priority chain (explicit spec field > state_dir > default).

The `NormalizedContext` dataclass carries all resolved values downstream to the planner and executor.

### Per-kind normalizers

- `_normalize_bootstrap()` — full bootstrap normalization (pubkeys, WG keys, SSH conf.d path, admin key discovery)
- `_normalize_service()` — service normalization (login key, inventory path, postgres password env resolution)
- `_normalize_file_template()` — resolve template source paths (spec-relative), render each template with Jinja2, store rendered content and hashes in context
- `_normalize_compose_project()` — resolve template sources, render project templates, read static compose file, resolve login key and inventory path

All are registered in `registry/_builtins.py` and dispatched via `NORMALIZER_REGISTRY`.

---

## Phase 3: Plan (`planner.py`)

Entry point: `plan(ctx: NormalizedContext) -> Plan`

The planner generates a deterministic, ordered list of `Step` objects based on which spec blocks are populated.

### Critical Invariant: SSH Lockout Prevention

```
Step N:   [GATE] verify_admin_login_on_new_port   (gate=True)
Step N+1: disable_root_login                       (depends_on=[N])
Step N+2: disable_password_auth                    (depends_on=[N])
```

Steps that would lock out the operator **MUST** depend on the gate step. If the gate fails, the executor aborts the plan and root access is preserved.

### Bootstrap plan structure

1. **Preflight** — verify root SSH access (`SSH_COMMAND` kind, not `VERIFY` — ensures real SSH execution for step-0 abort logic)
2. **OS detection** — assert Debian/Ubuntu
3. **Apt update** — dedicated `apt_update` step to refresh the package index
4. **Package install** — ufw, wireguard (if enabled) — single `apt-get install` command (no embedded `apt-get update`)
5. **User creation** — admin user with sudo, authorized keys
6. **Pre-port-change gate** — verify admin login before touching sshd
7. **SSH hardening** — port change, config candidate, firewall
8. **Post-port-change gate** — verify admin login on new port
9. **Lockout-gated steps** — disable root login, disable password auth
10. **Firewall finalization** — three separate steps: default deny incoming, default allow outgoing, force enable
11. **WireGuard** (if enabled) — config upload, load kernel module (`modprobe wireguard`), enable, verify, SSH restriction (allow on WG + delete open rule)
12. **Goss verification** — generate, ship, and run server-state checks
12. **Local finalization** — SSH conf.d, WireGuard state save, inventory DB

### Service plan structure

1. **Preflight** — verify admin SSH access (`SSH_COMMAND` kind, not `VERIFY`)
2. **OS detection** — detect remote OS
3. **Apt update** — shared `apt_update` step (emitted when any service needs package installation)
4. **PostgreSQL** (if enabled) — PGDG apt repository setup (prerequisites, signing key, source list, apt update), install, configure, create role/db, verify (`sudo=True` on verify)
5. **Nginx** (if enabled) — install, enable, remove default site, write per-site configs (`SSH_UPLOAD`), enable per-site symlinks, validate config, reload, verify (`sudo=True` on verify)
6. **Docker** (if needed) — install, enable, verify (`sudo=True` on verify)
7. **Containers** — pull, stop, remove, run, health check per container (all steps use `sudo=True` since the admin user is not in the docker group)
8. **Local inventory** — upsert services, record run

### Per-kind planners

- `_plan_bootstrap()` — generates the full bootstrap step sequence
- `_plan_service()` — generates the service deployment step sequence
- `_plan_file_template()` — generates steps per template: mkdir parent, upload rendered content, chmod, chown
- `_plan_compose_project()` — generates steps: apt update, Docker install/enable/verify, mkdir project dir, mkdir managed dirs, upload rendered templates, upload compose file, compose config validate, compose pull, compose up, health check, inventory

All are registered in `registry/_builtins.py` and dispatched via `PLANNER_REGISTRY`.

### File template plan structure

1. **Preflight** — verify admin SSH access
2. **Per-template** — for each template: mkdir parent → upload rendered content → chmod → chown (all `sudo=True`)
3. **Postflight checks** (if defined)
4. **Local inventory** (if enabled)

### Compose project plan structure

1. **Preflight** — verify admin SSH access
2. **Apt update** — refresh package index (always emitted; Docker install requires it)
3. **Docker install** — `curl -fsSL https://get.docker.com | sh` (always emitted; compose_project requires Docker)
4. **Enable Docker service** — `systemctl enable --now docker`
5. **Verify Docker** — `docker --version`
6. **Create project directory** (`mkdir -p`)
7. **Create managed directories** (mkdir + chmod + chown via `bash -c` wrapper)
8. **Upload rendered templates** (`SSH_UPLOAD` with Jinja2-rendered content)
9. **Upload compose file** (`SSH_UPLOAD` with raw file content)
10. **Validate compose config** (`docker compose config --quiet`)
11. **Pull images** (optional, `pull_before_up`)
12. **Start the stack** (`docker compose up -d`)
13. **Health check** (optional, `COMPOSE_HEALTH_CHECK` step kind with configurable timeout/interval)
14. **Postflight checks** (if defined)
15. **Local inventory** (if enabled)

---

## Design Decisions

- **Plan is the single source of truth**: both `docs` (Markdown) and `apply` (execution) consume the same `Plan` object.
- **Steps are re-indexed after generation**: `plan()` assigns final `step.index` values, so planners don't need to track absolute indices.
- **Hashing**: both `spec_hash` (from model JSON) and `plan_hash` (from step IDs + commands) are computed for change detection and audit.
- **Apt update is a separate step**: step builders never embed `apt-get update` inside install commands. The planner emits a dedicated `apt_update` step before any package installation. This avoids Fabric `sudo()` breaking compound `&&` chains (only the first command runs as root).
- **Preflight steps use `SSH_COMMAND` kind**: preflight connection checks use `StepKind.SSH_COMMAND` (not `StepKind.VERIFY`) so the executor's step-0 abort logic works correctly — the echo command actually executes over SSH rather than being intercepted by the verify handler's `startswith("echo ")` short-circuit.
- **Container steps always use `sudo=True`**: the bootstrap process adds the admin user to the `sudo` group but not the `docker` group, so all Docker CLI commands must be elevated.
- **Service verify steps use `sudo=True`**: verification commands like `pg_isready`, `nginx -t`, and `docker --version` may need root access depending on the system configuration.
- **Templates rendered at plan time**: Jinja2 templates are rendered during normalization (phase 2), not at apply time. This makes plans fully reviewable — the exact file content appears in `step.file_content`.
- **Compose commands use `bash -c` wrappers**: Docker Compose commands require `cd` + shell operators, which break Fabric's `sudo()`. All compose commands are wrapped in `bash -c '...'` so a single sudo elevation covers the entire command chain.
