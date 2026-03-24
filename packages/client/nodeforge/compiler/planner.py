"""Phase 3: Convert normalized spec into an ordered Plan.

CRITICAL INVARIANT (SSH lockout prevention):
  Steps 'disable_root_login' and 'disable_password_auth' MUST have
  depends_on referencing the index of 'verify_admin_login_on_new_port'.
  'verify_admin_login_on_new_port' MUST be gate=True.
  Local steps MUST only be generated after all critical remote steps.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

from nodeforge.compiler.normalizer import NormalizedContext
from nodeforge_core.plan.models import Plan, Step, StepKind, StepScope
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
from nodeforge_core.utils.hashing import sha256_string

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


def _encode_check_command(check, spec) -> str:
    """Encode a CheckBlock into a command string for the executor to dispatch."""
    ctype = check.type
    host = spec.host.address
    if ctype == "ssh_reachable":
        port = check.port or 22
        user = check.user or "root"
        return f"check:ssh_reachable:{host}:{port}:{user}"
    elif ctype == "port_open":
        port = check.port or 22
        return f"check:port_open:{host}:{port}"
    elif ctype == "wireguard_up":
        iface = check.interface or "wg0"
        return f"check:wireguard_up:{iface}"
    elif ctype == "container_running":
        name = check.name or "unknown"
        return f"check:container_running:{name}"
    elif ctype == "http":
        url = check.url or ""
        status = check.expect_status or 200
        return f"check:http:{url}:{status}"
    elif ctype == "postgres_ready":
        return "check:postgres_ready"
    elif ctype == "nginx_ready":
        return "check:nginx_ready"
    return f"check:{ctype}"


def plan(ctx: NormalizedContext) -> Plan:
    """Convert a NormalizedContext into an executable Plan."""
    from nodeforge_core.registry import get_planner, load_addons

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
                "set_wireguard_dir_permissions",
                "Secure /etc/wireguard directory (chmod 700)",
                R,
                StepKind.SSH_COMMAND,
                command=wg.set_wireguard_dir_permissions(),
                sudo=True,
                tags=["wireguard"],
            )
        )
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
                "load_wireguard_module",
                "Load WireGuard kernel module",
                R,
                StepKind.SSH_COMMAND,
                command=wg.load_wireguard_module(),
                sudo=True,
                tags=["wireguard"],
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
                command=_encode_check_command(check, spec),
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
                command=_encode_check_command(check, spec),
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
    from nodeforge.runtime.steps import docker as dk

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

    # Docker — always required for compose_project
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
                command=_encode_check_command(check, spec),
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


def _plan_stack(spec: StackSpec, ctx: NormalizedContext) -> list[Step]:
    """Plan a stack by expanding resources in dependency order.

    Stack resources are topologically sorted by ``depends_on``, then each
    resource is delegated to its kind's registered planner.  Steps from
    each resource are prefixed with the resource name for traceability.
    """
    from nodeforge_core.registry import get_normalizer, get_planner, get_spec_model

    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    steps: list[Step] = []

    # Topological sort
    ordered = _topo_sort(spec.resources)

    for res in ordered:
        planner_fn = get_planner(res.kind)
        if planner_fn is None:
            steps.append(
                _s(
                    f"stack_{res.name}_error",
                    f"No planner for resource kind '{res.kind}'",
                    R,
                    StepKind.AGENT_COMMAND,
                    command=f"echo 'ERROR: no planner for {res.kind}'",
                    tags=["stack", res.name, "error"],
                )
            )
            continue

        # Build a minimal spec-like object for the resource's planner.
        model_class = get_spec_model(res.kind)
        if model_class is None:
            continue

        # Construct a synthetic spec for the child resource.  We merge
        # the stack-level host/login/local into the resource config.
        child_data = {
            "kind": res.kind,
            "meta": {"name": f"{spec.meta.name}/{res.name}"},
            "host": spec.host.model_dump(),
            **res.config,
        }

        # Inject login and local if the model expects them and they're
        # not already in the config.
        if "login" not in child_data:
            child_data["login"] = spec.login.model_dump()
        if "local" not in child_data:
            child_data["local"] = spec.local.model_dump()

        try:
            child_spec = model_class.model_validate(child_data)
        except Exception:
            steps.append(
                _s(
                    f"stack_{res.name}_validation_error",
                    f"Failed to validate resource '{res.name}' config as {res.kind}",
                    R,
                    StepKind.AGENT_COMMAND,
                    command=f"echo 'ERROR: validation failed for {res.name}'",
                    tags=["stack", res.name, "error"],
                )
            )
            continue

        # Normalize the child spec
        child_ctx = NormalizedContext(spec=child_spec, spec_dir=ctx.spec_dir)
        normalizer_fn = get_normalizer(res.kind)
        if normalizer_fn is not None:
            with contextlib.suppress(Exception):
                normalizer_fn(child_spec, child_ctx)

        # Generate steps from the child planner
        child_steps = planner_fn(child_spec, child_ctx)

        # Prefix step IDs with the resource name for traceability
        for cs in child_steps:
            cs.id = f"stack_{res.name}_{cs.id}"
            cs.tags = ["stack", res.name] + cs.tags

        steps.extend(child_steps)

    # Postflight checks for the stack
    for check in spec.checks:
        steps.append(
            _s(
                f"stack_postflight_{check.type}",
                f"Stack postflight check: {check.type}",
                V,
                StepKind.VERIFY,
                command=_encode_check_command(check, spec),
                tags=["stack", "postflight", check.type],
            )
        )

    # Local inventory
    if spec.local.inventory.enabled:
        steps.append(
            _s(
                "stack_open_or_init_local_inventory",
                "Open or initialize local inventory database",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="init_inventory",
                tags=["local", "inventory", "stack"],
            )
        )

    return steps


def _plan_postgres_ensure(spec: PostgresEnsureSpec, ctx: NormalizedContext) -> list[Step]:
    """Generate steps for ensuring PostgreSQL resources exist."""
    from nodeforge.runtime.steps.postgres_ensure import (
        ensure_database_cmd,
        ensure_extension_cmd,
        ensure_grant_cmd,
        ensure_user_cmd,
        pg_isready_cmd,
    )

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    conn = spec.connection
    conn_kwargs = {
        "conn_host": conn.host,
        "conn_port": conn.port,
        "admin_user": conn.admin_user,
        "docker_exec": conn.docker_exec,
    }

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

    # Gate: verify PostgreSQL is ready
    steps.append(
        _s(
            "pg_isready_gate",
            "Verify PostgreSQL is accepting connections",
            R,
            StepKind.GATE,
            command=pg_isready_cmd(**conn_kwargs),
            gate=True,
            sudo=True,
            tags=["postgres_ensure", "always"],
        )
    )

    # Ensure users
    for u in spec.users:
        password = u.password_env if u.password_env else None
        steps.append(
            _s(
                f"ensure_user_{u.name}",
                f"Ensure PostgreSQL user '{u.name}' exists",
                R,
                StepKind.SSH_COMMAND,
                command=ensure_user_cmd(u.name, password, **conn_kwargs),
                sudo=True,
                tags=["postgres_ensure", "user"],
            )
        )

    # Ensure databases
    for d in spec.databases:
        steps.append(
            _s(
                f"ensure_database_{d.name}",
                f"Ensure PostgreSQL database '{d.name}' exists with owner '{d.owner}'",
                R,
                StepKind.SSH_COMMAND,
                command=ensure_database_cmd(d.name, d.owner, **conn_kwargs),
                sudo=True,
                tags=["postgres_ensure", "database"],
            )
        )

    # Ensure extensions
    for e in spec.extensions:
        steps.append(
            _s(
                f"ensure_extension_{e.name}_on_{e.database}",
                f"Ensure extension '{e.name}' on database '{e.database}'",
                R,
                StepKind.SSH_COMMAND,
                command=ensure_extension_cmd(e.name, e.database, **conn_kwargs),
                sudo=True,
                tags=["postgres_ensure", "extension"],
            )
        )

    # Ensure grants
    for g in spec.grants:
        steps.append(
            _s(
                f"grant_{g.privilege.lower()}_{g.on_database}_to_{g.to_user}",
                f"Grant {g.privilege} on {g.on_database} to {g.to_user}",
                R,
                StepKind.SSH_COMMAND,
                command=ensure_grant_cmd(g.privilege, g.on_database, g.to_user, **conn_kwargs),
                sudo=True,
                tags=["postgres_ensure", "grant"],
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
                command=_encode_check_command(check, spec),
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
                "update_postgres_ensure_metadata",
                f"Update postgres_ensure metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_postgres_ensure_run",
                "Record postgres_ensure run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _plan_backup_job(spec: BackupJobSpec, ctx: NormalizedContext) -> list[Step]:
    """Generate steps for deploying a backup job with systemd timer."""
    from nodeforge.runtime.steps.backup import render_backup_script
    from nodeforge.runtime.steps.systemd import (
        daemon_reload,
        enable_now_unit,
        is_active,
        render_service_unit,
        render_timer_unit,
    )

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    b = spec.backup
    src = b.source
    script_name = f"nodeforge-backup-{b.name}"
    script_path = f"/usr/local/bin/{script_name}.sh"

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

    # Create backup destination directory
    steps.append(
        _s(
            f"mkdir_backup_dest_{b.name}",
            f"Create backup destination directory {b.destination.path}",
            R,
            StepKind.SSH_COMMAND,
            command=f"mkdir -p {b.destination.path}",
            sudo=True,
            tags=["backup_job", "mkdir"],
        )
    )

    # Write backup script
    script_content = render_backup_script(
        name=b.name,
        source_type=src.type,
        destination_path=b.destination.path,
        retention_count=b.retention.count,
        database=src.database,
        pg_host=src.host,
        pg_port=src.port,
        pg_user=src.user,
        docker_exec=src.docker_exec,
        source_path=src.path,
    )
    steps.append(
        _s(
            f"write_backup_script_{b.name}",
            f"Write backup script {script_path}",
            R,
            StepKind.SSH_UPLOAD,
            file_content=script_content,
            target_path=script_path,
            sudo=True,
            tags=["backup_job", "upload"],
        )
    )

    # Make script executable
    steps.append(
        _s(
            f"chmod_backup_script_{b.name}",
            "Make backup script executable",
            R,
            StepKind.SSH_COMMAND,
            command=f"chmod 0755 {script_path}",
            sudo=True,
            tags=["backup_job"],
        )
    )

    # Write systemd service (oneshot)
    service_content = render_service_unit(
        description=f"Backup job: {b.name}",
        exec_start=script_path,
        service_type="oneshot",
        restart="no",
        restart_sec=0,
        wanted_by="",
    )
    service_file = f"/etc/systemd/system/{script_name}.service"
    steps.append(
        _s(
            f"write_backup_service_{b.name}",
            f"Write backup service file {service_file}",
            R,
            StepKind.SSH_UPLOAD,
            file_content=service_content,
            target_path=service_file,
            sudo=True,
            tags=["backup_job", "upload"],
        )
    )

    # Write systemd timer
    timer_content = render_timer_unit(
        description=f"Backup timer: {b.name}",
        on_calendar=b.schedule,
        persistent=True,
    )
    timer_file = f"/etc/systemd/system/{script_name}.timer"
    steps.append(
        _s(
            f"write_backup_timer_{b.name}",
            f"Write backup timer file {timer_file}",
            R,
            StepKind.SSH_UPLOAD,
            file_content=timer_content,
            target_path=timer_file,
            sudo=True,
            tags=["backup_job", "upload"],
        )
    )

    # Daemon reload
    steps.append(
        _s(
            "systemd_daemon_reload",
            "Reload systemd daemon",
            R,
            StepKind.SSH_COMMAND,
            command=daemon_reload(),
            sudo=True,
            tags=["backup_job", "always"],
        )
    )

    # Enable and start timer
    steps.append(
        _s(
            f"enable_start_backup_timer_{b.name}",
            f"Enable and start {script_name}.timer",
            R,
            StepKind.SSH_COMMAND,
            command=enable_now_unit(f"{script_name}.timer"),
            sudo=True,
            tags=["backup_job", "always"],
        )
    )

    # Verify timer active
    steps.append(
        _s(
            f"verify_backup_timer_{b.name}_active",
            f"Verify {script_name}.timer is active",
            V,
            StepKind.VERIFY,
            command=is_active(f"{script_name}.timer"),
            tags=["backup_job", "verify"],
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
                command=_encode_check_command(check, spec),
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
                "update_backup_job_metadata",
                f"Update backup_job metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_backup_job_run",
                "Record backup_job run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _plan_systemd_unit(spec: SystemdUnitSpec, ctx: NormalizedContext) -> list[Step]:
    """Generate steps for deploying a systemd service unit."""
    from nodeforge.runtime.steps.systemd import (
        daemon_reload,
        enable_unit,
        is_active,
        render_logrotate_config,
        render_service_unit,
        restart_unit,
    )

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    u = spec.unit
    unit_file = f"/etc/systemd/system/{u.unit_name}.service"

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

    # Write unit file
    unit_content = render_service_unit(
        description=u.description or spec.meta.description or u.unit_name,
        exec_start=u.exec_start,
        exec_stop=u.exec_stop,
        working_directory=u.working_directory,
        user=u.user,
        group=u.group,
        restart=u.restart,
        restart_sec=u.restart_sec,
        after=u.after,
        environment=u.environment,
        environment_file=u.environment_file,
        service_type=u.type,
        wanted_by=u.wanted_by,
    )

    steps.append(
        _s(
            f"write_unit_{u.unit_name}",
            f"Write systemd unit file {unit_file}",
            R,
            StepKind.SSH_UPLOAD,
            file_content=unit_content,
            target_path=unit_file,
            sudo=True,
            tags=["systemd_unit", "upload"],
        )
    )

    # Daemon reload
    steps.append(
        _s(
            "systemd_daemon_reload",
            "Reload systemd daemon",
            R,
            StepKind.SSH_COMMAND,
            command=daemon_reload(),
            sudo=True,
            tags=["systemd_unit", "always"],
        )
    )

    # Enable
    steps.append(
        _s(
            f"enable_{u.unit_name}",
            f"Enable {u.unit_name}.service",
            R,
            StepKind.SSH_COMMAND,
            command=enable_unit(u.unit_name),
            sudo=True,
            tags=["systemd_unit"],
        )
    )

    # Restart
    steps.append(
        _s(
            f"restart_{u.unit_name}",
            f"Restart {u.unit_name}.service",
            R,
            StepKind.SSH_COMMAND,
            command=restart_unit(u.unit_name),
            sudo=True,
            tags=["systemd_unit", "always"],
        )
    )

    # Verify active
    steps.append(
        _s(
            f"verify_{u.unit_name}_active",
            f"Verify {u.unit_name}.service is active",
            V,
            StepKind.VERIFY,
            command=is_active(u.unit_name),
            tags=["systemd_unit", "verify"],
        )
    )

    # Optional logrotate
    lr = spec.logrotate
    if lr and lr.enabled:
        logrotate_content = render_logrotate_config(
            name=u.unit_name,
            path=lr.path,
            rotate=lr.rotate,
            frequency=lr.frequency,
            compress=lr.compress,
            max_size=lr.max_size,
        )
        steps.append(
            _s(
                f"write_logrotate_{u.unit_name}",
                f"Write logrotate config for {u.unit_name}",
                R,
                StepKind.SSH_UPLOAD,
                file_content=logrotate_content,
                target_path=f"/etc/logrotate.d/nodeforge-{u.unit_name}",
                sudo=True,
                tags=["systemd_unit", "logrotate"],
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
                command=_encode_check_command(check, spec),
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
                "update_systemd_unit_metadata",
                f"Update systemd_unit metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_systemd_unit_run",
                "Record systemd_unit run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _plan_systemd_timer(spec: SystemdTimerSpec, ctx: NormalizedContext) -> list[Step]:
    """Generate steps for deploying a systemd timer with companion oneshot service."""
    from nodeforge.runtime.steps.systemd import (
        daemon_reload,
        enable_now_unit,
        is_active,
        render_service_unit,
        render_timer_unit,
    )

    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    t = spec.timer
    s = spec.service

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

    # Write companion .service (Type=oneshot)
    service_content = render_service_unit(
        description=t.description or f"Service for timer {t.timer_name}",
        exec_start=s.exec_start,
        working_directory=s.working_directory,
        user=s.user,
        group=s.group,
        restart="no",
        restart_sec=0,
        environment=s.environment,
        service_type="oneshot",
        wanted_by="",
    )
    service_file = f"/etc/systemd/system/{t.timer_name}.service"
    steps.append(
        _s(
            f"write_service_{t.timer_name}",
            f"Write companion service file {service_file}",
            R,
            StepKind.SSH_UPLOAD,
            file_content=service_content,
            target_path=service_file,
            sudo=True,
            tags=["systemd_timer", "upload"],
        )
    )

    # Write .timer
    timer_content = render_timer_unit(
        description=t.description or f"Timer for {t.timer_name}",
        on_calendar=t.on_calendar,
        persistent=t.persistent,
        accuracy_sec=t.accuracy_sec,
    )
    timer_file = f"/etc/systemd/system/{t.timer_name}.timer"
    steps.append(
        _s(
            f"write_timer_{t.timer_name}",
            f"Write timer unit file {timer_file}",
            R,
            StepKind.SSH_UPLOAD,
            file_content=timer_content,
            target_path=timer_file,
            sudo=True,
            tags=["systemd_timer", "upload"],
        )
    )

    # Daemon reload
    steps.append(
        _s(
            "systemd_daemon_reload",
            "Reload systemd daemon",
            R,
            StepKind.SSH_COMMAND,
            command=daemon_reload(),
            sudo=True,
            tags=["systemd_timer", "always"],
        )
    )

    # Enable and start timer
    steps.append(
        _s(
            f"enable_start_{t.timer_name}_timer",
            f"Enable and start {t.timer_name}.timer",
            R,
            StepKind.SSH_COMMAND,
            command=enable_now_unit(f"{t.timer_name}.timer"),
            sudo=True,
            tags=["systemd_timer", "always"],
        )
    )

    # Verify timer active
    steps.append(
        _s(
            f"verify_{t.timer_name}_timer_active",
            f"Verify {t.timer_name}.timer is active",
            V,
            StepKind.VERIFY,
            command=is_active(f"{t.timer_name}.timer"),
            tags=["systemd_timer", "verify"],
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
                command=_encode_check_command(check, spec),
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
                "update_systemd_timer_metadata",
                f"Update systemd_timer metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_systemd_timer_run",
                "Record systemd_timer run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _plan_http_check(spec: HttpCheckSpec, ctx: NormalizedContext) -> list[Step]:
    """Generate steps for a GET-only HTTP readiness probe."""
    steps: list[Step] = []
    R = StepScope.REMOTE
    L = StepScope.LOCAL
    V = StepScope.VERIFY

    c = spec.check

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

    # HTTP check gate — executed by agent with retry loop
    steps.append(
        _s(
            "http_check_gate",
            f"HTTP readiness check: GET {c.url} expecting {c.expected_status}",
            R,
            StepKind.GATE,
            command=f"http_check:{c.url}:{c.expected_status}:{c.retries}:{c.interval}:{c.timeout}",
            gate=True,
            tags=["http_check", "always"],
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
                command=_encode_check_command(check, spec),
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
                "update_http_check_metadata",
                f"Update http_check metadata in inventory for {spec.host.name}",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="upsert_services",
                tags=["local", "inventory"],
            )
        )
        steps.append(
            _s(
                "record_http_check_run",
                "Record http_check run metadata in inventory",
                L,
                StepKind.LOCAL_DB_WRITE,
                command="record_run",
                tags=["local", "inventory"],
            )
        )

    return steps


def _topo_sort(resources) -> list:
    """Topologically sort stack resources by depends_on.

    Returns resources in dependency-first order.
    """
    name_to_res = {r.name: r for r in resources}
    visited: set[str] = set()
    result: list = []

    def _visit(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        res = name_to_res.get(name)
        if res is None:
            return
        for dep in res.depends_on:
            _visit(dep)
        result.append(res)

    for r in resources:
        _visit(r.name)

    return result
