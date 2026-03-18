# nodeforge/utils/ — File and Path Utilities

This package provides shared utility functions used across the nodeforge codebase, primarily for path resolution and file operations.

---

## Files

| File | Purpose |
|---|---|
| `files.py` | Path resolution, directory creation, safe file reading |
| `hashing.py` | SHA-256 string hashing (used for spec_hash and plan_hash computation) |
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

## Design Decisions

- **Spec-relative resolution**: relative paths are resolved against the spec directory first, making specs portable across different working directories.
- **Safe file reading**: `read_text_safe()` returns `None` instead of raising, reducing try/except boilerplate in callers.
- **Explicit permissions**: `ensure_dir()` sets mode after creation because `mkdir(mode=...)` is affected by umask.
