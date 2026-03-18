# nodeforge/plan/ — Plan Data Models and Renderers

This package defines the central `Plan` and `Step` data structures that all downstream modules consume, plus renderers that produce human-readable output from plans.

---

## Files

| File | Purpose |
|---|---|
| `models.py` | Pydantic models: `Plan`, `Step`, `StepScope` enum, `StepKind` open constants |
| `render_text.py` | Rich console table output for `nodeforge plan` |
| `render_markdown.py` | Jinja2-based Markdown rendering for `nodeforge docs` |
| `__init__.py` | Empty package marker |

---

## Data Models (`models.py`)

### `Step`

A single unit of work in the execution plan:

| Field | Type | Purpose |
|---|---|---|
| `id` | `str` | Unique identifier (e.g., `create_admin_user`, `verify_admin_login`) |
| `index` | `int` | Execution order (assigned by `planner.plan()`) |
| `description` | `str` | Human-readable description |
| `scope` | `StepScope` | `remote`, `local`, or `verify` |
| `kind` | `str` | Step execution type (open string, not a closed enum) |
| `command` | `str?` | Shell command for SSH/local execution |
| `file_content` | `str?` | Content for file writes/uploads |
| `target_path` | `str?` | Destination path for file operations |
| `sudo` | `bool` | Execute with sudo |
| `depends_on` | `list[int]` | Step indices that must succeed first |
| `gate` | `bool` | If True, failure aborts the entire plan |
| `tags` | `list[str]` | Categorization tags |

### `StepScope` (enum)

- `REMOTE` — executed on the target host via SSH
- `LOCAL` — executed on the operator's machine
- `VERIFY` — verification step (gates, health checks)

### `StepKind` (open constants)

Not a closed enum — addons can register arbitrary kind strings:

- `ssh_command`, `ssh_upload` — remote execution
- `local_command`, `local_file_write`, `local_db_write` — local operations
- `verify` — non-gate verification
- `gate` — must-pass verification (SSH lockout prevention)

### `Plan`

The top-level container:

- `spec_name`, `spec_kind`, `target_host` — metadata
- `spec_hash`, `plan_hash` — integrity hashes for change detection
- `steps` — ordered list of `Step` objects
- `created_at` — ISO timestamp
- Helper methods: `remote_steps()`, `local_steps()`, `gates()`

---

## Text Renderer (`render_text.py`)

`render_plan(plan, console=None)` — renders a Rich console table for the `nodeforge plan` command:

- Summary panel (spec name, target, step counts, hash)
- Steps table with columns: index, ID, description, scope (colour-coded), kind, gate flag, dependencies

---

## Markdown Renderer (`render_markdown.py`)

`render_markdown(plan, mode="guide") -> str` — renders plan as Markdown via Jinja2 templates:

- **`guide` mode** — full runbook with section headings, code blocks for every command, gate warnings, recovery notes
- **`commands` mode** — compact list of just the commands

Templates are stored as inline string constants — no external `.j2` files needed.

---

## Design Decisions

- **Plan is the single source of truth**: the same `Plan` object produces both documentation and execution.
- **`StepKind` is an open string, not a closed Enum**: this allows addons to register new step kinds (e.g., `compose_up`) without modifying core code.
- **Preflight steps use `ssh_command`, not `verify`**: preflight connection checks must actually execute over SSH to trigger the executor's step-0 abort logic. Using `verify` kind would hit the `startswith("echo ")` short-circuit in `_execute_verify`, returning synthetic success without testing connectivity.
- **Inline Jinja2 templates**: avoids filesystem dependencies for the Markdown renderer.
