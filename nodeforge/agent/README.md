# nodeforge/agent/ — Server-Side Agent

This package contains the nodeforge agent that runs on managed servers. The agent executes plans locally via subprocess instead of over SSH, enabling reliable operations even during SSH service restarts.

---

## Files

| File | Purpose |
|---|---|
| `cli.py` | Agent CLI: `nodeforge-agent apply`, `status`, `version` commands |
| `executor.py` | Local plan executor: runs steps via subprocess, tracks state, supports idempotent re-apply |
| `state.py` | Runtime state management: `RuntimeState` and `ResourceState` models, atomic load/save |
| `lock.py` | Mutation locking: `MutationLock` context manager, `fcntl`-based exclusive file lock |
| `paths.py` | Server-side path constants: `/etc/nodeforge/`, `/var/lib/nodeforge/`, `/var/log/nodeforge/` |
| `installer.py` | Agent detection and installation utilities |

---

## Architecture

The agent model separates the **client** (transporter) from the **agent** (operator):

1. **Client** generates the plan and uploads it to the target server via SSH
2. **Agent** executes the plan locally using `subprocess.run()` — no SSH round-trips
3. **Agent** tracks resource state in `/var/lib/nodeforge/runtime-state.json`
4. **Client** retrieves the result and runs local steps (SSH conf.d, inventory)

### Execution Flow

```
Client                          Target Server
  │                                  │
  ├── Generate plan                  │
  ├── Upload plan.json ──────────────► /var/lib/nodeforge/desired/plan.json
  ├── Invoke agent ──────────────────► nodeforge-agent apply plan.json
  │                                  ├── Acquire mutation lock
  │                                  ├── Load runtime state
  │                                  ├── For each step:
  │                                  │   ├── Check idempotency (hash)
  │                                  │   ├── Execute locally (subprocess)
  │                                  │   └── Update state
  │                                  ├── Save runtime state
  │                                  └── Write result
  ◄── Retrieve result ──────────────── /var/lib/nodeforge/last-result.json
  ├── Run local steps (SSH conf.d, inventory)
  └── Done
```

### Idempotent Re-Apply

Each step's content is hashed (`sha256(id + command + file_content + target_path)`).
On re-apply, the agent compares hashes against `runtime-state.json`:
- **Hash matches** → step is skipped (status: `unchanged`)
- **Hash differs** → step is re-executed
- **Gate/verify steps** → always re-evaluated regardless of hash

### Mutation Locking

Only one `nodeforge-agent apply` can run at a time. The `MutationLock` uses
`fcntl.flock(LOCK_EX | LOCK_NB)` for atomic, non-blocking lock acquisition.
A second concurrent apply fails immediately with a clear error message.

---

## Server-Side Paths

| Path | Purpose |
|---|---|
| `/etc/nodeforge/` | Configuration (read-only after bootstrap) |
| `/var/lib/nodeforge/` | Runtime state directory |
| `/var/lib/nodeforge/runtime-state.json` | Applied resource hashes and timestamps |
| `/var/lib/nodeforge/desired/` | Uploaded plan and spec files |
| `/var/lib/nodeforge/locks/` | Mutation lock files |
| `/var/lib/nodeforge/last-result.json` | Last apply result (for client retrieval) |
| `/var/log/nodeforge/` | Execution logs |
| `/usr/local/bin/nodeforge-agent` | Agent binary |

---

## CLI Commands

```bash
nodeforge-agent apply <plan.json>   # Execute a plan locally
nodeforge-agent status              # Show current runtime state
nodeforge-agent version             # Print agent version
```
