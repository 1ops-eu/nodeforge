# loft-cli-core

> Shared models, specs, and registry infrastructure for loft-cli.

`loft-cli-core` is the foundation package that both the client (`loft-cli`) and agent (`loft-cli-agent`) depend on. It contains all Pydantic spec schemas, plan models, the registry system, the policy engine, and shared utilities.

**This package has no CLI.** It is a library consumed by the client and agent packages.

---

## Installation

```bash
pip install loft-cli-core
```

Or as part of the monorepo development setup:

```bash
pip install -e packages/core
```

---

## Dependencies

- `pydantic>=2.5` -- spec schemas and validation
- `pyyaml>=6.0` -- YAML loading
- `jinja2>=3.1` -- template rendering
- `rich>=13.0` -- terminal formatting
- `python-dotenv>=1.0` -- `.env` file loading

No Fabric, no paramiko, no sqlcipher. This keeps the package lightweight and installable on managed servers (where the agent runs).

---

## Module Structure

```
loft_cli_core/
  __init__.py          Package root, exports __version__
  agent_models.py      AgentApplyResult, AgentStepResult — shared between client and agent
  agent_paths.py       Server-side path constants (/etc/loft-cli/, /var/lib/loft-cli/, etc.)
  policy.py            Policy engine: rules, evaluation, HMAC-SHA256 approval tokens
  state.py             RuntimeState, ResourceState models — server-side state tracking
  plan/
    __init__.py
    models.py          Plan, Step, NormalizedContext data models
    render_diff.py     Diff renderer — compare plan against runtime state
    render_markdown.py Markdown ops guide renderer
    render_text.py     Plain text plan renderer (CLI output)
  registry/
    __init__.py        Re-exports all registry functions + load_addons()
    executors.py       STEP_HANDLER_REGISTRY — step.kind -> handler function
    hooks.py           HOOKS_REGISTRY — kind -> KindHooks lifecycle callbacks
    local_paths.py     LocalPathsConfig — configurable state directory
    normalizers.py     NORMALIZER_REGISTRY — kind -> normalizer function
    planners.py        PLANNER_REGISTRY — kind -> plan-builder function
    resolvers.py       RESOLVER_REGISTRY — prefix -> value resolver function
    specs.py           SPEC_REGISTRY — kind -> Pydantic model class
    validators.py      VALIDATOR_REGISTRY — kind -> validator function
  specs/
    __init__.py
    bootstrap_schema.py     BootstrapSpec Pydantic model
    compose_project_schema.py ComposeProjectSpec Pydantic model
    file_template_schema.py FileTemplateSpec Pydantic model
    loader.py               load_spec(), load_env_file(), SpecLoadError
    service_schema.py       ServiceSpec Pydantic model
    stack_schema.py         StackSpec Pydantic model + stack validator/planner
    http_check_schema.py    HttpCheckSpec Pydantic model
    systemd_unit_schema.py  SystemdUnitSpec Pydantic model
    systemd_timer_schema.py SystemdTimerSpec Pydantic model
    backup_job_schema.py    BackupJobSpec Pydantic model
    postgres_ensure_schema.py PostgresEnsureSpec Pydantic model
    validators.py           Kind-specific validation logic
  utils/
    __init__.py
    files.py           File I/O helpers
    hashing.py         SHA-256 content hashing for idempotent re-apply
    os_detect.py       OS detection helpers (Debian/Ubuntu)
    templates.py       Jinja2 template rendering
```

---

## Registry System

The registry system is the core extension mechanism. Seven open registries map string keys to callables:

| Registry | Key | Maps to | Purpose |
|---|---|---|---|
| `SPEC_REGISTRY` | `kind` | Pydantic model class | Parse YAML into typed spec |
| `PLANNER_REGISTRY` | `kind` | Plan-builder function | Generate `Step` list from spec |
| `NORMALIZER_REGISTRY` | `kind` | Normalizer function | Resolve paths, keys, secrets |
| `VALIDATOR_REGISTRY` | `kind` | Validator function | Semantic validation |
| `STEP_HANDLER_REGISTRY` | `step.kind` | Handler function | Execute a step |
| `HOOKS_REGISTRY` | `kind` | `KindHooks` dataclass | Lifecycle callbacks |
| `RESOLVER_REGISTRY` | `prefix` | Resolver function | Resolve `${prefix:key}` tokens |

### Addon Loading

External packages register as addons via Python `entry_points`:

```toml
[project.entry-points."loft_cli.addons"]
my_addon = "my_addon:register"
```

`load_addons()` discovers and calls all registered `register()` functions at startup.

---

## Policy Engine

The policy engine (`policy.py`) evaluates per-step policy rules:

- **`auto_apply`** -- step executes without intervention
- **`require_approval`** -- step requires an HMAC-SHA256 approval token
- **`deny`** -- step is rejected

Policy is loaded from `/etc/loft-cli/policy.yaml` on the server. If no policy file exists, the engine is inert (all steps execute normally).

Rules match steps via `fnmatch`-based patterns on step ID, kind, and tags. First matching rule wins. If no rule matches, the `default_action` applies.

---

## Import Boundary

`loft-cli-core` must **never** import from `loft-cli` (client) or `loft_cli_agent`. It is the bottom of the dependency graph:

```
loft-cli (client)  ──depends-on──>  loft-cli-core
loft-cli-agent     ──depends-on──>  loft-cli-core
```

---

## Key Design Decisions

1. **Pydantic v2 with `extra='forbid'`** -- all spec models reject unknown fields, catching typos and schema drift at load time.
2. **Plan is immutable** -- once generated, a Plan is a frozen data structure. Both docs and apply consume the same Plan object.
3. **Registry-based dispatch** -- no `if kind == "bootstrap"` branching. All dispatch goes through registries, making the system extensible without code modification.
4. **Policy is OSS** -- the policy engine is in core, not in the commercial variant. Anyone can audit it.
