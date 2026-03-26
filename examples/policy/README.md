# Policy Engine Example

Demonstrates the policy engine — controlling which plan steps the agent is allowed to execute automatically, which require human approval, and which are denied outright.

## What it does

The `policy.yaml` file defines rules that the agent evaluates **per-step** before execution:

| Rule | Matches | Action |
|---|---|---|
| `deny-root-lockout` | Step ID `disable_root_login` | **deny** — refused unconditionally |
| `approve-firewall` | Step IDs matching `ufw_*` | **require_approval** — needs a valid token |
| `approve-destructive` | Steps tagged `destructive` | **require_approval** |
| `auto-commands` | Steps with kind `agent_command` | **auto_apply** — executes without intervention |

If no rule matches, the `default_action` (`auto_apply`) is used.

## Key concepts

- **Policy is inert by default** — no `policy.yaml` means no checks; the agent executes everything
- **Per-step evaluation** — each step is evaluated independently against the rule list
- **First match wins** — rules are evaluated in order; the first matching rule determines the action
- **Approval tokens** — HMAC-SHA256 time-limited tokens for `require_approval` steps
- **AND logic** — if a rule specifies multiple conditions (kind + id + tags), all must match

## Policy actions

| Action | Behaviour |
|---|---|
| `auto_apply` | Step executes without human intervention |
| `require_approval` | Step requires a valid approval token (passed via `--approval-token`) |
| `deny` | Step is refused unconditionally |

## Usage

```bash
# Deploy policy to the target host
scp examples/policy/policy.yaml admin@myhost:/etc/loft-cli/policy.yaml

# Or pass it to the agent directly
loft-cli-agent apply --policy examples/policy/policy.yaml plan.json
```

## Structure

```
policy/
  policy.yaml     # Example policy configuration
  README.md       # This file
```
