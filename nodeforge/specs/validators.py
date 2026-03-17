"""Cross-field validation beyond Pydantic schema checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

from nodeforge.specs.bootstrap_schema import BootstrapSpec
from nodeforge.specs.service_schema import ServiceSpec

AnySpec = Union[BootstrapSpec, ServiceSpec]


@dataclass
class ValidationIssue:
    severity: Literal["error", "warning"]
    field: str
    message: str

    def __str__(self) -> str:
        icon = "✗" if self.severity == "error" else "⚠"
        return f"{icon} [{self.severity.upper()}] {self.field}: {self.message}"


def validate_bootstrap(spec: BootstrapSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # SSH port range
    if not (1 <= spec.ssh.port <= 65535):
        issues.append(
            ValidationIssue(
                "error",
                "ssh.port",
                f"Port {spec.ssh.port} is out of valid range 1-65535",
            )
        )

    # disable_password_auth requires at least one pubkey
    if spec.ssh.disable_password_auth and not spec.admin_user.pubkeys:
        issues.append(
            ValidationIssue(
                "error",
                "ssh.disable_password_auth",
                "disable_password_auth=true requires at least one pubkey in admin_user.pubkeys",
            )
        )

    # WireGuard completeness
    wg = spec.wireguard
    if wg.enabled:
        for attr, label in [
            ("private_key_file", "wireguard.private_key_file"),
            ("endpoint", "wireguard.endpoint"),
            ("address", "wireguard.address"),
            ("peer_address", "wireguard.peer_address"),
        ]:
            if not getattr(wg, attr):
                issues.append(
                    ValidationIssue(
                        "error",
                        label,
                        f"wireguard.enabled=true requires {label} to be set",
                    )
                )

    # registered_peers_only requires WireGuard
    if spec.firewall.registered_peers_only and not spec.wireguard.enabled:
        issues.append(
            ValidationIssue(
                "warning",
                "firewall.registered_peers_only",
                "registered_peers_only=true has no effect when wireguard.enabled=false",
            )
        )

    # SSH port should differ from login port
    if spec.ssh.port == spec.login.port:
        issues.append(
            ValidationIssue(
                "warning",
                "ssh.port",
                f"ssh.port ({spec.ssh.port}) is the same as login.port — "
                "consider using a different port for post-bootstrap access",
            )
        )

    # OS family check
    if spec.host.os_family not in ("debian", "ubuntu"):
        issues.append(
            ValidationIssue(
                "warning",
                "host.os_family",
                f"os_family '{spec.host.os_family}' may not be fully supported; "
                "nodeforge V1 targets Debian/Ubuntu",
            )
        )

    return issues


def validate_service(spec: ServiceSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # Postgres role password env
    if spec.postgres and spec.postgres.create_role:
        role = spec.postgres.create_role
        if not role.password_env:
            issues.append(
                ValidationIssue(
                    "warning",
                    "postgres.create_role.password_env",
                    "No password_env set for postgres role — role will be created without password",
                )
            )

    # Container images
    for i, c in enumerate(spec.containers):
        if not c.image:
            issues.append(
                ValidationIssue(
                    "error",
                    f"containers[{i}].image",
                    f"Container '{c.name}' has no image specified",
                )
            )

    # Docker required for containers
    if spec.containers and (spec.docker is None or not spec.docker.enabled):
        issues.append(
            ValidationIssue(
                "warning",
                "docker",
                "Containers are defined but docker.enabled is not set — Docker will be installed",
            )
        )

    return issues


def validate_spec(spec) -> list[ValidationIssue]:
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge.registry import load_addons, get_validator

    load_addons()

    validator = get_validator(spec.kind)
    if validator is None:
        return [
            ValidationIssue(
                "error", "kind", f"No validator registered for spec kind '{spec.kind}'"
            )
        ]
    return validator(spec)


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
