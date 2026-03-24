"""Cross-field validation beyond Pydantic schema checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from nodeforge_core.specs.backup_job_schema import BackupJobSpec
from nodeforge_core.specs.bootstrap_schema import BootstrapSpec
from nodeforge_core.specs.compose_project_schema import ComposeProjectSpec
from nodeforge_core.specs.file_template_schema import FileTemplateSpec
from nodeforge_core.specs.http_check_schema import HttpCheckSpec
from nodeforge_core.specs.postgres_ensure_schema import PostgresEnsureSpec
from nodeforge_core.specs.service_schema import ServiceSpec
from nodeforge_core.specs.stack_schema import StackSpec
from nodeforge_core.specs.systemd_timer_schema import SystemdTimerSpec
from nodeforge_core.specs.systemd_unit_schema import SystemdUnitSpec

AnySpec = (
    BootstrapSpec
    | ServiceSpec
    | FileTemplateSpec
    | ComposeProjectSpec
    | StackSpec
    | HttpCheckSpec
    | SystemdUnitSpec
    | SystemdTimerSpec
    | BackupJobSpec
    | PostgresEnsureSpec
)


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


def validate_postgres_ensure(spec: PostgresEnsureSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # Must have at least one declaration
    if not spec.users and not spec.databases and not spec.extensions and not spec.grants:
        issues.append(
            ValidationIssue(
                "error",
                "postgres_ensure",
                "At least one user, database, extension, or grant must be declared",
            )
        )

    # User names must be non-empty and unique
    user_names: set[str] = set()
    for i, u in enumerate(spec.users):
        if not u.name:
            issues.append(
                ValidationIssue("error", f"users[{i}].name", "User name must not be empty")
            )
        if u.name in user_names:
            issues.append(
                ValidationIssue(
                    "error", f"users[{i}].name", f"Duplicate user name: {u.name}"
                )
            )
        user_names.add(u.name)

    # Database names must be non-empty and unique
    db_names: set[str] = set()
    for i, d in enumerate(spec.databases):
        if not d.name:
            issues.append(
                ValidationIssue(
                    "error", f"databases[{i}].name", "Database name must not be empty"
                )
            )
        if d.name in db_names:
            issues.append(
                ValidationIssue(
                    "error", f"databases[{i}].name", f"Duplicate database name: {d.name}"
                )
            )
        db_names.add(d.name)

    # Extension names must be non-empty
    for i, e in enumerate(spec.extensions):
        if not e.name:
            issues.append(
                ValidationIssue(
                    "error", f"extensions[{i}].name", "Extension name must not be empty"
                )
            )
        if not e.database:
            issues.append(
                ValidationIssue(
                    "error",
                    f"extensions[{i}].database",
                    "Extension database must not be empty",
                )
            )

    # Grant fields must be non-empty
    for i, g in enumerate(spec.grants):
        if not g.privilege:
            issues.append(
                ValidationIssue(
                    "error", f"grants[{i}].privilege", "Privilege must not be empty"
                )
            )
        if not g.on_database:
            issues.append(
                ValidationIssue(
                    "error", f"grants[{i}].on_database", "on_database must not be empty"
                )
            )
        if not g.to_user:
            issues.append(
                ValidationIssue(
                    "error", f"grants[{i}].to_user", "to_user must not be empty"
                )
            )

    return issues


def validate_backup_job(spec: BackupJobSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    b = spec.backup

    if not b.name:
        issues.append(
            ValidationIssue("error", "backup.name", "Backup job name must not be empty")
        )

    if not b.destination.path or not b.destination.path.startswith("/"):
        issues.append(
            ValidationIssue(
                "error",
                "backup.destination.path",
                f"Destination path must be an absolute path, got '{b.destination.path}'",
            )
        )

    if b.retention.count < 1:
        issues.append(
            ValidationIssue(
                "error",
                "backup.retention.count",
                f"Retention count must be at least 1, got {b.retention.count}",
            )
        )

    if not b.schedule:
        issues.append(
            ValidationIssue("error", "backup.schedule", "Schedule must not be empty")
        )

    src = b.source
    if src.type == "postgres_dump":
        if not src.database:
            issues.append(
                ValidationIssue(
                    "error",
                    "backup.source.database",
                    "Database name is required for postgres_dump backups",
                )
            )
    elif src.type == "directory":
        if not src.path:
            issues.append(
                ValidationIssue(
                    "error",
                    "backup.source.path",
                    "Source path is required for directory backups",
                )
            )
        elif not src.path.startswith("/"):
            issues.append(
                ValidationIssue(
                    "error",
                    "backup.source.path",
                    f"Source path must be absolute, got '{src.path}'",
                )
            )

    return issues


def validate_systemd_unit(spec: SystemdUnitSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    u = spec.unit

    if not u.unit_name:
        issues.append(
            ValidationIssue("error", "unit.unit_name", "Unit name must not be empty")
        )

    if not u.exec_start:
        issues.append(
            ValidationIssue("error", "unit.exec_start", "ExecStart must not be empty")
        )

    valid_restart = ("no", "always", "on-failure", "on-abnormal", "on-abort", "on-success")
    if u.restart not in valid_restart:
        issues.append(
            ValidationIssue(
                "error",
                "unit.restart",
                f"Invalid restart policy '{u.restart}'. "
                f"Must be one of: {', '.join(valid_restart)}",
            )
        )

    valid_types = ("simple", "forking", "oneshot", "notify", "dbus", "idle")
    if u.type not in valid_types:
        issues.append(
            ValidationIssue(
                "error",
                "unit.type",
                f"Invalid service type '{u.type}'. "
                f"Must be one of: {', '.join(valid_types)}",
            )
        )

    if u.restart_sec < 0:
        issues.append(
            ValidationIssue(
                "error",
                "unit.restart_sec",
                f"RestartSec must be non-negative, got {u.restart_sec}",
            )
        )

    # Logrotate validation
    lr = spec.logrotate
    if lr and lr.enabled:
        if not lr.path:
            issues.append(
                ValidationIssue(
                    "error",
                    "logrotate.path",
                    "Logrotate path must not be empty when enabled",
                )
            )
        valid_freq = ("daily", "weekly", "monthly")
        if lr.frequency not in valid_freq:
            issues.append(
                ValidationIssue(
                    "error",
                    "logrotate.frequency",
                    f"Invalid frequency '{lr.frequency}'. "
                    f"Must be one of: {', '.join(valid_freq)}",
                )
            )
        if lr.rotate < 1:
            issues.append(
                ValidationIssue(
                    "error",
                    "logrotate.rotate",
                    f"Rotate count must be at least 1, got {lr.rotate}",
                )
            )

    return issues


def validate_systemd_timer(spec: SystemdTimerSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    t = spec.timer
    s = spec.service

    if not t.timer_name:
        issues.append(
            ValidationIssue("error", "timer.timer_name", "Timer name must not be empty")
        )

    if not t.on_calendar:
        issues.append(
            ValidationIssue("error", "timer.on_calendar", "OnCalendar must not be empty")
        )

    if not s.exec_start:
        issues.append(
            ValidationIssue("error", "service.exec_start", "ExecStart must not be empty")
        )

    return issues


def validate_http_check(spec: HttpCheckSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    c = spec.check

    if not c.url:
        issues.append(
            ValidationIssue("error", "check.url", "URL must not be empty")
        )
    elif not c.url.startswith(("http://", "https://")):
        issues.append(
            ValidationIssue(
                "error",
                "check.url",
                f"URL must start with http:// or https://, got '{c.url}'",
            )
        )

    if not (100 <= c.expected_status <= 599):
        issues.append(
            ValidationIssue(
                "error",
                "check.expected_status",
                f"Expected status must be 100-599, got {c.expected_status}",
            )
        )

    if c.retries < 1:
        issues.append(
            ValidationIssue(
                "error",
                "check.retries",
                f"Retries must be at least 1, got {c.retries}",
            )
        )

    if c.interval < 0:
        issues.append(
            ValidationIssue(
                "error",
                "check.interval",
                f"Interval must be non-negative, got {c.interval}",
            )
        )

    if c.timeout <= 0:
        issues.append(
            ValidationIssue(
                "error",
                "check.timeout",
                f"Timeout must be positive, got {c.timeout}",
            )
        )

    return issues


def validate_stack(spec: StackSpec) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # Must have at least one resource
    if not spec.resources:
        issues.append(
            ValidationIssue(
                "error",
                "resources",
                "Stack must contain at least one resource",
            )
        )

    # Resource names must be unique
    names: set[str] = set()
    for i, res in enumerate(spec.resources):
        if not res.name:
            issues.append(
                ValidationIssue(
                    "error",
                    f"resources[{i}].name",
                    "Resource name must not be empty",
                )
            )
        if res.name in names:
            issues.append(
                ValidationIssue(
                    "error",
                    f"resources[{i}].name",
                    f"Duplicate resource name: {res.name}",
                )
            )
        names.add(res.name)

        # Check that referenced kinds are registered
        from nodeforge_core.registry import get_spec_model, list_spec_kinds

        if get_spec_model(res.kind) is None:
            known = ", ".join(list_spec_kinds()) or "none"
            issues.append(
                ValidationIssue(
                    "error",
                    f"resources[{i}].kind",
                    f"Unknown resource kind '{res.kind}'. Supported: {known}",
                )
            )

        # Check depends_on references exist
        for dep in res.depends_on:
            if dep not in names and dep != res.name:
                # dep might refer to a resource defined later — defer full check
                pass

    # Full circular dependency check (topological sort)
    name_set = {r.name for r in spec.resources}
    for i, res in enumerate(spec.resources):
        for dep in res.depends_on:
            if dep not in name_set:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"resources[{i}].depends_on",
                        f"Dependency '{dep}' not found in stack resources",
                    )
                )

    # Detect cycles using DFS
    adj: dict[str, list[str]] = {r.name: list(r.depends_on) for r in spec.resources}
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _has_cycle(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in adj.get(node, []):
            if _has_cycle(dep):
                return True
        in_stack.discard(node)
        return False

    for name in adj:
        if _has_cycle(name):
            issues.append(
                ValidationIssue(
                    "error",
                    "resources",
                    "Circular dependency detected in stack resources",
                )
            )
            break

    return issues


def validate_spec(spec) -> list[ValidationIssue]:
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge_core.registry import get_validator, load_addons

    load_addons()

    if isinstance(spec, list):
        issues = []
        for s in spec:
            issues.extend(validate_spec(s))
        return issues

    validator = get_validator(spec.kind)
    if validator is None:
        return [
            ValidationIssue("error", "kind", f"No validator registered for spec kind '{spec.kind}'")
        ]
    return validator(spec)


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
