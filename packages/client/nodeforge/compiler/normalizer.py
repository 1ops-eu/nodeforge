"""Phase 2: Fill defaults and resolve computed values from spec."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path

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
from nodeforge_core.utils.files import expand_path, resolve_path

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
class NormalizedContext:
    """Resolved values derived from the spec during normalization."""

    spec: AnySpec
    spec_dir: Path | None = (
        None  # directory containing the spec file; used for relative path resolution
    )

    # Template rendering results (file_template and compose_project)
    rendered_templates: dict[str, str] = field(default_factory=dict)  # dest -> rendered content
    template_hashes: dict[str, str] = field(default_factory=dict)  # dest -> sha256 of content
    compose_file_content: str = ""  # raw or rendered compose file content

    # Bootstrap-specific resolved values
    pubkey_contents: list[str] = field(default_factory=list)
    wireguard_private_key: str = ""
    wireguard_public_key: str = ""  # derived via PyNaCl from server private key
    wireguard_conf_content: str = ""  # server config; populated by planner, used by executor
    wg_client_private_key: str = ""  # auto-generated client Curve25519 private key
    wg_client_public_key: str = ""  # derived via PyNaCl from client private key
    wg_client_conf_content: str = ""  # client wg-quick config; populated by planner, saved locally
    ssh_conf_d_path: Path | None = None
    db_path: Path | None = None
    login_key_path: Path | None = None
    login_password: str | None = None
    admin_key_path: Path | None = None


def normalize(spec, spec_dir: Path | None = None) -> NormalizedContext:
    """Resolve all paths, read key files, compute derived values.

    Args:
        spec: Parsed spec object.
        spec_dir: Directory of the spec file. Relative paths in the spec are
            resolved against this directory first. Falls back to CWD if None.
    """
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge_core.registry import get_normalizer, load_addons

    load_addons()

    if isinstance(spec, list):
        # Multi-document: normalize each spec independently, return list of contexts
        return [normalize(s, spec_dir=spec_dir) for s in spec]

    ctx = NormalizedContext(spec=spec, spec_dir=spec_dir)

    normalizer = get_normalizer(spec.kind)
    if normalizer is None:
        raise RuntimeError(f"No normalizer registered for spec kind '{spec.kind}'")
    normalizer(spec, ctx)

    return ctx


def _generate_wg_private_key() -> str:
    """Generate a fresh Curve25519 private key encoded as WireGuard base64."""
    import nacl.public

    priv = nacl.public.PrivateKey.generate()
    return base64.b64encode(bytes(priv)).decode()


def _derive_wg_public_key(private_key_b64: str) -> str:
    """Derive a WireGuard public key from a base64 Curve25519 private key.

    Uses PyNaCl (libsodium) which is already a transitive dependency via
    Fabric/Paramiko and is now an explicit dependency in pyproject.toml.
    Returns an empty string if the key is invalid or PyNaCl is unavailable.
    """
    try:
        import nacl.public

        key_bytes = base64.b64decode(private_key_b64)
        priv = nacl.public.PrivateKey(key_bytes)
        return base64.b64encode(bytes(priv.public_key)).decode()
    except Exception:
        return ""


def _apply_state_dir(spec) -> None:
    """Apply state_dir override from env var or spec field.

    Priority (highest to lowest):
    1. NODEFORGE_STATE_DIR environment variable
    2. local.state_dir spec field
    3. Built-in defaults (no action needed)

    When a state_dir is active, re-registers LocalPathsConfig so all
    downstream code (ssh_config, wireguard_store, etc.) picks it up.
    """
    from nodeforge_core.registry.local_paths import LocalPathsConfig, register_local_paths

    env_state_dir = os.environ.get("NODEFORGE_STATE_DIR")
    spec_state_dir = spec.local.state_dir if spec.local.state_dir else None

    effective = env_state_dir or spec_state_dir
    if effective:
        register_local_paths(LocalPathsConfig(state_dir=Path(effective)))


def _resolve_db_path(spec) -> Path:
    """Resolve inventory database path respecting the priority order.

    Priority (highest to lowest):
    1. Explicit spec field (local.inventory.db_path) if non-default
    2. state_dir-derived path (via get_local_paths())
    3. Built-in default (~/.nodeforge/inventory.db)
    """
    from nodeforge_core.registry.local_paths import get_local_paths

    inv = spec.local.inventory
    default_db = "~/.nodeforge/inventory.db"
    if inv.db_path and inv.db_path != default_db:
        # Explicit per-resource override in spec
        return expand_path(inv.db_path)
    # Use the centrally-resolved path (state_dir-aware)
    return get_local_paths().inventory_db_path


def _normalize_bootstrap(spec: BootstrapSpec, ctx: NormalizedContext) -> None:
    spec_dir = ctx.spec_dir

    # Apply state_dir override before resolving any local paths
    _apply_state_dir(spec)

    # Resolve login private key path
    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    # Derive admin private key path from the first .pub entry in pubkeys
    for pk_str in spec.admin_user.pubkeys:
        pk_path = resolve_path(pk_str, spec_dir)
        if pk_path.suffix == ".pub":
            candidate = pk_path.with_suffix("")
            if candidate.exists():
                ctx.admin_key_path = candidate
                break

    # Read pubkey file contents (missing files are stored as placeholder for plan/docs)
    for pk_path_str in spec.admin_user.pubkeys:
        pk_path = resolve_path(pk_path_str, spec_dir)
        if pk_path.exists():
            ctx.pubkey_contents.append(pk_path.read_text(encoding="utf-8").strip())
        else:
            ctx.pubkey_contents.append(f"<key not found: {pk_path}>")

    # Read WireGuard server private key and derive public key via PyNaCl (Curve25519).
    # When private_key_file is omitted, the key is auto-generated using write-once
    # semantics: reuse from local state if it exists, otherwise generate a fresh key.
    # The key is persisted by save_wireguard_state after a successful apply.
    if spec.wireguard.enabled:
        if spec.wireguard.private_key_file:
            wg_key_path = resolve_path(spec.wireguard.private_key_file, spec_dir)
            if wg_key_path.exists():
                ctx.wireguard_private_key = wg_key_path.read_text(encoding="utf-8").strip()
                ctx.wireguard_public_key = _derive_wg_public_key(ctx.wireguard_private_key)
            else:
                ctx.wireguard_private_key = f"<key not found: {wg_key_path}>"
                ctx.wireguard_public_key = ""
        else:
            # Auto-generate: reuse persisted key or generate fresh (write-once)
            from nodeforge_core.registry.local_paths import get_local_paths

            server_key_path = (
                get_local_paths().wg_state_base / spec.host.name / "private.key"
            )
            if server_key_path.exists():
                ctx.wireguard_private_key = server_key_path.read_text(
                    encoding="utf-8"
                ).strip()
            else:
                ctx.wireguard_private_key = _generate_wg_private_key()
            ctx.wireguard_public_key = _derive_wg_public_key(ctx.wireguard_private_key)

    # Auto-generate (or reuse) WireGuard client key pair.
    # The client private key is persisted to ~/.wg/nodeforge/{host}/client.key after
    # a successful apply so that re-runs reuse the same key (stable peer identity).
    # On first run the file won't exist yet — we generate it in memory here and the
    # executor's save_wireguard_state step writes it to disk.
    if spec.wireguard.enabled:
        from nodeforge_core.registry.local_paths import get_local_paths

        client_key_path = get_local_paths().wg_state_base / spec.host.name / "client.key"
        if client_key_path.exists():
            ctx.wg_client_private_key = client_key_path.read_text(encoding="utf-8").strip()
        else:
            ctx.wg_client_private_key = _generate_wg_private_key()
        ctx.wg_client_public_key = _derive_wg_public_key(ctx.wg_client_private_key)

    # Compute SSH conf.d path   using the addon-overridable base directory
    from nodeforge_core.registry.local_paths import get_local_paths

    ssh_conf_d_base = get_local_paths().ssh_conf_d_base
    ctx.ssh_conf_d_path = ssh_conf_d_base / f"{spec.host.name}.conf"

    # If host_alias not set, default to host name
    if not spec.local.ssh_config.host_alias:
        spec.local.ssh_config.host_alias = spec.host.name

    # Resolve inventory db path (state_dir-aware)
    ctx.db_path = _resolve_db_path(spec)


def _normalize_service(spec: ServiceSpec, ctx: NormalizedContext) -> None:
    spec_dir = ctx.spec_dir

    # Apply state_dir override before resolving any local paths
    _apply_state_dir(spec)

    # Resolve login key
    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    # Resolve inventory (state_dir-aware)
    ctx.db_path = _resolve_db_path(spec)

    # Resolve postgres role password from env
    if spec.postgres and spec.postgres.create_role:
        role = spec.postgres.create_role
        if role.password_env:
            pw = os.environ.get(role.password_env, "")
            role.password_env = pw  # store resolved value


def _normalize_file_template(spec: FileTemplateSpec, ctx: NormalizedContext) -> None:
    """Normalize a file_template spec: resolve paths, render templates at plan time."""
    from nodeforge_core.utils.templates import content_hash, render_template_file

    spec_dir = ctx.spec_dir

    # Apply state_dir override before resolving any local paths
    _apply_state_dir(spec)

    # Resolve login key
    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    # Resolve inventory (state_dir-aware)
    ctx.db_path = _resolve_db_path(spec)

    # Render all templates with Jinja2 and store results on ctx
    for t in spec.templates:
        src_path = resolve_path(t.src, spec_dir)
        rendered = render_template_file(src_path, spec.variables)
        ctx.rendered_templates[t.dest] = rendered
        ctx.template_hashes[t.dest] = content_hash(rendered)


def _normalize_compose_project(spec: ComposeProjectSpec, ctx: NormalizedContext) -> None:
    """Normalize a compose_project spec: resolve paths, render templates, read compose file."""
    from nodeforge_core.utils.templates import content_hash, render_template_file

    spec_dir = ctx.spec_dir
    p = spec.project

    # Apply state_dir override before resolving any local paths
    _apply_state_dir(spec)

    # Resolve login key
    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    # Resolve inventory (state_dir-aware)
    ctx.db_path = _resolve_db_path(spec)

    # Render project templates (Jinja2)
    for t in p.templates:
        src_path = resolve_path(t.src, spec_dir)
        rendered = render_template_file(src_path, p.variables)
        # dest is relative to project directory — store with full remote path as key
        if t.dest.startswith("/"):
            full_dest = t.dest
        else:
            full_dest = f"{p.directory}/{t.dest}"
        ctx.rendered_templates[full_dest] = rendered
        ctx.template_hashes[full_dest] = content_hash(rendered)

    # Read the compose file (static, not rendered through Jinja2)
    compose_path = resolve_path(p.compose_file, spec_dir)
    if compose_path.exists():
        ctx.compose_file_content = compose_path.read_text(encoding="utf-8")
    else:
        ctx.compose_file_content = f"<compose file not found: {compose_path}>"


def _normalize_postgres_ensure(spec: PostgresEnsureSpec, ctx: NormalizedContext) -> None:
    """Normalize a postgres_ensure spec: resolve login, paths, passwords."""
    spec_dir = ctx.spec_dir

    _apply_state_dir(spec)

    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    ctx.db_path = _resolve_db_path(spec)

    # Resolve password_env for each user
    for user in spec.users:
        if user.password_env:
            pw = os.environ.get(user.password_env, "")
            user.password_env = pw  # store resolved value


def _normalize_backup_job(spec: BackupJobSpec, ctx: NormalizedContext) -> None:
    """Normalize a backup_job spec: resolve login, paths, state_dir."""
    spec_dir = ctx.spec_dir

    _apply_state_dir(spec)

    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    ctx.db_path = _resolve_db_path(spec)


def _normalize_systemd_unit(spec: SystemdUnitSpec, ctx: NormalizedContext) -> None:
    """Normalize a systemd_unit spec: resolve login, paths, state_dir."""
    spec_dir = ctx.spec_dir

    _apply_state_dir(spec)

    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    ctx.db_path = _resolve_db_path(spec)


def _normalize_systemd_timer(spec: SystemdTimerSpec, ctx: NormalizedContext) -> None:
    """Normalize a systemd_timer spec: resolve login, paths, state_dir."""
    spec_dir = ctx.spec_dir

    _apply_state_dir(spec)

    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    ctx.db_path = _resolve_db_path(spec)


def _normalize_http_check(spec: HttpCheckSpec, ctx: NormalizedContext) -> None:
    """Normalize an http_check spec: resolve login, paths, state_dir."""
    spec_dir = ctx.spec_dir

    # Apply state_dir override before resolving any local paths
    _apply_state_dir(spec)

    # Resolve login key
    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    # Resolve inventory (state_dir-aware)
    ctx.db_path = _resolve_db_path(spec)


def _normalize_stack(spec: StackSpec, ctx: NormalizedContext) -> None:
    """Normalize a stack spec: resolve login, paths, state_dir."""
    spec_dir = ctx.spec_dir

    # Apply state_dir override before resolving any local paths
    _apply_state_dir(spec)

    # Resolve login key
    ctx.login_key_path = (
        resolve_path(spec.login.private_key, spec_dir) if spec.login.private_key else None
    )
    ctx.login_password = spec.login.password or None

    # Resolve inventory (state_dir-aware)
    ctx.db_path = _resolve_db_path(spec)
