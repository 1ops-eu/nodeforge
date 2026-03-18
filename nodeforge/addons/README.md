# nodeforge/addons/ — Built-in Optional Components

This package contains built-in addons that ship with nodeforge but are architecturally separate from the core compiler/runtime pipeline. Each addon is a self-contained subpackage.

External addons are distributed as separate Python packages and discovered at runtime via the `nodeforge.addons` entry_points group.

---

## Current Built-in Addons

### `goss/` — Server-State Verification

The Goss addon is both a functional component and a **reference implementation** demonstrating the addon pattern. It automatically verifies server state after a successful bootstrap.

#### Files

| File | Purpose |
|---|---|
| `goss/__init__.py` | Package docstring |
| `goss/generator.py` | Generates a goss-compatible YAML spec from a `BootstrapSpec`. Every check is driven by live spec values — no hardcoded user names, ports, or interfaces. |
| `goss/shipper.py` | Ships goss binary + spec to the remote server, updates the master gossfile, runs `goss validate --format json`, returns parsed results. |
| `goss/renderer.py` | Renders goss validation results as a Rich console table with colour-coded status, summary line, and failure detail panel. |

#### How it works

1. **Generator** (`generator.py`) inspects the `BootstrapSpec` and produces a goss YAML with checks for:
   - Users (admin account, groups, home dir)
   - Files (sshd_config contents, authorized_keys, WireGuard config)
   - Services (ssh, ufw, wg-quick)
   - Ports (SSH port listening, port 22 not listening if changed)
   - Packages (wireguard-tools)
   - Commands (ufw status, ip address show, wg show)

2. **Shipper** (`shipper.py`) handles the remote side:
   - Installs goss via curl if not present
   - Creates `~/.goss/` directory
   - Uploads the generated spec
   - Read-modify-writes the master gossfile (`~/.goss/goss.yaml`) so each spec is accumulated
   - Runs `goss validate --format json` and parses the JSON output

3. **Renderer** (`renderer.py`) displays results:
   - Rich table with resource type, ID, property, status, details
   - Summary line with pass/fail counts and duration
   - Separate failure panel listing only failing checks for immediate action

#### Integration with the executor

The goss addon is not registered as a traditional addon via `entry_points`. Instead, the bootstrap planner directly imports `generator.py` to embed the goss spec in plan steps (`ship_goss_file` + `run_goss_validate`), and the executor's `_execute_goss_validate()` method calls `shipper.ship_and_run()` and `renderer.render_goss_results()`.

If the generator fails for any reason, the plan emits a `goss_unavailable` warning step — the plan never breaks because of test-tooling issues.

---

## Writing a New Addon

See the [Addon / Extension Architecture section in README.md](../../README.md#addon--extension-architecture) for the full addon registration pattern using Python entry_points.

An addon's `register()` function can register:
- Spec kinds (`register_spec_kind`)
- Normalizers (`register_normalizer`)
- Planners (`register_planner`)
- Validators (`register_validator`)
- Step handlers (`register_step_handler`)
- Lifecycle hooks (`register_kind_hooks`)
- Custom local paths (`register_local_paths`)
