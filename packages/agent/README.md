# nodeforge-agent

> Server-side agent for nodeforge -- executes plans locally on managed Linux servers.

`nodeforge-agent` is the agent package. It runs on every managed server and executes plans locally via subprocess. The agent is intentionally minimal — it depends only on `nodeforge-core`, `typer`, and `rich`. No Fabric, no paramiko, no sqlcipher.

---

## Installation

The agent is typically installed automatically during `nodeforge apply` (bootstrap). For manual installation:

```bash
pip install nodeforge-agent
```

Or download the standalone binary from the [Releases](../../releases) page:

| Platform | File |
|---|---|
| Linux (x86-64) | `nodeforge-agent-linux-amd64` |
| Linux (ARM64) | `nodeforge-agent-linux-arm64` |

---

## Dependencies

- `nodeforge-core>=0.5.0` -- shared models, specs, policy engine
- `typer[all]>=0.9.0` -- CLI framework
- `rich>=13.0` -- terminal formatting

No Fabric, no paramiko, no sqlcipher3. This keeps the binary small and avoids system library dependencies on managed servers.

---

## Module Structure

```
nodeforge_agent/
  __init__.py     Re-exports __version__ from nodeforge-core
  cli.py          Typer CLI entry point — apply, status, version, doctor
  executor.py     AgentExecutor — local plan execution via subprocess + policy enforcement
  lock.py         Mutation locking via fcntl.flock (one apply at a time)
  paths.py        ensure_agent_dirs() + re-exports path constants from core
  state.py        State management: load/save RuntimeState, resource change detection
```

---

## CLI Commands

```
nodeforge-agent apply   <plan.json>    Execute a plan locally
nodeforge-agent status                 Show current agent state
nodeforge-agent version                Print agent version
nodeforge-agent doctor  <plan.json>    Compare desired state against runtime state
```

---

## Server-Side Paths

The agent uses these directories on the managed server:

| Path | Purpose |
|---|---|
| `/etc/nodeforge/` | Configuration (policy.yaml, platform.conf) |
| `/var/lib/nodeforge/` | Runtime state, locks, desired state |
| `/var/lib/nodeforge/desired/desired-state.json` | Last-applied desired state |
| `/var/lib/nodeforge/runtime-state.json` | Current runtime state (hashes, timestamps) |
| `/var/lib/nodeforge/locks/` | Mutation lock files |
| `/var/log/nodeforge/` | Agent execution logs |

`paths.py` provides `ensure_agent_dirs()` which creates all required directories on first run.

---

## Execution Model

The `AgentExecutor` processes a plan as follows:

1. **Acquire mutation lock** — `fcntl.flock` ensures one apply at a time
2. **Load policy** — reads `/etc/nodeforge/policy.yaml` (if present)
3. **For each step:**
   a. Check if step is idempotent-skippable (content hash matches runtime state)
   b. Evaluate policy — `auto_apply`, `require_approval`, or `deny`
   c. Execute via subprocess (shell commands) or direct file write
   d. Update runtime state with new hash and timestamp
4. **Save runtime state** — atomic write to `runtime-state.json`
5. **Save desired state** — persist plan to `desired-state.json`
6. **Release lock**

### Idempotent Re-Apply

The agent skips unchanged resources on re-apply. Each step's content is hashed (SHA-256). If the hash matches what's recorded in `runtime-state.json`, the step is skipped. This makes `nodeforge apply` safe to run repeatedly.

### Policy Enforcement

If a `policy.yaml` exists on the server, every step is evaluated against its rules before execution:

- **`auto_apply`** — step executes normally
- **`require_approval`** — step needs a valid HMAC-SHA256 approval token (time-limited)
- **`deny`** — step is rejected and logged

No policy file = no checks = agent executes everything it's told.

---

## Mutation Locking

`lock.py` uses `fcntl.flock` to ensure only one `nodeforge-agent apply` runs at a time. If a lock is held, a second apply attempt fails immediately with a clear error message. Locks are automatically released when the process exits.

---

## State Management

`state.py` provides:

| Function | Purpose |
|---|---|
| `load_state(path)` | Load `RuntimeState` from JSON (returns empty state if file missing) |
| `save_state(state, path)` | Atomic write (write to temp + rename) |
| `resource_changed(state, resource_id, content_hash)` | Check if a resource needs re-apply |
| `update_resource(state, resource_id, content_hash)` | Record a resource as applied |

`RuntimeState` is a dict mapping resource IDs to `ResourceState` objects (hash + timestamp). This enables both idempotent skip and drift detection.

---

## Binary Build

The agent binary is built with PyInstaller:

```bash
make build-agent-binary
# or: python scripts/build_agent_binary.py
```

The build script installs `packages/core` + `packages/agent`, then produces a single-file executable. No system library dependencies are needed.

Output: `dist/nodeforge-agent`

The agent binary targets **Linux only** (Debian/Ubuntu). There is no macOS or Windows build — the agent runs on managed servers, not developer machines.

---

## Import Boundary

`nodeforge-agent` may import from:
- `nodeforge_core` (shared models, specs, policy engine)
- Standard library

`nodeforge-agent` must **never** import from `nodeforge` (client). The agent and client are independent consumers of core.
