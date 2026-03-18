"""Shell command templates for bootstrap steps.

Adapted from vm_wizard/fab_infra/tasks/user/bootstrap_admin_user/bootstrap_admin_user.py.
All functions return shell command strings consumed by the executor.

IMPORTANT — Fabric sudo() compatibility:
  Fabric's ``sudo()`` runs ``sudo -S -p '' <raw command>``.  Shell
  metacharacters that create a new command context (``&&``, ``||``, ``|``,
  ``>``, ``>>``) break out of the sudo elevation — only the first simple
  command runs as root.

  To work around this, every function that needs shell operators wraps the
  entire command string in ``bash -c '...'`` so that Fabric elevates the
  outer ``bash`` process and all inner commands inherit root privileges.

  Functions that are *logically separate operations* (e.g. firewall rules)
  are split into individual functions so the planner can emit one step per
  operation — no shell chaining required.
"""

from __future__ import annotations


def apt_update() -> str:
    return "bash -c 'apt-get update -y 2>&1 | tail -3'"


def apt_upgrade() -> str:
    return "bash -c 'DEBIAN_FRONTEND=noninteractive apt-get upgrade -y 2>&1 | tail -5'"


def install_packages(packages: list[str]) -> str:
    pkg_list = " ".join(packages)
    return f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_list}"


def delete_non_system_users(admin_username: str) -> str:
    """Remove non-system users (UID 1000-65533) except the admin user.

    Awk pattern from vm_wizard bootstrap_admin_user.py lines 111-114.
    Uses double-quoted ``bash -c`` with ``\\$`` to protect awk field
    references from shell expansion.
    """
    return (
        f'bash -c "awk -F: '
        f'\'\\$3 >= 1000 && \\$3 < 65534 && \\$1 != \\"{admin_username}\\" '
        f"{{print \\$1}}' /etc/passwd "
        f'| while read u; do userdel -r \\$u 2>&1; done"'
    )


def create_admin_user(username: str, groups: list[str]) -> str:
    """Create admin user idempotently and add to specified groups."""
    group_str = ",".join(groups) if groups else "sudo"
    return (
        f"bash -c '"
        f"getent group {username} >/dev/null 2>&1 || addgroup {username} && "
        f'id {username} >/dev/null 2>&1 || adduser --disabled-password --gecos "" --ingroup {username} {username} && '
        f"usermod -aG {group_str} {username}"
        f"'"
    )


def set_admin_password(username: str, password: str) -> str:
    # Use single-quoted password inside double-quoted bash -c to prevent
    # shell expansion of special characters in the password.
    escaped_pw = password.replace("'", "'\\''")
    return f"bash -c \"echo '{username}:{escaped_pw}' | chpasswd\""


def nopasswd_sudoers(username: str) -> str:
    return f"bash -c 'echo \"{username} ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/{username}'"


def secure_sudoers(username: str) -> str:
    return f"chmod 440 /etc/sudoers.d/{username}"


def install_authorized_keys(username: str, pubkey_content: str) -> str:
    """Install SSH authorized_keys for admin user.

    The entire chain runs inside ``bash -c "..."`` so Fabric's sudo elevates
    everything.  We use double quotes for the outer wrapper so single quotes
    in the inner ``printf`` don't conflict.
    """
    inner = (
        f"mkdir -p /home/{username}/.ssh && "
        f"printf '%s\\n' '{pubkey_content}' >> /home/{username}/.ssh/authorized_keys && "
        f"chmod 700 /home/{username}/.ssh && "
        f"chmod 600 /home/{username}/.ssh/authorized_keys && "
        f"chown -R {username}:{username} /home/{username}/.ssh"
    )
    return f'bash -c "{inner}"'


def enable_pubkey_auth() -> str:
    """Ensure PubkeyAuthentication yes is active so admin key login can succeed.

    Some distro images ship with PubkeyAuthentication no. We must enable it and
    reload sshd before running the admin-login gate, otherwise key auth never works.
    The grep+sed pattern handles commented, uncommented, or missing lines.

    Uses double quotes for the outer ``bash -c`` to avoid conflicts with
    the single-quoted sed expressions inside.
    """
    return (
        'bash -c "'
        "grep -q '^#\\\\?PubkeyAuthentication' /etc/ssh/sshd_config "
        "&& sed -i 's/^#\\\\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config "
        "|| echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config; "
        'systemctl reload ssh || systemctl reload sshd"'
    )


def write_sshd_config_candidate(port: int) -> str:
    """Configure SSH port. Root login and password auth are deferred until gate passes."""
    return (
        f"bash -c '"
        f"cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak && "
        f'sed -i "s/^#\\?Port .*/Port {port}/" /etc/ssh/sshd_config'
        f"'"
    )


def validate_sshd_config() -> str:
    return "sshd -t"


def reload_sshd() -> str:
    return "bash -c 'systemctl reload ssh || systemctl reload sshd'"


def disable_root_login() -> str:
    """Disable root SSH login. MUST only run after gate (verify_admin_login_on_new_port)."""
    return r"sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config"


def disable_password_auth() -> str:
    """Disable password auth. MUST only run after gate (verify_admin_login_on_new_port)."""
    return (
        r"sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config"
    )


def open_firewall_port(port: int) -> str:
    return f"ufw allow {port}/tcp"


# ── Firewall finalization (split into individual steps) ──────────────
# Previously a single ``&&`` chain; now three separate functions so the
# planner emits one step per operation — no shell chaining required.


def ufw_default_deny_incoming() -> str:
    return "ufw default deny incoming"


def ufw_default_allow_outgoing() -> str:
    return "ufw default allow outgoing"


def ufw_force_enable() -> str:
    return "ufw --force enable"


# ── WireGuard SSH restriction (split into individual steps) ──────────
# Previously a single ``&&`` chain; now two separate functions.


def allow_ssh_on_wireguard(
    ssh_port: int,
    wg_interface: str,
    peer_ip: str | None = None,
) -> str:
    """Add a WireGuard-restricted SSH allow rule.

    When peer_ip is set (firewall.registered_peers_only=true):
        ufw allow in on {wg_interface} from {peer_ip} to any port {ssh_port} proto tcp
    When peer_ip is None (registered_peers_only=false, default):
        ufw allow in on {wg_interface} to any port {ssh_port} proto tcp
    """
    from_clause = f"from {peer_ip} " if peer_ip else ""
    return f"ufw allow in on {wg_interface} {from_clause}to any port {ssh_port} proto tcp"


def delete_open_ssh_rule(ssh_port: int) -> str:
    """Remove the temporary open-to-all SSH rule.

    MUST be the last remote SSH step — after this executes, direct SSH to
    spec.host.address stops working. All subsequent steps must be LOCAL.
    """
    return f"ufw delete allow {ssh_port}/tcp"
