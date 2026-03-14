import hashlib
from pathlib import Path


def sha256_string(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_string(path.read_text(encoding="utf-8"))
