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
| `normalizer.py` | 2 | Resolves all file paths (spec-relative), reads SSH key contents, derives WireGuard key pairs via PyNaCl, applies `state_dir` overrides, and produces a `NormalizedContext` dataclass. |
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
- **State directory**: applies `NODEFORGE_STATE_DIR` or `local.state_dir` override before resolving any local paths.
- **Inventory path**: resolves `db_path` respecting the priority chain (explicit spec field > state_dir > default).

The `NormalizedContext` dataclass carries all resolved values downstream to the planner and executor.

### Per-kind normalizers

- `_normalize_bootstrap()` — full bootstrap normalization (pubkeys, WG keys, SSH conf.d path, admin key discovery)
- `_normalize_service()` — service normalization (login key, inventory path, postgres password env resolution)

Both are registered in `registry/_builtins.py` and dispatched via `NORMALIZER_REGISTRY`.

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
11. **WireGuard** (if enabled) — config upload, enable, verify, SSH restriction (allow on WG + delete open rule)
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

Both are registered in `registry/_builtins.py` and dispatched via `PLANNER_REGISTRY`.

---

## Design Decisions

- **Plan is the single source of truth**: both `docs` (Markdown) and `apply` (execution) consume the same `Plan` object.
- **Steps are re-indexed after generation**: `plan()` assigns final `step.index` values, so planners don't need to track absolute indices.
- **Hashing**: both `spec_hash` (from model JSON) and `plan_hash` (from step IDs + commands) are computed for change detection and audit.
- **Apt update is a separate step**: step builders never embed `apt-get update` inside install commands. The planner emits a dedicated `apt_update` step before any package installation. This avoids Fabric `sudo()` breaking compound `&&` chains (only the first command runs as root).
- **Preflight steps use `SSH_COMMAND` kind**: preflight connection checks use `StepKind.SSH_COMMAND` (not `StepKind.VERIFY`) so the executor's step-0 abort logic works correctly — the echo command actually executes over SSH rather than being intercepted by the verify handler's `startswith("echo ")` short-circuit.
- **Container steps always use `sudo=True`**: the bootstrap process adds the admin user to the `sudo` group but not the `docker` group, so all Docker CLI commands must be elevated.
- **Service verify steps use `sudo=True`**: verification commands like `pg_isready`, `nginx -t`, and `docker --version` may need root access depending on the system configuration.
