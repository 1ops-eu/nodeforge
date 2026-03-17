# Feature Request: Configurable Local State Directory (NODEFORGE_STATE_DIR)

## Summary

Allow all nodeforge-managed local files (WireGuard state, SSH config
fragments, inventory database) to be routed to a single configurable base
directory, enabling full isolation between production and test/CI contexts.

## Motivation

When nodeforge runs in production it naturally stores state in standard
locations that integrate with the OS:

| Concern | Default path |
|---|---|
| WireGuard client configs & keys | `~/.wg/nodeforge/{host}/` |
| SSH config snippets | `~/.ssh/conf.d/nodeforge/` |
| Host inventory database | `~/.nodeforge/inventory.db` |

This is the right behaviour for a developer's workstation.

However, in a **test or CI context**, writing to `~/.wg/`, `~/.ssh/`, and
`~/.nodeforge/` creates several problems:

1. **Isolation.** Multiple test runs for different projects can collide if
   they use the same host names.
2. **Cleanup.** Test artefacts left in `~/.wg/` are not automatically
   removed when the test suite tears down the VM.
3. **Reproducibility.** A developer's existing `~/.ssh/conf.d/nodeforge/`
   entries from production servers bleed into CI output and vice-versa.
4. **Portability.** In a containerised CI environment, `~` may not persist
   between jobs, making it unreliable as a state location.

The test suite currently works around this by disabling SSH config and
inventory features entirely (`local.ssh_config.enabled: false`,
`local.inventory.enabled: false`).  The WireGuard client config still lands
in `~/.wg/nodeforge/` and must be found there by the post-apply connect test.
There is no way to redirect it to the test suite's own `_env/` directory.

## Proposed Behaviour

Introduce a `NODEFORGE_STATE_DIR` environment variable (and an optional
`local.state_dir` field in the spec) that sets the root for all local
nodeforge output:

| Concern | Default | With `NODEFORGE_STATE_DIR=/path/to/_env` |
|---|---|---|
| WireGuard client configs & keys | `~/.wg/nodeforge/{host}/` | `_env/wg/{host}/` |
| SSH config snippets | `~/.ssh/conf.d/nodeforge/` | `_env/ssh/conf.d/` |
| Host inventory database | `~/.nodeforge/inventory.db` | `_env/inventory.db` |

When `NODEFORGE_STATE_DIR` is set, the include directive added to
`~/.ssh/config` points to `{state_dir}/ssh/conf.d/*` instead of the default.

### Production usage (no change)

```bash
nodeforge apply spec.yaml
# Writes to ~/.wg/nodeforge/, ~/.ssh/conf.d/nodeforge/, ~/.nodeforge/
```

### Test / CI usage

```bash
export NODEFORGE_STATE_DIR=/home/alice/git/my-project/all_tests/nodeforge/_env
nodeforge apply spec.yaml
# Writes to _env/wg/, _env/ssh/conf.d/, _env/inventory.db
# Fully isolated from production state
```

The test suite's `.env` file would then contain:

```dotenv
NODEFORGE_STATE_DIR=/home/alice/git/my-project/all_tests/nodeforge/_env
WG_CLIENT_CONF_DIR=${NODEFORGE_STATE_DIR}/wg/ubuntu-node-1
```

…and the `_env/` directory can be `.gitignore`d as a whole.

## Design Notes

### Resolution order

For each path, the resolution priority is:

1. Per-resource spec field (e.g. `local.inventory.db_path`) — highest priority
2. `NODEFORGE_STATE_DIR` environment variable
3. `local.state_dir` spec field
4. Built-in default (`~/.wg/nodeforge/`, etc.) — lowest priority

### `local_paths.py` changes

`LocalPathsConfig` gains a `state_dir` field.  The default factory reads
`NODEFORGE_STATE_DIR` from the environment:

```python
@dataclass
class LocalPathsConfig:
    state_dir: Path | None = field(
        default_factory=lambda: Path(os.environ["NODEFORGE_STATE_DIR"])
        if "NODEFORGE_STATE_DIR" in os.environ else None
    )

    @property
    def wg_state_base(self) -> Path:
        return (self.state_dir / "wg") if self.state_dir else Path("~/.wg/nodeforge").expanduser()

    @property
    def ssh_conf_d_base(self) -> Path:
        return (self.state_dir / "ssh" / "conf.d") if self.state_dir else Path("~/.ssh/conf.d/nodeforge").expanduser()
```

### Inventory database

`local.inventory.db_path` in the spec defaults to
`{state_dir}/inventory.db` when `NODEFORGE_STATE_DIR` is set, falling back to
`~/.nodeforge/inventory.db`.

The `NODEFORGE_DB_PATH` environment variable (currently used by CLI inventory
commands) is superseded by `NODEFORGE_STATE_DIR`; the existing variable
remains supported for backward compatibility.

### SSH config include path

When writing the `Include` directive to `~/.ssh/config`, use the resolved
`ssh_conf_d_base` path so the include always matches wherever the fragments
are stored.

## Alternatives Considered

- **Per-resource environment variables** (e.g. `NODEFORGE_WG_STATE_DIR`,
  `NODEFORGE_SSH_CONF_DIR`).  More granular but harder to configure and
  document; a single `STATE_DIR` covers the common "redirect everything" use
  case with one variable.
- **Addon registration only** (current mechanism).  Requires writing Python
  code and registering an entry point; not accessible to end-users who only
  have a spec file and an environment.
- **`--state-dir` CLI flag.** Could complement `NODEFORGE_STATE_DIR` but
  adds boilerplate to every `apply` invocation in scripts.

## Acceptance Criteria

- [ ] Setting `NODEFORGE_STATE_DIR=/some/path` redirects WireGuard state,
      SSH conf.d snippets, and the inventory DB to that directory.
- [ ] Unset `NODEFORGE_STATE_DIR` preserves all existing default paths (no
      behaviour change for existing users).
- [ ] `local.state_dir` in the spec provides the same override (lower
      priority than the environment variable).
- [ ] Per-resource overrides (`local.inventory.db_path`) still take
      precedence over `NODEFORGE_STATE_DIR`.
- [ ] Unit tests cover: default paths, env-var override, spec-field override,
      and priority ordering between all three.
- [ ] Documentation updated with a "Test / CI isolation" example.
