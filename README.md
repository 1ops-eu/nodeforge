# nodeforge

> **A CLI that safely bootstraps fresh Linux servers into production-ready self-hosted nodes — generating human-readable ops documentation, managing local SSH config, and maintaining a local inventory — all from a single typed YAML spec.**

---

## Installation

### Option 1 — pip (recommended for Python users)

```bash
pip install nodeforge
```

### Option 2 — Standalone binary

Download the pre-built binary for your platform from the [Releases](../../releases) page:

| Platform | File |
|---|---|
| Linux (x86-64) | `nodeforge-linux-amd64` |
| macOS | `nodeforge-macos-amd64` |
| Windows (x86-64) | `nodeforge-windows-amd64.exe` |

```bash
# Linux / macOS
chmod +x nodeforge-linux-amd64
sudo mv nodeforge-linux-amd64 /usr/local/bin/nodeforge

# Verify
nodeforge --help
```

### Option 3 — Docker

```bash
docker run --rm ghcr.io/1ops-eu/nodeforge:latest --help
```

With a spec file and SSH key:

```bash
docker run --rm \
  -v ~/.ssh:/root/.ssh:ro \
  -v $(pwd)/my-server.yaml:/spec.yaml:ro \
  ghcr.io/1ops-eu/nodeforge:latest apply /spec.yaml
```

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
- A local inventory with full historization

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
nodeforge apply my-server.yaml
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
                                     └─ Local inventory
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

### Server Verification (Goss)

`nodeforge apply` automatically verifies the server after every successful bootstrap using [Goss](https://github.com/goss-org/goss):

1. Generates a goss spec from the live spec values (ports, users, WireGuard interface, etc.)
2. Installs goss on the remote server if absent
3. Uploads the spec to `~/.goss/<spec-name>.yaml`
4. Accumulates it into a master gossfile `~/.goss/goss.yaml` (so re-running adds to, not replaces, prior specs)
5. Runs `goss -g ~/.goss/goss.yaml validate` and displays a Rich results table

If goss cannot run for any reason, apply prints a **bold yellow warning** and continues — the server is still configured.

To re-run goss manually or check a specific static reference spec:

```bash
# On the server
goss -g ~/.goss/goss.yaml validate

# Via Makefile (copies a static reference spec and runs it)
make test-goss HOST=203.0.113.10 PORT=2222 USER=admin
```

Each example in `examples/ubuntu/` ships as a pair — a nodeforge YAML and a matching `.goss.yaml` reference spec side-by-side in the same folder:

```
examples/ubuntu/
  04-firewall-ssh2222/
    04-firewall-ssh2222.yaml        ← nodeforge spec
    04-firewall-ssh2222.goss.yaml   ← static goss reference
```

### Local State Management

After a successful bootstrap:
- `~/.ssh/conf.d/{host_name}.conf` — SSH alias to the new server
- `~/.nodeforge/inventory.db` — local server inventory
- `~/.nodeforge/runs/` — JSON execution logs
- `~/.goss/` — goss specs and master gossfile deposited by nodeforge

---

## Spec Types

### `kind: bootstrap`

Hardens a fresh Debian/Ubuntu server:
- Creates admin user with SSH key auth
- Configures custom SSH port
- Disables root login and password auth
- Enables UFW firewall
- Configures WireGuard VPN
- Updates local SSH config + inventory

See [examples/bootstrap.yaml](examples/bootstrap.yaml)

### `kind: service`

Installs services on an already-bootstrapped server:
- PostgreSQL (with optional role/database creation)
- Docker
- Docker containers (with health checks)

See [examples/postgres.yaml](examples/postgres.yaml) and [examples/app-container.yaml](examples/app-container.yaml)

---

## Local Inventory

nodeforge maintains a local database with a full historization system (versionize triggers) — every change is recorded with timestamps, so you can see the full history of your server inventory.

```bash
nodeforge inventory list
nodeforge inventory show prod-node-1
```

---

## Development

```bash
# Install with dev dependencies (creates .venv automatically)
make dev

# Run tests
make test            # unit + integration (no live host needed)
make test-local      # local integration tests

# Lint and format
make lint
make fmt

# Smoke tests against example specs
make validate-example
make plan-example
make docs-example
```

### Building a standalone binary locally

```bash
# Linux / macOS
make build-binary

# Windows
python scripts/build_binary.py
# or
powershell -ExecutionPolicy Bypass -File scripts\build_binary.ps1
```

### Building the Docker image locally

```bash
make build-docker
```

---

## Release flow

Releases are triggered by Git tags:

```bash
# Bump version in pyproject.toml and nodeforge/__init__.py, then:
git add pyproject.toml nodeforge/__init__.py
git commit -m "chore(release): bump version to 0.2.0"
git push origin main

git tag v0.2.0
git push origin v0.2.0
```

GitHub Actions will automatically:
1. Build binaries for Linux, macOS, and Windows
2. Generate `checksums.txt`
3. Create a GitHub Release with all assets
4. Build and push the Docker image to `ghcr.io/1ops-eu/nodeforge`

---

## What nodeforge is not

- Not a general-purpose config management system (not Ansible)
- Not a Kubernetes orchestrator
- Not a UI/SaaS product
- Not an agent framework

**V1 scope:** Single host, Debian/Ubuntu only, PostgreSQL + Docker as the only add-ons.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full milestone plan from v0.1 through v1.0, including planned work on stack deployment, Docker Compose runtime, operational primitives, reusable blueprints, and multi-host operations.

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
