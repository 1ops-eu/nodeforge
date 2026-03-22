# Doctor (Drift Detection) Example

Demonstrates the `nodeforge doctor` command — comparing the desired plan state against the server's runtime state to detect drift.

## What it does

The `doctor` command runs a three-step process:

1. **Compile** — generates the desired plan from the spec (same as `nodeforge plan`)
2. **Fetch runtime state** — retrieves the current `runtime-state.json` from the agent
3. **Compare** — diffs desired steps against runtime resource hashes to find drift

The output shows which resources are **in-sync**, **drifted**, or **missing** from the server.

## Usage

```bash
# Check drift against a bootstrap spec
nodeforge doctor examples/bootstrap.yaml

# Check drift against a stack spec
nodeforge doctor examples/stack/stack.yaml

# Reconcile — re-apply only the drifted resources
nodeforge reconcile examples/stack/stack.yaml
```

## How it works

### Agent side

The agent stores two files after each successful apply:

- `/var/lib/nodeforge/desired/desired-state.json` — the plan that was applied
- `/var/lib/nodeforge/state/runtime-state.json` — per-resource hash state

### Client side

The `doctor` command:
1. Generates a fresh plan from the current spec
2. SSHs to the host and runs `nodeforge-agent doctor`
3. The agent compares the desired plan hashes against runtime state
4. Reports drifted, missing, and in-sync resources

The `reconcile` command:
1. Runs `doctor` to identify drift
2. Re-applies only the steps whose resources have drifted or are missing

## Key concepts

- **Hash-based comparison** — each step has a deterministic content hash; drift is detected when hashes differ
- **No re-execution of unchanged resources** — the agent's idempotent executor already skips unchanged steps, and doctor makes this visible
- **Desired state storage** — the agent persists the last-applied plan so drift can be detected even between client invocations

## Structure

```
doctor/
  README.md       # This file
```

No spec file is needed here — `doctor` and `reconcile` work with any existing spec (bootstrap, service, stack, etc.).
