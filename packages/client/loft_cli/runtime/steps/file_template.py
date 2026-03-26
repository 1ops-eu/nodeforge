"""Shell command builders for kind: file_template steps.

IMPORTANT — Fabric sudo() compatibility:
  See bootstrap.py module docstring for details.  Functions here follow
  the same pattern: no shell operators in command strings that will be
  executed via Fabric's sudo().
"""

from __future__ import annotations


def mkdir_for_file(dest: str) -> str:
    """Create the parent directory for a target file."""
    parent = dest.rsplit("/", 1)[0]
    return f"mkdir -p {parent}"


def chmod_file(dest: str, mode: str) -> str:
    """Set file permissions."""
    return f"chmod {mode} {dest}"


def chown_file(dest: str, owner: str, group: str) -> str:
    """Set file ownership."""
    return f"chown {owner}:{group} {dest}"
