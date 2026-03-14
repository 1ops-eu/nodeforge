from pathlib import Path


def expand_path(p: str) -> Path:
    """Expand ~ and resolve to absolute path."""
    return Path(p).expanduser().resolve()


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
