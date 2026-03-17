from pathlib import Path


def expand_path(p: str) -> Path:
    """Expand ~ and resolve to absolute path (relative to CWD)."""
    return Path(p).expanduser().resolve()


def resolve_path(p: str, base_dir: Path | None = None) -> Path:
    """Expand ~ and resolve a path, preferring spec-relative resolution.

    Resolution order for relative paths:
    1. If the path starts with ~ or is absolute: resolve normally (CWD-independent).
    2. If base_dir is given and the path exists relative to base_dir: use that.
    3. Fall back to CWD-relative resolution (same as expand_path).

    This ensures that `pubkeys: [.secrets/key.pub]` in a spec file resolves
    correctly regardless of the working directory nodeforge is invoked from.
    """
    raw = Path(p)
    if raw.is_absolute() or str(p).startswith("~"):
        return raw.expanduser().resolve()
    if base_dir is not None:
        candidate = (base_dir / raw).resolve()
        if candidate.exists():
            return candidate
    return raw.expanduser().resolve()


def ensure_dir(p: Path, mode: int = 0o700) -> None:
    """Create directory and parents if they don't exist."""
    p.mkdir(parents=True, exist_ok=True)
    p.chmod(mode)


def read_text_safe(p: Path) -> str | None:
    """Read file text, returning None if file does not exist."""
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
