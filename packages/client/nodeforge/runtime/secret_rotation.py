"""Secret rotation: find secret references in specs and rotate them."""

from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass, field


@dataclass
class SecretRef:
    """A reference to a secret (environment variable) found in a spec."""

    env_var: str
    kind: str  # spec kind where found
    field_path: str  # e.g. "users[0].password_env"


@dataclass
class RotationResult:
    """Result of a secret rotation operation."""

    secret_name: str
    new_value: str
    refs_found: list[SecretRef] = field(default_factory=list)
    applied: bool = False
    error: str | None = None


def find_secret_refs(spec) -> list[SecretRef]:
    """Scan a parsed spec for password_env references."""
    refs: list[SecretRef] = []
    kind = spec.kind

    # service spec: postgres.roles[].password_env
    if hasattr(spec, "postgres") and spec.postgres:
        pg = spec.postgres
        if hasattr(pg, "roles"):
            for i, role in enumerate(pg.roles):
                if role.password_env:
                    refs.append(SecretRef(
                        env_var=role.password_env,
                        kind=kind,
                        field_path=f"postgres.roles[{i}].password_env",
                    ))

    # postgres_ensure spec: users[].password_env
    if hasattr(spec, "users"):
        for i, user in enumerate(spec.users):
            if hasattr(user, "password_env") and user.password_env:
                refs.append(SecretRef(
                    env_var=user.password_env,
                    kind=kind,
                    field_path=f"users[{i}].password_env",
                ))

    return refs


def generate_password(length: int = 32) -> str:
    """Generate a cryptographically secure random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def rotate_secret(
    spec,
    secret_name: str,
    new_value: str | None = None,
) -> RotationResult:
    """Rotate a secret by name.

    Finds all references to the given env var in the spec,
    sets the env var to the new value, and returns a result
    indicating what was found.
    """
    refs = find_secret_refs(spec)
    matching = [r for r in refs if r.env_var == secret_name]

    if not matching:
        return RotationResult(
            secret_name=secret_name,
            new_value="",
            error=f"No references to '{secret_name}' found in spec",
        )

    value = new_value or generate_password()
    os.environ[secret_name] = value

    return RotationResult(
        secret_name=secret_name,
        new_value=value,
        refs_found=matching,
    )
