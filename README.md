# nodeforge

> **A CLI that safely bootstraps fresh Linux servers into production-ready self-hosted nodes — generating human-readable ops documentation, managing local SSH config, and maintaining an encrypted local inventory — all from a single typed YAML spec.**

---

## What nodeforge does

1. **Validate** — checks a YAML spec for correctness and safety
2. **Plan** — generates a deterministic, reviewable execution plan
3. **Docs** — renders a human-readable Markdown ops guide from the plan
4. **Apply** — executes the plan safely, enforcing SSH lockout prevention

From a single YAML spec, you get:
- A secure, hardened Linux server (SSH key-only, custom port, ufw, WireGuard)
- A Markdown runbook you can put in your wiki
- A local `~/.ssh/conf.d/` entry for easy SSH access
- An encrypted local inventory (SQLCipher) with full historization

---

## Installation

```bash
# System dependency (Debian/Ubuntu)
apt-get install libsqlcipher-dev

# macOS
brew install sqlcipher

# Install nodeforge
pip install .
```

---

## Quick Start

### 1. Bootstrap a fresh server

```bash
# Create your spec
cp examples/bootstrap.yaml my-server.yaml
# Edit: set host.address, login.private_key, admin_user.pubkeys

# Validate
nodeforge validate my-server.yaml

# Preview the plan
nodeforge plan my-server.yaml

# Generate ops docs
nodeforge docs my-server.yaml -o MY_SERVER_BOOTSTRAP.md

# Apply (bootstraps the server)
NODEFORGE_SQLCIPHER_KEY='your-key' nodeforge apply my-server.yaml
```

After apply, you can SSH directly:
```bash
ssh my-server-name  # via the ~/.ssh/conf.d/ entry nodeforge created
```

### 2. Install PostgreSQL

```bash
nodeforge apply examples/postgres.yaml
```

### 3. Deploy a Docker container

```bash
nodeforge apply examples/app-container.yaml
```

---

## Commands

```
nodeforge validate <spec.yaml>          Validate a spec file
nodeforge plan     <spec.yaml>          Show the execution plan
nodeforge docs     <spec.yaml> [-o FILE] [--mode guide|commands]
                                         Generate Markdown ops docs
nodeforge apply    <spec.yaml> [--dry-run]
                                         Execute the plan
nodeforge inspect  run <run-id>          Inspect a past run
nodeforge inventory list                 List all servers
nodeforge inventory show <server-id>     Show server details
```

---

## Architecture

```
YAML Spec
  └─ Parse (loader.py)
       └─ Validate (validators.py)
            └─ Normalize (normalizer.py)
                 └─ Plan (planner.py)
                      ├─ Docs  (render_markdown.py)
                      └─ Apply (executor.py)
                               ├─ Remote: SSH via Fabric
                               └─ Local:
                                    ├─ SSH conf.d entry
                                    └─ SQLCipher inventory
```

**Plan is the single source of truth.** Both docs and apply are generated from the same Plan object — what you review is exactly what executes.

### SSH Lockout Prevention

The critical bootstrap invariant enforced by the planner:

```
Step 10: [GATE] verify_admin_login_on_new_port
Step 11: disable_root_login         (depends_on: [10])
Step 12: disable_password_auth      (depends_on: [10])
```

Steps 11 and 12 **never execute** unless the gate (SSH login verification) passes. If the gate fails, the plan aborts and you keep root access.

### Local State Management

After a successful bootstrap:
- `~/.ssh/conf.d/{host_name}.conf` — SSH alias to the new server
- `~/.nodeforge/inventory.db` — SQLCipher-encrypted server inventory
- `~/.nodeforge/runs/` — JSON execution logs

---

## Spec Types

### `kind: bootstrap`

Hardens a fresh Debian/Ubuntu server:
- Creates admin user with SSH key auth
- Configures custom SSH port
- Disables root login and password auth
- Enables UFW firewall
- Configures WireGuard VPN
- Updates local SSH config + encrypted inventory

See [examples/bootstrap.yaml](examples/bootstrap.yaml)

### `kind: service`

Installs services on an already-bootstrapped server:
- PostgreSQL (with optional role/database creation)
- Docker
- Docker containers (with health checks)

See [examples/postgres.yaml](examples/postgres.yaml) and [examples/app-container.yaml](examples/app-container.yaml)

---

## SQLCipher Inventory

nodeforge maintains a local encrypted database using the `sqlcipher3` library. The database uses a full historization system (versionize triggers) — every change is recorded with timestamps, so you can see the full history of your server inventory.

```bash
export NODEFORGE_SQLCIPHER_KEY='your-strong-key'
nodeforge inventory list
nodeforge inventory show prod-node-1
```

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/test_specs/ tests/test_compiler/ tests/test_plan/ -v
pytest tests/test_local/ -v  # requires sqlcipher3
```

---

## What nodeforge is not

- Not a general-purpose config management system (not Ansible)
- Not a Kubernetes orchestrator
- Not a UI/SaaS product
- Not an agent framework

**V1 scope:** Single host, Debian/Ubuntu only, PostgreSQL + Docker as the only add-ons.

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
