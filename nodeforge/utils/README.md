# nodeforge/utils/ — File, Path, and Template Utilities

This package provides shared utility functions used across the nodeforge codebase, primarily for path resolution, file operations, and Jinja2 template rendering.

---

## Files

| File | Purpose |
|---|---|
| `files.py` | Path resolution, directory creation, safe file reading |
| `hashing.py` | SHA-256 string hashing (used for spec_hash and plan_hash computation) |
| `templates.py` | Jinja2 template rendering: file and string rendering with `StrictUndefined`, content hashing for change detection |
| `__init__.py` | Empty package marker |

---

## Path Resolution (`files.py`)

### `expand_path(p: str) -> Path`

Expands `~` and resolves to an absolute path relative to CWD.

### `resolve_path(p: str, base_dir: Path | None = None) -> Path`

Spec-relative path resolution with this priority order:

1. If the path starts with `~` or is absolute: resolve normally (CWD-independent)
2. If `base_dir` is given and the path exists relative to `base_dir`: use that
3. Fall back to CWD-relative resolution

This ensures that relative paths in specs (e.g., `pubkeys: [.secrets/key.pub]`) resolve correctly against the spec file's directory, regardless of where nodeforge is invoked from. The `base_dir` parameter is set to the spec file's parent directory by the normalizer.

### `ensure_dir(p: Path, mode: int = 0o700) -> None`

Creates a directory and its parents if they don't exist, then sets the specified permission mode.

### `read_text_safe(p: Path) -> str | None`

Reads file text, returning `None` if the file does not exist (instead of raising `FileNotFoundError`).

---

## Hashing (`hashing.py`)

### `sha256_string(s: str) -> str`

Returns the hex-encoded SHA-256 hash of a string. Used by the planner to compute `spec_hash` (from the model's JSON dump) and `plan_hash` (from concatenated step IDs and commands) for change detection and audit trails.

---

## Template Rendering (`templates.py`)

Shared Jinja2 rendering used by both `file_template` and `compose_project` specs. Templates are rendered at **plan time** so the rendered content appears in `step.file_content`, making plans fully reviewable and deterministic.

### `render_template_file(template_path: Path, variables: dict) -> str`

Renders a Jinja2 template file with the given variables. The template is loaded from its parent directory so that Jinja2's `include`/`extends` directives work with sibling files.

### `render_template_string(template_str: str, variables: dict) -> str`

Renders a Jinja2 template string (inline content) with the given variables.

### `content_hash(content: str) -> str`

Returns the SHA-256 hash of rendered content. Used for change detection in step IDs.

### Configuration

- **`StrictUndefined`**: any undefined variable in a template raises an error immediately rather than silently inserting an empty string.
- **`keep_trailing_newline=True`**: preserves trailing newlines in template files (important for config files).
- **`autoescape=False`**: templates produce plain text, not HTML.
- **`TemplateRenderError`**: all rendering failures raise this exception with a descriptive message.

---

## Design Decisions

- **Spec-relative resolution**: relative paths are resolved against the spec directory first, making specs portable across different working directories.
- **Safe file reading**: `read_text_safe()` returns `None` instead of raising, reducing try/except boilerplate in callers.
- **Explicit permissions**: `ensure_dir()` sets mode after creation because `mkdir(mode=...)` is affected by umask.
- **Plan-time rendering**: templates are rendered during normalization/planning, not during execution. This ensures the plan contains the exact file content that will be deployed, making it fully reviewable.
- **Strict undefined variables**: using `StrictUndefined` catches typos and missing variables at plan time rather than silently deploying broken config files.
