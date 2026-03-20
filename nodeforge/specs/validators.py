"""Cross-field validation beyond Pydantic schema checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nodeforge.specs.bootstrap_schema import BootstrapSpec
from nodeforge.specs.compose_project_schema import ComposeProjectSpec
from nodeforge.specs.file_template_schema import FileTemplateSpec
from nodeforge.specs.service_schema import ServiceSpec

AnySpec = BootstrapSpec | ServiceSpec | FileTemplateSpec | ComposeProjectSpec


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

    # Nginx validations
    if spec.nginx and spec.nginx.enabled:
        if not spec.nginx.sites:
            issues.append(
                ValidationIssue(
                    "warning",
                    "nginx.sites",
                    "nginx.enabled=true but no sites defined",
                )
            )
        for i, site in enumerate(spec.nginx.sites):
            if not site.domain:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"nginx.sites[{i}].domain",
                        "Each nginx site requires a domain",
                    )
                )
            if site.ssl and (not site.ssl_certificate or not site.ssl_certificate_key):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"nginx.sites[{i}].ssl",
                        f"Site '{site.domain}' has ssl=true but missing "
                        "ssl_certificate or ssl_certificate_key",
                    )
                )
            if not (1 <= site.listen_port <= 65535):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"nginx.sites[{i}].listen_port",
                        f"Port {site.listen_port} is out of valid range 1-65535",
                    )
                )

    return issues


def validate_file_template(spec: FileTemplateSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # Must have at least one template
    if not spec.templates:
        issues.append(
            ValidationIssue(
                "error",
                "templates",
                "At least one template is required",
            )
        )

    dests: set[str] = set()
    for i, t in enumerate(spec.templates):
        # src must not be empty
        if not t.src:
            issues.append(
                ValidationIssue(
                    "error",
                    f"templates[{i}].src",
                    "Template source path must not be empty",
                )
            )

        # dest must be an absolute path
        if not t.dest or not t.dest.startswith("/"):
            issues.append(
                ValidationIssue(
                    "error",
                    f"templates[{i}].dest",
                    f"Template destination must be an absolute path, got '{t.dest}'",
                )
            )

        # mode must be a valid octal string
        if not re.match(r"^0?[0-7]{3,4}$", t.mode):
            issues.append(
                ValidationIssue(
                    "error",
                    f"templates[{i}].mode",
                    f"Invalid file mode '{t.mode}' — expected octal like '0644'",
                )
            )

        # No duplicate destinations
        if t.dest in dests:
            issues.append(
                ValidationIssue(
                    "error",
                    f"templates[{i}].dest",
                    f"Duplicate destination path: {t.dest}",
                )
            )
        dests.add(t.dest)

    return issues


def validate_compose_project(spec: ComposeProjectSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    p = spec.project

    # Project name must not be empty
    if not p.name:
        issues.append(
            ValidationIssue(
                "error",
                "project.name",
                "Compose project name must not be empty",
            )
        )

    # Project directory must be absolute
    if not p.directory or not p.directory.startswith("/"):
        issues.append(
            ValidationIssue(
                "error",
                "project.directory",
                f"Project directory must be an absolute path, got '{p.directory}'",
            )
        )

    # Template sources must not be empty
    template_dests: set[str] = set()
    for i, t in enumerate(p.templates):
        if not t.src:
            issues.append(
                ValidationIssue(
                    "error",
                    f"project.templates[{i}].src",
                    "Template source path must not be empty",
                )
            )
        if not t.dest:
            issues.append(
                ValidationIssue(
                    "error",
                    f"project.templates[{i}].dest",
                    "Template destination filename must not be empty",
                )
            )
        if t.dest in template_dests:
            issues.append(
                ValidationIssue(
                    "error",
                    f"project.templates[{i}].dest",
                    f"Duplicate template destination: {t.dest}",
                )
            )
        template_dests.add(t.dest)

    # Health check values
    hc = p.healthcheck
    if hc.timeout <= 0:
        issues.append(
            ValidationIssue(
                "error",
                "project.healthcheck.timeout",
                f"Health check timeout must be positive, got {hc.timeout}",
            )
        )
    if hc.interval <= 0:
        issues.append(
            ValidationIssue(
                "error",
                "project.healthcheck.interval",
                f"Health check interval must be positive, got {hc.interval}",
            )
        )

    # Managed directory paths should be relative (not absolute)
    for i, d in enumerate(p.directories):
        if d.path.startswith("/"):
            issues.append(
                ValidationIssue(
                    "warning",
                    f"project.directories[{i}].path",
                    f"Directory path '{d.path}' is absolute — it will be used as-is, "
                    "not relative to project.directory",
                )
            )
        if not re.match(r"^0?[0-7]{3,4}$", d.mode):
            issues.append(
                ValidationIssue(
                    "error",
                    f"project.directories[{i}].mode",
                    f"Invalid directory mode '{d.mode}' — expected octal like '0755'",
                )
            )

    return issues


def validate_spec(spec) -> list[ValidationIssue]:
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge.registry import get_validator, load_addons

    load_addons()

    validator = get_validator(spec.kind)
    if validator is None:
        return [
            ValidationIssue("error", "kind", f"No validator registered for spec kind '{spec.kind}'")
        ]
    return validator(spec)


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
