"""Phase 3: Convert normalized spec into an ordered Plan.

CRITICAL INVARIANT (SSH lockout prevention):
  Steps 'disable_root_login' and 'disable_password_auth' MUST have
  depends_on referencing the index of 'verify_admin_login_on_new_port'.
  'verify_admin_login_on_new_port' MUST be gate=True.
  Local steps MUST only be generated after all critical remote steps.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from nodeforge.compiler.normalizer import NormalizedContext
from nodeforge.plan.models import Plan, Step, StepKind, StepScope
from nodeforge.specs.bootstrap_schema import BootstrapSpec
from nodeforge.specs.service_schema import ServiceSpec
from nodeforge.utils.hashing import sha256_string

AnySpec = Union[BootstrapSpec, ServiceSpec]


def plan(ctx: NormalizedContext) -> Plan:
    """Convert a NormalizedContext into an executable Plan."""
    spec = ctx.spec
    if isinstance(spec, BootstrapSpec):
        steps = _plan_bootstrap(spec, ctx)
    else:
        steps = _plan_service(spec, ctx)

    # Re-index all steps
    for i, step in enumerate(steps):
        step.index = i

    spec_hash = sha256_string(spec.model_dump_json())
    plan_obj = Plan(
        spec_name=spec.meta.name,
        spec_kind=spec.kind,
        target_host=spec.host.address,
        spec_hash=spec_hash,
        plan_hash="",
        steps=steps,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    plan_obj.plan_hash = sha256_string(
        "".join(s.id + (s.command or "") for s in steps)
    )
    return plan_obj


def _s(
    id: str,
    description: str,
    scope: StepScope,
    kind: StepKind,
    *,
    command: str | None = None,
    file_content: str | None = None,
    target_path: str | None = None,
    sudo: bool = False,
    check_command: str | None = None,
    rollback_hint: str | None = None,
    depends_on: list[int] | None = None,
    gate: bool = False,
    tags: list[str] | None = None,
) -> Step:
    """Helper to construct a Step with index placeholder (set later)."""
    return Step(
        id=id,
        index=0,  # filled in by plan()
        description=description,
        scope=scope,
        kind=kind,
        command=command,
        file_content=file_content,
        target_path=target_path,
        sudo=sudo,
        check_command=check_command,
        rollback_hint=rollback_hint,
        depends_on=depends_on or [],
        gate=gate,
        tags=tags or [],
    )


def _plan_bootstrap(spec: BootstrapSpec, ctx: NormalizedContext) -> list[Step]:
    from nodeforge.runtime.steps import bootstrap as bs
    from nodeforge.runtime.steps import wireguard as wg

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    pubkey_content = "\n".join(ctx.pubkey_contents) if ctx.pubkey_contents else ""

    # ------------------------------------------------------------------ #
    # REMOTE: critical bootstrap path
    # ------------------------------------------------------------------ #

    # 0: preflight — verify root SSH access
    steps.append(_s(
        "preflight_connect_root",
        f"Verify root SSH access to {spec.host.address}:{spec.login.port}",
        R, StepKind.VERIFY,
        command=f"echo 'preflight ok'",
        rollback_hint="Check SSH credentials and network connectivity.",
        tags=["preflight"],
    ))
    idx_preflight = len(steps) - 1

    # 1: detect OS
    steps.append(_s(
        "detect_os",
        "Detect remote OS (assert Debian/Ubuntu)",
        R, StepKind.SSH_COMMAND,
        command="cat /etc/os-release",
        depends_on=[idx_preflight],
        tags=["os"],
    ))

    # 2: install base packages
    base_packages = ["ufw"]
    if spec.wireguard.enabled:
        base_packages.append("wireguard")
    pkg_list = " ".join(base_packages)
    steps.append(_s(
        "install_base_packages",
        f"apt update + install base packages: {pkg_list}",
        R, StepKind.SSH_COMMAND,
        command=bs.install_packages(base_packages),
        sudo=True,
        rollback_hint="Check apt sources and network connectivity.",
        tags=["packages"],
    ))

    # 3: create admin user (idempotent)
    steps.append(_s(
        "create_admin_user",
        f"Create admin user '{spec.admin_user.name}' with sudo",
        R, StepKind.SSH_COMMAND,
        command=bs.create_admin_user(
            spec.admin_user.name,
            spec.admin_user.groups,
        ),
        sudo=True,
        tags=["user"],
    ))

    # 4: install authorized keys
    if pubkey_content:
        steps.append(_s(
            "install_authorized_keys",
            f"Install SSH authorized keys for {spec.admin_user.name}",
            R, StepKind.SSH_COMMAND,
            command=bs.install_authorized_keys(spec.admin_user.name, pubkey_content),
            sudo=True,
            tags=["ssh", "keys"],
        ))
    else:
        steps.append(_s(
            "install_authorized_keys",
            f"No pubkeys configured — skipping authorized_keys install",
            R, StepKind.VERIFY,
            command="echo 'no pubkeys configured'",
            tags=["ssh", "keys"],
        ))

    # 4b: ensure PubkeyAuthentication yes + reload sshd
    # Some images (e.g. this VirtualBox Ubuntu) ship with PubkeyAuthentication no.
    # The gate below requires key auth to work, so we must enable it first.
    steps.append(_s(
        "enable_pubkey_auth",
        "Enable PubkeyAuthentication in sshd and reload",
        R, StepKind.SSH_COMMAND,
        command=bs.enable_pubkey_auth(),
        sudo=True,
        tags=["ssh", "sshd"],
    ))

    # 4c: GATE — verify admin login on current port BEFORE touching sshd
    # This is the critical safety gate: if admin key login doesn't work yet,
    # we must NOT change the SSH port — the server would become unrecoverable.
    if pubkey_content:
        idx_pre_gate = len(steps)
        steps.append(_s(
            "verify_admin_login_before_port_change",
            f"[GATE] Verify admin SSH login before port change: "
            f"{spec.admin_user.name}@{spec.host.address}:{spec.login.port}",
            V, StepKind.GATE,
            command=f"ssh_check:{spec.host.address}:{spec.login.port}:{spec.admin_user.name}",
            rollback_hint=(
                "Admin key login failed — SSH port has NOT been changed. "
                "Safe to re-run. Check that admin user and authorized_keys were created correctly."
            ),
            gate=True,
            tags=["gate", "ssh", "lockout-prevention"],
        ))

    # 5: write sshd config candidate (port change, defer root/password disable)
    steps.append(_s(
        "write_sshd_config_candidate",
        f"Configure SSH daemon: port={spec.ssh.port} (root/password hardening deferred)",
        R, StepKind.SSH_COMMAND,
        command=bs.write_sshd_config_candidate(spec.ssh.port),
        sudo=True,
        rollback_hint="Restore /etc/ssh/sshd_config from backup: "
                      "cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config",
        tags=["ssh", "sshd"],
    ))

    # 6: open new SSH port in firewall
    steps.append(_s(
        "open_new_ssh_port_in_firewall",
        f"Open firewall for new SSH port {spec.ssh.port}/tcp",
        R, StepKind.SSH_COMMAND,
        command=bs.open_firewall_port(spec.ssh.port),
        sudo=True,
        tags=["firewall"],
    ))

    # 7: validate sshd config
    steps.append(_s(
        "validate_sshd_config",
        "Validate sshd configuration (sshd -t)",
        R, StepKind.SSH_COMMAND,
        command="sshd -t",
        sudo=True,
        rollback_hint="Fix /etc/ssh/sshd_config errors before reloading.",
        tags=["ssh", "sshd"],
    ))

    # 8: reload sshd
    steps.append(_s(
        "reload_sshd",
        "Reload SSH daemon to apply config",
        R, StepKind.SSH_COMMAND,
        command=bs.reload_sshd(),
        sudo=True,
        rollback_hint="If reload fails, check sshd_config syntax with 'sshd -t'.",
        tags=["ssh", "sshd"],
    ))

    # 9: GATE — verify admin login on new port
    # This is the SSH lockout prevention gate.
    # Steps that disable root login and password auth MUST depend on this index.
    idx_before_gate = len(steps)
    steps.append(_s(
        "verify_admin_login_on_new_port",
        f"[GATE] Verify admin SSH login: {spec.admin_user.name}@{spec.host.address}:{spec.ssh.port}",
        V, StepKind.GATE,
        command=f"ssh_check:{spec.host.address}:{spec.ssh.port}:{spec.admin_user.name}",
        rollback_hint=(
            "Admin login failed. Do NOT disable root login or password auth. "
            f"Restore sshd_config: cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config && "
            f"systemctl reload ssh"
        ),
        gate=True,
        tags=["gate", "ssh", "lockout-prevention"],
    ))
    idx_gate = len(steps) - 1

    # 10: disable root login — MUST depend on gate
    steps.append(_s(
        "disable_root_login",
        "Disable root SSH login (PermitRootLogin no)",
        R, StepKind.SSH_COMMAND,
        command=bs.disable_root_login(),
        sudo=True,
        depends_on=[idx_gate],
        rollback_hint="sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config && systemctl reload ssh",
        tags=["ssh", "hardening", "lockout-prevention"],
    ))

    # 11: disable password auth — MUST depend on gate
    if spec.ssh.disable_password_auth and pubkey_content:
        steps.append(_s(
            "disable_password_auth",
            "Disable SSH password authentication",
            R, StepKind.SSH_COMMAND,
            command=bs.disable_password_auth(),
            sudo=True,
            depends_on=[idx_gate],
            rollback_hint="sed -i 's/^PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config && systemctl reload ssh",
            tags=["ssh", "hardening", "lockout-prevention"],
        ))
    else:
        steps.append(_s(
            "disable_password_auth",
            "Password auth not disabled (no pubkeys or config not set)",
            R, StepKind.VERIFY,
            command="echo 'password auth left enabled'",
            depends_on=[idx_gate],
            tags=["ssh", "hardening"],
        ))

    # 12: finalize firewall
    steps.append(_s(
        "finalize_firewall",
        "Finalize firewall: default deny incoming, enable ufw",
        R, StepKind.SSH_COMMAND,
        command=bs.finalize_firewall(),
        sudo=True,
        tags=["firewall"],
    ))

    # 13: reload sshd again after hardening changes
    steps.append(_s(
        "reload_sshd_final",
        "Reload SSH daemon to apply hardening changes",
        R, StepKind.SSH_COMMAND,
        command=bs.reload_sshd(),
        sudo=True,
        depends_on=[idx_gate],
        tags=["ssh", "sshd"],
    ))

    # 14-16: WireGuard
    if spec.wireguard.enabled:
        wg_conf = wg.generate_wireguard_config(
            interface=spec.wireguard.interface,
            address=spec.wireguard.address,
            private_key=ctx.wireguard_private_key,
            server_public_key=spec.wireguard.server_public_key,
            endpoint=spec.wireguard.endpoint,
            allowed_ips=spec.wireguard.allowed_ips,
            persistent_keepalive=spec.wireguard.persistent_keepalive,
        )
        steps.append(_s(
            "write_wireguard_config",
            f"Write WireGuard config: /etc/wireguard/{spec.wireguard.interface}.conf",
            R, StepKind.SSH_UPLOAD,
            file_content=wg_conf,
            target_path=f"/etc/wireguard/{spec.wireguard.interface}.conf",
            sudo=True,
            tags=["wireguard"],
        ))
        steps.append(_s(
            "enable_wireguard",
            f"Enable and start WireGuard: wg-quick@{spec.wireguard.interface}",
            R, StepKind.SSH_COMMAND,
            command=wg.enable_wireguard(spec.wireguard.interface),
            sudo=True,
            tags=["wireguard"],
        ))
        steps.append(_s(
            "verify_wireguard",
            f"Verify WireGuard interface {spec.wireguard.interface} is up",
            V, StepKind.VERIFY,
            command=f"wg show {spec.wireguard.interface}",
            sudo=True,
            tags=["wireguard"],
        ))

    # 17: postflight checks (from spec)
    for check in spec.checks:
        steps.append(_s(
            f"postflight_{check.type}",
            f"Postflight check: {check.type}",
            V, StepKind.VERIFY,
            command=f"check:{check.type}",
            tags=["postflight", check.type],
        ))

    # ------------------------------------------------------------------ #
    # 18-19: Goss — generate, ship, and run server-spec verification.
    # This is optional but strongly recommended.  If the goss generator
    # raises for any reason the steps are emitted as no-ops so the plan
    # never breaks because of test-tooling issues.
    # ------------------------------------------------------------------ #
    goss_content: str | None = None
    try:
        from nodeforge.addons.goss.generator import generate_goss_yaml
        goss_content = generate_goss_yaml(spec)
    except Exception:
        goss_content = None

    if goss_content is not None:
        idx_ship = len(steps)
        steps.append(_s(
            "ship_goss_file",
            f"Ship goss spec to ~/.goss/{spec.meta.name}.yaml on remote",
            R, StepKind.SSH_UPLOAD,
            file_content=goss_content,
            target_path=f"~/.goss/{spec.meta.name}.yaml",
            sudo=False,
            tags=["goss"],
        ))
        steps.append(_s(
            "run_goss_validate",
            "Run goss validate and display verification results",
            V, StepKind.VERIFY,
            command="goss_validate",
            depends_on=[idx_ship],
            tags=["goss", "verify"],
        ))
    else:
        # Emit a visible warning step so the operator sees it in the plan output
        steps.append(_s(
            "goss_unavailable",
            "[WARNING] No goss spec available — server state will NOT be verified",
            V, StepKind.VERIFY,
            command="goss_unavailable",
            tags=["goss", "warning"],
        ))

    # ------------------------------------------------------------------ #
    # LOCAL: only after remote success
    # ------------------------------------------------------------------ #
    remote_indices = list(range(len(steps)))  # all remote steps must succeed

    # 18: backup local SSH config
    steps.append(_s(
        "backup_local_ssh_config",
        "Backup local ~/.ssh/config",
        L, StepKind.LOCAL_COMMAND,
        command="backup_ssh_config",
        tags=["local", "ssh-config"],
    ))

    # 19: write SSH conf.d entry
    steps.append(_s(
        "write_local_ssh_conf_d",
        f"Write local SSH conf.d entry: {ctx.ssh_conf_d_path}",
        L, StepKind.LOCAL_FILE_WRITE,
        target_path=str(ctx.ssh_conf_d_path) if ctx.ssh_conf_d_path else "",
        tags=["local", "ssh-config"],
    ))

    # 20: ensure Include directive
    steps.append(_s(
        "ensure_include_directive",
        "Ensure Include directive in ~/.ssh/config",
        L, StepKind.LOCAL_COMMAND,
        command="ensure_include",
        tags=["local", "ssh-config"],
    ))

    # 21: init inventory DB
    if spec.local.inventory.enabled:
        steps.append(_s(
            "open_or_init_local_inventory",
            "Open or initialize local SQLCipher inventory database",
            L, StepKind.LOCAL_DB_WRITE,
            command="init_inventory",
            tags=["local", "inventory"],
        ))

        # 22: upsert server record
        steps.append(_s(
            "upsert_server_inventory",
            f"Upsert server record in inventory: {spec.host.name}",
            L, StepKind.LOCAL_DB_WRITE,
            command="upsert_server",
            tags=["local", "inventory"],
        ))

        # 23: record run metadata
        steps.append(_s(
            "record_run_metadata",
            "Record bootstrap run metadata in inventory",
            L, StepKind.LOCAL_DB_WRITE,
            command="record_run",
            tags=["local", "inventory"],
        ))

    return steps


def _plan_service(spec: ServiceSpec, ctx: NormalizedContext) -> list[Step]:
    from nodeforge.runtime.steps import postgres as pg
    from nodeforge.runtime.steps import docker as dk
    from nodeforge.runtime.steps import container as ct

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    # preflight
    steps.append(_s(
        "preflight_connect_admin",
        f"Verify admin SSH access to {spec.host.address}:{spec.login.port}",
        V, StepKind.VERIFY,
        command="echo 'preflight ok'",
        tags=["preflight"],
    ))

    steps.append(_s(
        "detect_os",
        "Detect remote OS",
        R, StepKind.SSH_COMMAND,
        command="cat /etc/os-release",
        tags=["os"],
    ))

    # Postgres
    if spec.postgres and spec.postgres.enabled:
        steps.append(_s(
            "install_postgres",
            f"Install PostgreSQL {spec.postgres.version}",
            R, StepKind.SSH_COMMAND,
            command=pg.install_postgres(spec.postgres.version),
            sudo=True,
            tags=["postgres"],
        ))
        steps.append(_s(
            "configure_postgres_listen",
            f"Configure PostgreSQL listen_addresses",
            R, StepKind.SSH_COMMAND,
            command=pg.configure_listen(spec.postgres.listen_addresses),
            sudo=True,
            tags=["postgres"],
        ))
        steps.append(_s(
            "enable_postgres",
            "Enable and start PostgreSQL service",
            R, StepKind.SSH_COMMAND,
            command=pg.enable_postgres(),
            sudo=True,
            tags=["postgres"],
        ))
        if spec.postgres.create_role:
            steps.append(_s(
                "create_db_role",
                f"Create PostgreSQL role: {spec.postgres.create_role.name}",
                R, StepKind.SSH_COMMAND,
                command=pg.create_role(
                    spec.postgres.create_role.name,
                    spec.postgres.create_role.password_env,
                ),
                sudo=True,
                tags=["postgres"],
            ))
        if spec.postgres.create_database:
            steps.append(_s(
                "create_database",
                f"Create PostgreSQL database: {spec.postgres.create_database.name}",
                R, StepKind.SSH_COMMAND,
                command=pg.create_database(
                    spec.postgres.create_database.name,
                    spec.postgres.create_database.owner,
                ),
                sudo=True,
                tags=["postgres"],
            ))
        steps.append(_s(
            "postgres_ready_check",
            "Verify PostgreSQL is ready",
            V, StepKind.VERIFY,
            command="pg_isready",
            tags=["postgres", "verify"],
        ))

    # Docker
    needs_docker = spec.docker and spec.docker.enabled or bool(spec.containers)
    if needs_docker:
        steps.append(_s(
            "install_docker",
            "Install Docker",
            R, StepKind.SSH_COMMAND,
            command=dk.install_docker(),
            sudo=True,
            tags=["docker"],
        ))
        steps.append(_s(
            "enable_docker",
            "Enable Docker service",
            R, StepKind.SSH_COMMAND,
            command=dk.enable_docker(),
            sudo=True,
            tags=["docker"],
        ))
        steps.append(_s(
            "docker_version_check",
            "Verify Docker installation",
            V, StepKind.VERIFY,
            command="docker --version",
            tags=["docker", "verify"],
        ))

    # Containers
    for c in spec.containers:
        steps.append(_s(
            f"pull_image_{c.name}",
            f"Pull container image: {c.image}",
            R, StepKind.SSH_COMMAND,
            command=ct.pull_image(c.image),
            tags=["container", c.name],
        ))
        steps.append(_s(
            f"stop_container_{c.name}",
            f"Stop existing container '{c.name}' (if running)",
            R, StepKind.SSH_COMMAND,
            command=ct.stop_container(c.name),
            tags=["container", c.name],
        ))
        steps.append(_s(
            f"remove_container_{c.name}",
            f"Remove existing container '{c.name}' (if present)",
            R, StepKind.SSH_COMMAND,
            command=ct.remove_container(c.name),
            tags=["container", c.name],
        ))
        steps.append(_s(
            f"run_container_{c.name}",
            f"Start container '{c.name}' from {c.image}",
            R, StepKind.SSH_COMMAND,
            command=ct.run_container(c),
            tags=["container", c.name],
        ))
        steps.append(_s(
            f"container_running_check_{c.name}",
            f"Verify container '{c.name}' is running",
            V, StepKind.VERIFY,
            command=f"docker inspect --format='{{{{.State.Running}}}}' {c.name}",
            tags=["container", c.name, "verify"],
        ))
        if c.healthcheck:
            steps.append(_s(
                f"http_health_check_{c.name}",
                f"HTTP health check: {c.healthcheck.url}",
                V, StepKind.VERIFY,
                command=f"http_check:{c.healthcheck.url}:{c.healthcheck.expect_status}",
                tags=["container", c.name, "health"],
            ))

    # Local inventory
    if spec.local.inventory.enabled:
        steps.append(_s(
            "open_or_init_local_inventory",
            "Open or initialize local SQLCipher inventory database",
            L, StepKind.LOCAL_DB_WRITE,
            command="init_inventory",
            tags=["local", "inventory"],
        ))
        steps.append(_s(
            "update_server_services_metadata",
            f"Update service metadata in inventory for {spec.host.name}",
            L, StepKind.LOCAL_DB_WRITE,
            command="upsert_services",
            tags=["local", "inventory"],
        ))
        steps.append(_s(
            "record_service_run_metadata",
            "Record service run metadata in inventory",
            L, StepKind.LOCAL_DB_WRITE,
            command="record_run",
            tags=["local", "inventory"],
        ))

    return steps
