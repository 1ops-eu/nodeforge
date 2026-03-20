"""Phase 3: Convert normalized spec into an ordered Plan.

CRITICAL INVARIANT (SSH lockout prevention):
  Steps 'disable_root_login' and 'disable_password_auth' MUST have
  depends_on referencing the index of 'verify_admin_login_on_new_port'.
  'verify_admin_login_on_new_port' MUST be gate=True.
  Local steps MUST only be generated after all critical remote steps.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nodeforge.compiler.normalizer import NormalizedContext
from nodeforge.plan.models import Plan, Step, StepKind, StepScope
from nodeforge.specs.bootstrap_schema import BootstrapSpec
from nodeforge.specs.compose_project_schema import ComposeProjectSpec
from nodeforge.specs.file_template_schema import FileTemplateSpec
from nodeforge.specs.service_schema import ServiceSpec
from nodeforge.utils.hashing import sha256_string

AnySpec = BootstrapSpec | ServiceSpec | FileTemplateSpec | ComposeProjectSpec


def plan(ctx: NormalizedContext) -> Plan:
    """Convert a NormalizedContext into an executable Plan."""
    from nodeforge.registry import get_planner, load_addons

    load_addons()

    spec = ctx.spec
    planner_fn = get_planner(spec.kind)
    if planner_fn is None:
        raise RuntimeError(f"No planner registered for spec kind '{spec.kind}'")
    steps = planner_fn(spec, ctx)

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
        created_at=datetime.now(UTC).isoformat(),
    )
    plan_obj.plan_hash = sha256_string("".join(s.id + (s.command or "") for s in steps))
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
    steps.append(
        _s(
            "preflight_connect_root",
            f"Verify root SSH access to {spec.host.address}:{spec.login.port}",
            R,
            StepKind.SSH_COMMAND,
            command="echo 'preflight ok'",
            rollback_hint="Check SSH credentials and network connectivity.",
            tags=["preflight"],
        )
    )
    idx_preflight = len(steps) - 1

    # 1: detect OS
    steps.append(
        _s(
            "detect_os",
            "Detect remote OS (assert Debian/Ubuntu)",
            R,
            StepKind.SSH_COMMAND,
            command="cat /etc/os-release",
            depends_on=[idx_preflight],
            tags=["os"],
        )
    )

    # 2: update apt package index
    steps.append(
        _s(
            "apt_update",
            "Update apt package index",
            R,
            StepKind.SSH_COMMAND,
            command=bs.apt_update(),
            sudo=True,
            rollback_hint="Check apt sources and network connectivity.",
            tags=["packages"],
        )
    )

    # 3: install base packages
    base_packages = ["ufw"]
    if spec.wireguard.enabled:
        base_packages.append("wireguard")
    pkg_list = " ".join(base_packages)
    steps.append(
        _s(
            "install_base_packages",
            f"Install base packages: {pkg_list}",
            R,
            StepKind.SSH_COMMAND,
            command=bs.install_packages(base_packages),
            sudo=True,
            rollback_hint="Check apt sources and network connectivity.",
            tags=["packages"],
        )
    )

    # 3: create admin user (idempotent)
    steps.append(
        _s(
            "create_admin_user",
            f"Create admin user '{spec.admin_user.name}' with sudo",
            R,
            StepKind.SSH_COMMAND,
            command=bs.create_admin_user(
                spec.admin_user.name,
                spec.admin_user.groups,
            ),
            sudo=True,
            tags=["user"],
        )
    )

    # 3b: grant passwordless sudo so the admin can run sudo without a password
    steps.append(
        _s(
            "configure_nopasswd_sudo",
            f"Grant {spec.admin_user.name} passwordless sudo",
            R,
            StepKind.SSH_COMMAND,
            command=bs.nopasswd_sudoers(spec.admin_user.name),
            sudo=True,
            tags=["user"],
        )
    )
    steps.append(
        _s(
            "secure_sudoers_file",
            f"Secure /etc/sudoers.d/{spec.admin_user.name} (chmod 440)",
            R,
            StepKind.SSH_COMMAND,
            command=bs.secure_sudoers(spec.admin_user.name),
            sudo=True,
            tags=["user"],
        )
    )

    # 4: install authorized keys
    if pubkey_content:
        steps.append(
            _s(
                "install_authorized_keys",
                f"Install SSH authorized keys for {spec.admin_user.name}",
                R,
                StepKind.SSH_COMMAND,
                command=bs.install_authorized_keys(spec.admin_user.name, pubkey_content),
                sudo=True,
                tags=["ssh", "keys"],
            )
        )
    else:
        steps.append(
            _s(
                "install_authorized_keys",
                "No pubkeys configured — skipping authorized_keys install",
                R,
                StepKind.VERIFY,
                command="echo 'no pubkeys configured'",
                tags=["ssh", "keys"],
            )
        )

    # 4b: ensure PubkeyAuthentication yes + reload sshd
    # Some images (e.g. this VirtualBox Ubuntu) ship with PubkeyAuthentication no.
    # The gate below requires key auth to work, so we must enable it first.
    steps.append(
        _s(
            "enable_pubkey_auth",
            "Enable PubkeyAuthentication in sshd and reload",
            R,
            StepKind.SSH_COMMAND,
            command=bs.enable_pubkey_auth(),
            sudo=True,
            tags=["ssh", "sshd"],
        )
    )

    # 4c: GATE — verify admin login on current port BEFORE touching sshd
    # This is the critical safety gate: if admin key login doesn't work yet,
    # we must NOT change the SSH port — the server would become unrecoverable.
    if pubkey_content:
        steps.append(
            _s(
                "verify_admin_login_before_port_change",
                f"[GATE] Verify admin SSH login before port change: "
                f"{spec.admin_user.name}@{spec.host.address}:{spec.login.port}",
                V,
                StepKind.GATE,
                command=f"ssh_check:{spec.host.address}:{spec.login.port}:{spec.admin_user.name}",
                rollback_hint=(
                    "Admin key login failed — SSH port has NOT been changed. "
                    "Safe to re-run. Check that admin user and authorized_keys were created correctly."
                ),
                gate=True,
                tags=["gate", "ssh", "lockout-prevention"],
            )
        )

    # 5: write sshd config candidate (port change, defer root/password disable)
    steps.append(
        _s(
            "write_sshd_config_candidate",
            f"Configure SSH daemon: port={spec.ssh.port} (root/password hardening deferred)",
            R,
            StepKind.SSH_COMMAND,
            command=bs.write_sshd_config_candidate(spec.ssh.port),
            sudo=True,
            rollback_hint="Restore /etc/ssh/sshd_config from backup: "
            "cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config",
            tags=["ssh", "sshd"],
        )
    )

    # 6: open new SSH port in firewall
    steps.append(
        _s(
            "open_new_ssh_port_in_firewall",
            f"Open firewall for new SSH port {spec.ssh.port}/tcp",
            R,
            StepKind.SSH_COMMAND,
            command=bs.open_firewall_port(spec.ssh.port),
            sudo=True,
            tags=["firewall"],
        )
    )

    # 7: validate sshd config
    steps.append(
        _s(
            "validate_sshd_config",
            "Validate sshd configuration (sshd -t)",
            R,
            StepKind.SSH_COMMAND,
            command="sshd -t",
            sudo=True,
            rollback_hint="Fix /etc/ssh/sshd_config errors before reloading.",
            tags=["ssh", "sshd"],
        )
    )

    # 8: reload sshd
    steps.append(
        _s(
            "reload_sshd",
            "Reload SSH daemon to apply config",
            R,
            StepKind.SSH_COMMAND,
            command=bs.reload_sshd(),
            sudo=True,
            rollback_hint="If reload fails, check sshd_config syntax with 'sshd -t'.",
            tags=["ssh", "sshd"],
        )
    )

    # 9: GATE — verify admin login on new port
    # This is the SSH lockout prevention gate.
    # Steps that disable root login and password auth MUST depend on this index.
    steps.append(
        _s(
            "verify_admin_login_on_new_port",
            f"[GATE] Verify admin SSH login: {spec.admin_user.name}@{spec.host.address}:{spec.ssh.port}",
            V,
            StepKind.GATE,
            command=f"ssh_check:{spec.host.address}:{spec.ssh.port}:{spec.admin_user.name}",
            rollback_hint=(
                "Admin login failed. Do NOT disable root login or password auth. "
                "Restore sshd_config: cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config && "
                "systemctl reload ssh"
            ),
            gate=True,
            tags=["gate", "ssh", "lockout-prevention"],
        )
    )
    idx_gate = len(steps) - 1

    # 10: disable root login — MUST depend on gate
    steps.append(
        _s(
            "disable_root_login",
            "Disable root SSH login (PermitRootLogin no)",
            R,
            StepKind.SSH_COMMAND,
            command=bs.disable_root_login(),
            sudo=True,
            depends_on=[idx_gate],
            rollback_hint="sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config && systemctl reload ssh",
            tags=["ssh", "hardening", "lockout-prevention"],
        )
    )

    # 11: disable password auth — MUST depend on gate
    if spec.ssh.disable_password_auth and pubkey_content:
        steps.append(
            _s(
                "disable_password_auth",
                "Disable SSH password authentication",
                R,
                StepKind.SSH_COMMAND,
                command=bs.disable_password_auth(),
                sudo=True,
                depends_on=[idx_gate],
                rollback_hint="sed -i 's/^PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config && systemctl reload ssh",
                tags=["ssh", "hardening", "lockout-prevention"],
            )
        )
    else:
        steps.append(
            _s(
                "disable_password_auth",
                "Password auth not disabled (no pubkeys or config not set)",
                R,
                StepKind.VERIFY,
                command="echo 'password auth left enabled'",
                depends_on=[idx_gate],
                tags=["ssh", "hardening"],
            )
        )

    # 12: finalize firewall (three separate steps — no shell chaining)
    steps.append(
        _s(
            "ufw_default_deny_incoming",
            "Firewall: default deny incoming",
            R,
            StepKind.SSH_COMMAND,
            command=bs.ufw_default_deny_incoming(),
            sudo=True,
            tags=["firewall"],
        )
    )
    steps.append(
        _s(
            "ufw_default_allow_outgoing",
            "Firewall: default allow outgoing",
            R,
            StepKind.SSH_COMMAND,
            command=bs.ufw_default_allow_outgoing(),
            sudo=True,
            tags=["firewall"],
        )
    )
    steps.append(
        _s(
            "ufw_force_enable",
            "Enable firewall (ufw --force enable)",
            R,
            StepKind.SSH_COMMAND,
            command=bs.ufw_force_enable(),
            sudo=True,
            tags=["firewall"],
        )
    )

    # 13: reload sshd again after hardening changes
    steps.append(
        _s(
            "reload_sshd_final",
            "Reload SSH daemon to apply hardening changes",
            R,
            StepKind.SSH_COMMAND,
            command=bs.reload_sshd(),
            sudo=True,
            depends_on=[idx_gate],
            tags=["ssh", "sshd"],
        )
    )

    # 14-18: WireGuard (remote steps + local state save)
    if spec.wireguard.enabled:
        import ipaddress as _ip

        wg_port = (
            int(spec.wireguard.endpoint.split(":")[-1]) if ":" in spec.wireguard.endpoint else 51820
        )
        # VPN subnet derived from the server's interface address (e.g. 10.10.0.0/24)
        vpn_subnet = str(_ip.ip_interface(spec.wireguard.address).network)

        # Server config: [Interface] with ListenPort + [Peer] with client public key
        server_conf = wg.generate_server_config(
            interface=spec.wireguard.interface,
            address=spec.wireguard.address,
            private_key=ctx.wireguard_private_key,
            listen_port=wg_port,
            client_public_key=ctx.wg_client_public_key,
            peer_address=spec.wireguard.peer_address,
        )
        # Client config: saved locally to ~/.wg/nodeforge/{host}/client.conf
        client_conf = wg.generate_client_config(
            client_private_key=ctx.wg_client_private_key,
            peer_address=spec.wireguard.peer_address,
            server_public_key=ctx.wireguard_public_key,
            endpoint=spec.wireguard.endpoint,
            vpn_subnet=vpn_subnet,
            persistent_keepalive=spec.wireguard.persistent_keepalive,
        )
        # Store both on ctx so the executor can persist them after apply
        ctx.wireguard_conf_content = server_conf
        ctx.wg_client_conf_content = client_conf

        steps.append(
            _s(
                "write_wireguard_config",
                f"Write WireGuard server config: /etc/wireguard/{spec.wireguard.interface}.conf",
                R,
                StepKind.SSH_UPLOAD,
                file_content=server_conf,
                target_path=f"/etc/wireguard/{spec.wireguard.interface}.conf",
                sudo=True,
                tags=["wireguard"],
            )
        )
        # Open the WireGuard UDP port in the firewall before starting the interface
        steps.append(
            _s(
                "open_wireguard_port_in_firewall",
                f"Open firewall for WireGuard UDP port {wg_port}",
                R,
                StepKind.SSH_COMMAND,
                command=f"ufw allow {wg_port}/udp",
                sudo=True,
                tags=["wireguard", "firewall"],
            )
        )
        steps.append(
            _s(
                "enable_wireguard",
                f"Enable and start WireGuard: wg-quick@{spec.wireguard.interface}",
                R,
                StepKind.SSH_COMMAND,
                command=wg.enable_wireguard(spec.wireguard.interface),
                sudo=True,
                tags=["wireguard"],
            )
        )
        steps.append(
            _s(
                "verify_wireguard",
                f"Verify WireGuard interface {spec.wireguard.interface} is up",
                V,
                StepKind.VERIFY,
                command=f"wg show {spec.wireguard.interface}",
                sudo=True,
                tags=["wireguard"],
            )
        )

    # 17: postflight checks (from spec)
    for check in spec.checks:
        steps.append(
            _s(
                f"postflight_{check.type}",
                f"Postflight check: {check.type}",
                V,
                StepKind.VERIFY,
                command=f"check:{check.type}",
                tags=["postflight", check.type],
            )
        )

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
        steps.append(
            _s(
                "ship_goss_file",
                f"Ship goss spec to ~/.goss/{spec.meta.name}.yaml on remote",
                R,
                StepKind.SSH_UPLOAD,
                file_content=goss_content,
                target_path=f"~/.goss/{spec.meta.name}.yaml",
                sudo=False,
                tags=["goss"],
            )
        )
        steps.append(
            _s(
                "run_goss_validate",
                "Run goss validate and display verification results",
                V,
                StepKind.VERIFY,
                command="goss_validate",
                depends_on=[idx_ship],
                tags=["goss", "verify"],
            )
        )
    else:
        # Emit a visible warning step so the operator sees it in the plan output
        steps.append(
            _s(
                "goss_unavailable",
                "[WARNING] No goss spec available — server state will NOT be verified",
                V,
                StepKind.VERIFY,
                command="goss_unavailable",
                tags=["goss", "warning"],
            )
        )

    # ------------------------------------------------------------------ #
    # WireGuard SSH restriction — MUST be the absolute last remote steps.
    # Adds a WireGuard-restricted SSH rule, then removes the open-to-all rule.
    # After these execute, direct SSH to spec.host.address stops working.
    # Split into two steps (no shell chaining).
    # ------------------------------------------------------------------ #
    if spec.wireguard.enabled:
        peer_ip = (
            spec.wireguard.peer_address.split("/")[0]
            if spec.firewall.registered_peers_only
            else None
        )
        label_allow = (
            f"Allow SSH port {spec.ssh.port} on WireGuard peer {peer_ip}"
            if peer_ip
            else f"Allow SSH port {spec.ssh.port} on WireGuard interface {spec.wireguard.interface}"
        )
        steps.append(
            _s(
                "allow_ssh_on_wireguard",
                label_allow,
                R,
                StepKind.SSH_COMMAND,
                command=bs.allow_ssh_on_wireguard(
                    spec.ssh.port,
                    spec.wireguard.interface,
                    peer_ip,
                ),
                sudo=True,
                tags=["ssh", "firewall", "wireguard"],
            )
        )
        steps.append(
            _s(
                "delete_open_ssh_rule",
                f"Remove open-to-all SSH rule for port {spec.ssh.port}/tcp",
                R,
                StepKind.SSH_COMMAND,
                command=bs.delete_open_ssh_rule(spec.ssh.port),
                sudo=True,
                tags=["ssh", "firewall", "wireguard"],
            )
        )

    # ------------------------------------------------------------------ #
    # LOCAL: only after remote success
    # ------------------------------------------------------------------ #

    # SSH conf.d entry — only when local.ssh_config.enabled (default: true)
    if spec.local.ssh_config.enabled:
        steps.append(
            _s(
                "backup_local_ssh_config",
                "Backup local ~/.ssh/config",
                L,
                StepKind.LOCAL_COMMAND,
                command="backup_ssh_config",
                tags=["local", "ssh-config"],
            )
        )
        steps.append(
            _s(
                "write_local_ssh_conf_d",
                f"Write local SSH conf.d entry: {ctx.ssh_conf_d_path}",
                L,
                StepKind.LOCAL_FILE_WRITE,
                target_path=str(ctx.ssh_conf_d_path) if ctx.ssh_conf_d_path else "",
                tags=["local", "ssh-config"],
            )
        )
        steps.append(
            _s(
                "ensure_include_directive",
                "Ensure Include directive in ~/.ssh/config",
                L,
                StepKind.LOCAL_COMMAND,
                command="ensure_include",
                tags=["local", "ssh-config"],
            )
        )

    # WireGuard local state — save key material + metadata after remote success
    if spec.wireguard.enabled:
        steps.append(
            _s(
                "save_local_wireguard_state",
                f"Save WireGuard state to ~/.wg/nodeforge/{spec.host.name}/",
                L,
                StepKind.LOCAL_COMMAND,
                command="save_wireguard_state",
                tags=["local", "wireguard"],
            )
        )

    # Inventory DB
    if spec.local.inventory.enabled:
        steps.append(
            _s(
                "open_or_init_local_inventory",
                "Open or initialize local SQLCipher inventory database",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="init_inventory",
                tags=["local", "inventory"],
            )
        )

        # 22: upsert server record
        steps.append(
            _s(
                "upsert_server_inventory",
                f"Upsert server record in inventory: {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_server",
                tags=["local", "inventory"],
            )
        )

        # 23: record run metadata
        steps.append(
            _s(
                "record_run_metadata",
                "Record bootstrap run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _plan_service(spec: ServiceSpec, ctx: NormalizedContext) -> list[Step]:
    from nodeforge.runtime.steps import container as ct
    from nodeforge.runtime.steps import docker as dk
    from nodeforge.runtime.steps import nginx as nx
    from nodeforge.runtime.steps import postgres as pg

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    # preflight
    steps.append(
        _s(
            "preflight_connect_admin",
            f"Verify admin SSH access to {spec.host.address}:{spec.login.port}",
            R,
            StepKind.SSH_COMMAND,
            command="echo 'preflight ok'",
            tags=["preflight"],
        )
    )

    steps.append(
        _s(
            "detect_os",
            "Detect remote OS",
            R,
            StepKind.SSH_COMMAND,
            command="cat /etc/os-release",
            tags=["os"],
        )
    )

    # apt update — shared by all service installations that need packages
    needs_apt = (
        (spec.postgres and spec.postgres.enabled)
        or (spec.nginx and spec.nginx.enabled)
        or (spec.docker and spec.docker.enabled)
        or bool(spec.containers)
    )
    if needs_apt:
        steps.append(
            _s(
                "apt_update",
                "Update apt package index",
                R,
                StepKind.SSH_COMMAND,
                command="apt-get update -y",
                sudo=True,
                tags=["packages"],
            )
        )

    # Postgres
    if spec.postgres and spec.postgres.enabled:
        # PGDG repository — ensures the requested PostgreSQL version is
        # available regardless of the distro's default packages.
        steps.append(
            _s(
                "install_pgdg_prerequisites",
                "Install PGDG repository prerequisites",
                R,
                StepKind.SSH_COMMAND,
                command=pg.install_pgdg_prerequisites(),
                sudo=True,
                tags=["postgres", "pgdg"],
            )
        )
        steps.append(
            _s(
                "add_pgdg_signing_key",
                "Import PostgreSQL PGDG apt signing key",
                R,
                StepKind.SSH_COMMAND,
                command=pg.add_pgdg_signing_key(),
                sudo=True,
                tags=["postgres", "pgdg"],
            )
        )
        steps.append(
            _s(
                "add_pgdg_source_list",
                "Add PGDG apt repository source list",
                R,
                StepKind.SSH_COMMAND,
                command=pg.add_pgdg_source_list(),
                sudo=True,
                tags=["postgres", "pgdg"],
            )
        )
        steps.append(
            _s(
                "apt_update_pgdg",
                "Update apt package index (with PGDG repo)",
                R,
                StepKind.SSH_COMMAND,
                command="apt-get update -y",
                sudo=True,
                tags=["postgres", "pgdg", "packages"],
            )
        )
        steps.append(
            _s(
                "install_postgres",
                f"Install PostgreSQL {spec.postgres.version}",
                R,
                StepKind.SSH_COMMAND,
                command=pg.install_postgres(spec.postgres.version),
                sudo=True,
                tags=["postgres"],
            )
        )
        steps.append(
            _s(
                "configure_postgres_listen",
                "Configure PostgreSQL listen_addresses",
                R,
                StepKind.SSH_COMMAND,
                command=pg.configure_listen(spec.postgres.listen_addresses),
                sudo=True,
                tags=["postgres"],
            )
        )
        steps.append(
            _s(
                "enable_postgres",
                "Enable and start PostgreSQL service",
                R,
                StepKind.SSH_COMMAND,
                command=pg.enable_postgres(),
                sudo=True,
                tags=["postgres"],
            )
        )
        if spec.postgres.create_role:
            steps.append(
                _s(
                    "create_db_role",
                    f"Create PostgreSQL role: {spec.postgres.create_role.name}",
                    R,
                    StepKind.SSH_COMMAND,
                    command=pg.create_role(
                        spec.postgres.create_role.name,
                        spec.postgres.create_role.password_env,
                    ),
                    sudo=True,
                    tags=["postgres"],
                )
            )
        if spec.postgres.create_database:
            steps.append(
                _s(
                    "create_database",
                    f"Create PostgreSQL database: {spec.postgres.create_database.name}",
                    R,
                    StepKind.SSH_COMMAND,
                    command=pg.create_database(
                        spec.postgres.create_database.name,
                        spec.postgres.create_database.owner,
                    ),
                    sudo=True,
                    tags=["postgres"],
                )
            )
        steps.append(
            _s(
                "postgres_ready_check",
                "Verify PostgreSQL is ready",
                V,
                StepKind.VERIFY,
                command="pg_isready",
                sudo=True,
                tags=["postgres", "verify"],
            )
        )

    # Nginx
    if spec.nginx and spec.nginx.enabled:
        steps.append(
            _s(
                "install_nginx",
                "Install nginx",
                R,
                StepKind.SSH_COMMAND,
                command=nx.install_nginx(),
                sudo=True,
                tags=["nginx"],
            )
        )
        steps.append(
            _s(
                "enable_nginx",
                "Enable and start nginx service",
                R,
                StepKind.SSH_COMMAND,
                command=nx.enable_nginx(),
                sudo=True,
                tags=["nginx"],
            )
        )
        steps.append(
            _s(
                "remove_nginx_default_site",
                "Remove default nginx site",
                R,
                StepKind.SSH_COMMAND,
                command=nx.remove_default_site(),
                sudo=True,
                tags=["nginx"],
            )
        )
        for site in spec.nginx.sites:
            safe_name = site.domain.replace(".", "_")
            steps.append(
                _s(
                    f"write_nginx_site_{safe_name}",
                    f"Write nginx site config for {site.domain}",
                    R,
                    StepKind.SSH_UPLOAD,
                    file_content=nx.site_config_content(site),
                    target_path=nx.site_config_path(site),
                    sudo=True,
                    tags=["nginx", site.domain],
                )
            )
            steps.append(
                _s(
                    f"enable_nginx_site_{safe_name}",
                    f"Enable nginx site: {site.domain}",
                    R,
                    StepKind.SSH_COMMAND,
                    command=nx.enable_site(site),
                    sudo=True,
                    tags=["nginx", site.domain],
                )
            )
        steps.append(
            _s(
                "validate_nginx_config",
                "Validate nginx configuration",
                R,
                StepKind.SSH_COMMAND,
                command=nx.validate_nginx_config(),
                sudo=True,
                rollback_hint="Check nginx config files for syntax errors.",
                tags=["nginx"],
            )
        )
        steps.append(
            _s(
                "reload_nginx",
                "Reload nginx to apply configuration",
                R,
                StepKind.SSH_COMMAND,
                command=nx.reload_nginx_service(),
                sudo=True,
                tags=["nginx"],
            )
        )
        steps.append(
            _s(
                "nginx_config_check",
                "Verify nginx configuration is valid",
                V,
                StepKind.VERIFY,
                command="nginx -t",
                sudo=True,
                tags=["nginx", "verify"],
            )
        )

    # Docker
    needs_docker = spec.docker and spec.docker.enabled or bool(spec.containers)
    if needs_docker:
        steps.append(
            _s(
                "install_docker",
                "Install Docker",
                R,
                StepKind.SSH_COMMAND,
                command=dk.install_docker(),
                sudo=True,
                tags=["docker"],
            )
        )
        steps.append(
            _s(
                "enable_docker",
                "Enable Docker service",
                R,
                StepKind.SSH_COMMAND,
                command=dk.enable_docker(),
                sudo=True,
                tags=["docker"],
            )
        )
        steps.append(
            _s(
                "docker_version_check",
                "Verify Docker installation",
                V,
                StepKind.VERIFY,
                command="docker --version",
                sudo=True,
                tags=["docker", "verify"],
            )
        )

    # Containers
    for c in spec.containers:
        steps.append(
            _s(
                f"pull_image_{c.name}",
                f"Pull container image: {c.image}",
                R,
                StepKind.SSH_COMMAND,
                command=ct.pull_image(c.image),
                sudo=True,
                tags=["container", c.name],
            )
        )
        steps.append(
            _s(
                f"stop_container_{c.name}",
                f"Stop existing container '{c.name}' (if running)",
                R,
                StepKind.SSH_COMMAND,
                command=ct.stop_container(c.name),
                sudo=True,
                tags=["container", c.name],
            )
        )
        steps.append(
            _s(
                f"remove_container_{c.name}",
                f"Remove existing container '{c.name}' (if present)",
                R,
                StepKind.SSH_COMMAND,
                command=ct.remove_container(c.name),
                sudo=True,
                tags=["container", c.name],
            )
        )
        steps.append(
            _s(
                f"run_container_{c.name}",
                f"Start container '{c.name}' from {c.image}",
                R,
                StepKind.SSH_COMMAND,
                command=ct.run_container(c),
                sudo=True,
                tags=["container", c.name],
            )
        )
        steps.append(
            _s(
                f"container_running_check_{c.name}",
                f"Verify container '{c.name}' is running",
                V,
                StepKind.VERIFY,
                command=f"docker inspect --format='{{{{.State.Running}}}}' {c.name}",
                sudo=True,
                tags=["container", c.name, "verify"],
            )
        )
        if c.healthcheck:
            steps.append(
                _s(
                    f"http_health_check_{c.name}",
                    f"HTTP health check: {c.healthcheck.url}",
                    V,
                    StepKind.VERIFY,
                    command=f"http_check:{c.healthcheck.url}:{c.healthcheck.expect_status}",
                    tags=["container", c.name, "health"],
                )
            )

    # Local inventory
    if spec.local.inventory.enabled:
        steps.append(
            _s(
                "open_or_init_local_inventory",
                "Open or initialize local SQLCipher inventory database",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="init_inventory",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "update_server_services_metadata",
                f"Update service metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_service_run_metadata",
                "Record service run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _plan_file_template(spec: FileTemplateSpec, ctx: NormalizedContext) -> list[Step]:
    """Generate steps for rendering and uploading managed configuration files."""
    from nodeforge.runtime.steps import file_template as ft

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    # Preflight
    steps.append(
        _s(
            "preflight_connect_admin",
            f"Verify admin SSH access to {spec.host.address}:{spec.login.port}",
            R,
            StepKind.SSH_COMMAND,
            command="echo 'preflight ok'",
            tags=["preflight"],
        )
    )

    # For each template: mkdir parent -> upload rendered content -> chmod -> chown
    for t in spec.templates:
        safe_id = t.dest.replace("/", "_").strip("_")
        rendered = ctx.rendered_templates.get(t.dest, "")

        # mkdir parent directory
        steps.append(
            _s(
                f"mkdir_{safe_id}",
                f"Create parent directory for {t.dest}",
                R,
                StepKind.SSH_COMMAND,
                command=ft.mkdir_for_file(t.dest),
                sudo=True,
                tags=["file_template", "mkdir"],
            )
        )

        # Upload rendered content
        steps.append(
            _s(
                f"upload_{safe_id}",
                f"Upload rendered template to {t.dest}",
                R,
                StepKind.SSH_UPLOAD,
                file_content=rendered,
                target_path=t.dest,
                sudo=True,
                tags=["file_template", "upload"],
            )
        )

        # Set permissions
        steps.append(
            _s(
                f"chmod_{safe_id}",
                f"Set permissions {t.mode} on {t.dest}",
                R,
                StepKind.SSH_COMMAND,
                command=ft.chmod_file(t.dest, t.mode),
                sudo=True,
                tags=["file_template", "chmod"],
            )
        )

        # Set ownership
        steps.append(
            _s(
                f"chown_{safe_id}",
                f"Set ownership {t.owner}:{t.group} on {t.dest}",
                R,
                StepKind.SSH_COMMAND,
                command=ft.chown_file(t.dest, t.owner, t.group),
                sudo=True,
                tags=["file_template", "chown"],
            )
        )

    # Postflight checks
    for check in spec.checks:
        steps.append(
            _s(
                f"postflight_{check.type}",
                f"Postflight check: {check.type}",
                V,
                StepKind.VERIFY,
                command=f"check:{check.type}",
                tags=["postflight", check.type],
            )
        )

    # Local inventory
    if spec.local.inventory.enabled:
        steps.append(
            _s(
                "open_or_init_local_inventory",
                "Open or initialize local inventory database",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="init_inventory",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "update_file_template_metadata",
                f"Update file_template metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_file_template_run",
                "Record file_template run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _plan_compose_project(spec: ComposeProjectSpec, ctx: NormalizedContext) -> list[Step]:
    """Generate steps for deploying a Docker Compose project."""
    from nodeforge.runtime.steps import compose as cp

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    p = spec.project

    # Preflight
    steps.append(
        _s(
            "preflight_connect_admin",
            f"Verify admin SSH access to {spec.host.address}:{spec.login.port}",
            R,
            StepKind.SSH_COMMAND,
            command="echo 'preflight ok'",
            tags=["preflight"],
        )
    )

    # Create project directory
    steps.append(
        _s(
            "mkdir_project_dir",
            f"Create project directory: {p.directory}",
            R,
            StepKind.SSH_COMMAND,
            command=f"mkdir -p {p.directory}",
            sudo=True,
            tags=["compose", "mkdir"],
        )
    )

    # Create managed directories
    for d in p.directories:
        if d.path.startswith("/"):
            full_path = d.path
        else:
            full_path = f"{p.directory}/{d.path}"
        safe_id = full_path.replace("/", "_").strip("_")
        steps.append(
            _s(
                f"mkdir_{safe_id}",
                f"Create managed directory: {full_path}",
                R,
                StepKind.SSH_COMMAND,
                command=cp.mkdir_with_permissions(full_path, d.mode, d.owner, d.group),
                sudo=True,
                tags=["compose", "mkdir"],
            )
        )

    # Upload rendered templates
    for t in p.templates:
        if t.dest.startswith("/"):
            full_dest = t.dest
        else:
            full_dest = f"{p.directory}/{t.dest}"
        safe_id = full_dest.replace("/", "_").strip("_")
        rendered = ctx.rendered_templates.get(full_dest, "")

        steps.append(
            _s(
                f"upload_template_{safe_id}",
                f"Upload rendered template: {full_dest}",
                R,
                StepKind.SSH_UPLOAD,
                file_content=rendered,
                target_path=full_dest,
                sudo=True,
                tags=["compose", "template"],
            )
        )

    # Upload compose file
    compose_dest = f"{p.directory}/{p.compose_file}"
    steps.append(
        _s(
            "upload_compose_file",
            f"Upload compose file: {compose_dest}",
            R,
            StepKind.SSH_UPLOAD,
            file_content=ctx.compose_file_content,
            target_path=compose_dest,
            sudo=True,
            tags=["compose", "compose-file"],
        )
    )

    # Validate compose config
    steps.append(
        _s(
            "compose_config_validate",
            f"Validate compose configuration for project '{p.name}'",
            R,
            StepKind.SSH_COMMAND,
            command=cp.compose_config(p.directory, p.compose_file, p.name),
            sudo=True,
            rollback_hint="Check compose file syntax and variable substitution.",
            tags=["compose", "validate"],
        )
    )

    # Pull images (optional)
    if p.pull_before_up:
        steps.append(
            _s(
                "compose_pull",
                f"Pull images for project '{p.name}'",
                R,
                StepKind.SSH_COMMAND,
                command=cp.compose_pull(p.directory, p.compose_file, p.name),
                sudo=True,
                tags=["compose", "pull"],
            )
        )

    # Start the stack
    steps.append(
        _s(
            "compose_up",
            f"Start compose project '{p.name}' (detached)",
            R,
            StepKind.SSH_COMMAND,
            command=cp.compose_up(p.directory, p.compose_file, p.name),
            sudo=True,
            tags=["compose", "up"],
        )
    )

    # Health check
    if p.healthcheck.enabled:
        # Command encodes the parameters for the handler to parse
        health_cmd = (
            f"compose_health:{p.directory}:{p.compose_file}:{p.name}"
            f":{p.healthcheck.timeout}:{p.healthcheck.interval}"
        )
        steps.append(
            _s(
                "compose_health_check",
                f"Wait for containers healthy (timeout={p.healthcheck.timeout}s)",
                V,
                StepKind.COMPOSE_HEALTH_CHECK,
                command=health_cmd,
                tags=["compose", "health"],
            )
        )

    # Postflight checks
    for check in spec.checks:
        steps.append(
            _s(
                f"postflight_{check.type}",
                f"Postflight check: {check.type}",
                V,
                StepKind.VERIFY,
                command=f"check:{check.type}",
                tags=["postflight", check.type],
            )
        )

    # Local inventory
    if spec.local.inventory.enabled:
        steps.append(
            _s(
                "open_or_init_local_inventory",
                "Open or initialize local inventory database",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="init_inventory",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "update_compose_project_metadata",
                f"Update compose_project metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_compose_project_run",
                "Record compose_project run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps
