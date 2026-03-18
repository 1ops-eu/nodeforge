# nodeforge/registry/ — Open Dispatch Registries

This package contains all open registries that power nodeforge's extensible pipeline. Every dispatch point in the system — from spec parsing to step execution — uses a registry lookup, making it possible for external addons to extend nodeforge without modifying core source files.

---

## How It Works

Registries are simple `dict[str, Callable]` mappings. Built-in kinds (`bootstrap`, `service`) are registered at startup via `_builtins.py`. External addons register via Python `entry_points` and are discovered by `load_addons()`.

The `load_addons()` function is **idempotent** — it runs once on first call, subsequent calls are no-ops. It is called automatically by the CLI startup callback and lazily by `load_spec()` and `validate_spec()` for non-CLI usage (tests, library imports).

---

## Files

| File | Purpose |
|---|---|
| `__init__.py` | Public API: re-exports all registration functions + `load_addons()` entry point |
| `_builtins.py` | Registers built-in `bootstrap` and `service` kinds across all registries at startup (all imports are lazy to avoid circular dependencies) |
| `specs.py` | `SPEC_REGISTRY`: maps `kind` string -> Pydantic model class |
| `planners.py` | `PLANNER_REGISTRY`: maps `kind` -> plan-builder function `(spec, ctx) -> list[Step]` |
| `normalizers.py` | `NORMALIZER_REGISTRY`: maps `kind` -> normalizer function `(spec, ctx) -> None` |
| `validators.py` | `VALIDATOR_REGISTRY`: maps `kind` -> validator function `(spec) -> list[ValidationIssue]` |
| `executors.py` | `STEP_HANDLER_REGISTRY`: maps step kind string -> handler `(executor, step) -> StepResult` |
| `hooks.py` | `HOOKS_REGISTRY`: maps `kind` -> `KindHooks` dataclass with lifecycle callbacks |
| `resolvers.py` | `RESOLVER_REGISTRY`: maps prefix string -> resolver callable `(key: str) -> str \| None` |
| `local_paths.py` | `LocalPathsConfig`: addon-overridable filesystem paths for all local state (SSH conf.d, WireGuard, inventory, logs) |

---

## Registry Summary

| Registry | Key | Value | Used By |
|---|---|---|---|
| `SPEC_REGISTRY` | spec `kind` | Pydantic model class | `loader.py` (parse) |
| `PLANNER_REGISTRY` | spec `kind` | plan-builder callable | `planner.py` (phase 3) |
| `NORMALIZER_REGISTRY` | spec `kind` | normalizer callable | `normalizer.py` (phase 2) |
| `VALIDATOR_REGISTRY` | spec `kind` | validator callable | `validators.py` |
| `STEP_HANDLER_REGISTRY` | step `kind` | executor handler | `executor.py` (apply) |
| `HOOKS_REGISTRY` | spec `kind` | `KindHooks` dataclass | `cli.py` (lifecycle) |
| `RESOLVER_REGISTRY` | prefix string | resolver `(key) -> str \| None` | `loader.py` (value resolution) |

---

## Resolver Registry

The `RESOLVER_REGISTRY` (`resolvers.py`) maps prefix strings to value resolver callables. It is used by `_resolve_values()` in `specs/loader.py` to resolve `${prefix:key}` tokens in spec files.

### Resolver callable signature

```python
(key: str) -> str | None
```

Return the resolved string value, or `None` if the key is not found / unset. The caller applies the default value, raises `SpecLoadError` in strict mode, or leaves the token unchanged in passthrough mode.

### Built-in resolvers

| Prefix | Behaviour |
|---|---|
| `env` | Looks up `os.environ`. Bare `${VAR}` is a permanent shorthand for `${env:VAR}`. |
| `file` | Reads the file at the given path, strips one trailing newline. `~` is expanded. Returns `None` if the file does not exist. |

### Token syntax

| Token | Meaning |
|---|---|
| `${VAR}` | Bare reference — permanent shorthand for `${env:VAR}` |
| `${env:VAR}` | Explicit environment variable lookup |
| `${file:/path/to/file}` | Read file contents |
| `${prefix:key}` | Dispatch to any addon-registered resolver |
| `${VAR:-default}` | Use *default* if resolved value is `None`; works with any prefix |

### Registering a resolver from an addon

```python
from nodeforge.registry import register_resolver

def register():
    register_resolver("sops", _resolve_sops)

def _resolve_sops(key: str) -> str | None:
    # key format: "path/to/secrets.yaml#json.dot.path"
    ...
```

---

## KindHooks

The `KindHooks` dataclass (`hooks.py`) allows spec kinds to declare CLI-level behaviours without `isinstance()` checks:

- `needs_key_generation: bool` — auto-generate SSH key pairs before normalization
- `ssh_port_fallback: bool` — try `ssh.port` if `login.port` is unreachable on re-runs
- `on_inventory_record: Callable | None` — post-apply callback to record results in inventory

---

## LocalPathsConfig

The `LocalPathsConfig` dataclass (`local_paths.py`) centralizes all filesystem paths for local state. It supports three override levels:

1. **Explicit field values** (e.g., `ssh_conf_d_base=Path(...)`)
2. **`state_dir`** (from `NODEFORGE_STATE_DIR` env var or explicit)
3. **Built-in defaults** (`~/.ssh/conf.d/nodeforge/`, `~/.wg/nodeforge/`, etc.)

Addons override paths by calling `register_local_paths()` — last registration wins.

---

## External Addon Registration

```toml
# addon's pyproject.toml
[project.entry-points."nodeforge.addons"]
my_addon = "my_addon:register"
```

```python
# my_addon/__init__.py
def register():
    from nodeforge.registry import (
        register_spec_kind, register_planner, register_normalizer,
        register_validator, register_step_handler, register_kind_hooks, KindHooks,
        register_resolver,
    )
    register_spec_kind("my_kind", MySpec)
    register_planner("my_kind", _plan_my_kind)
    register_resolver("my_prefix", _resolve_my_prefix)
    # ... etc.
```

---

## Design Decisions

- **Lazy imports in `_builtins.py`**: all imports are inside function bodies to prevent circular dependencies between `compiler/`, `specs/`, `runtime/`, and `registry/`.
- **`StepKind` is an open string, not a closed Enum**: addons can register arbitrary step kind strings without editing core code.
- **Module-level singleton for `LocalPathsConfig`**: replaced wholesale on each `register_local_paths()` call, so there is no global mutable state beyond one reference swap.
