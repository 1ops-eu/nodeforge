"""Shell command builders for kind: compose_project steps.

IMPORTANT — Fabric sudo() compatibility:
  See bootstrap.py module docstring for details.  Functions here follow
  the same pattern: no shell operators in command strings that will be
  executed via Fabric's sudo().

  Commands that require shell operators (e.g. cd + docker compose) are
  wrapped in bash -c '...' so Fabric elevates the outer bash process.
"""

from __future__ import annotations


def mkdir_with_permissions(path: str, mode: str, owner: str, group: str) -> str:
    """Create a directory with specific mode and ownership.

    Uses bash -c to chain mkdir + chmod + chown under a single sudo elevation.
    """
    return f"bash -c 'mkdir -p {path} && chmod {mode} {path} && chown {owner}:{group} {path}'"


def compose_config(directory: str, compose_file: str, project_name: str) -> str:
    """Validate compose file syntax (docker compose config)."""
    return (
        f"bash -c 'cd {directory} && "
        f"docker compose -f {compose_file} -p {project_name} config --quiet'"
    )


def compose_pull(directory: str, compose_file: str, project_name: str) -> str:
    """Pull images defined in compose file."""
    return f"bash -c 'cd {directory} && docker compose -f {compose_file} -p {project_name} pull'"


def compose_up(directory: str, compose_file: str, project_name: str) -> str:
    """Start compose project in detached mode."""
    return f"bash -c 'cd {directory} && docker compose -f {compose_file} -p {project_name} up -d'"


def compose_down(directory: str, compose_file: str, project_name: str) -> str:
    """Stop and remove compose project containers."""
    return f"bash -c 'cd {directory} && docker compose -f {compose_file} -p {project_name} down'"
