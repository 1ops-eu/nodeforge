"""Shell command templates for bootstrap steps.

Adapted from vm_wizard/fab_infra/tasks/user/bootstrap_admin_user/bootstrap_admin_user.py.
All functions return shell command strings consumed by the executor.
"""

from __future__ import annotations


def apt_update() -> str:
    return "apt-get update -y 2>&1 | tail -3"


def apt_upgrade() -> str:
    return "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y 2>&1 | tail -5"


def install_packages(packages: list[str]) -> str:
    pkg_list = " ".join(packages)
    return f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_list}"


def delete_non_system_users(admin_username: str) -> str:
    """Remove non-system users (UID 1000-65533) except the admin user.

    Awk pattern from vm_wizard bootstrap_admin_user.py lines 111-114.
    """
    return (
        "awk -F: '$3 >= 1000 && $3 < 65534 && $1 != \""
        + admin_username
        + "\" {print $1}' /etc/passwd | while read u; do userdel -r $u 2>&1; done"
    )


def create_admin_user(username: str, groups: list[str]) -> str:
    """Create admin user idempotently and add to specified groups."""
    group_str = ",".join(groups) if groups else "sudo"
    cmds = [
        f"getent group {username} >/dev/null 2>&1 || addgroup {username}",
        f"id {username} >/dev/null 2>&1 || adduser --disabled-password --gecos '' --ingroup {username} {username}",
        f"usermod -aG {group_str} {username}",
    ]
    return " && ".join(cmds)


def set_admin_password(username: str, password: str) -> str:
    return f"echo '{username}:{password}' | chpasswd"


def nopasswd_sudoers(username: str) -> str:
    return f"echo '{username} ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/{username}"


def secure_sudoers(username: str) -> str:
    return f"chmod 440 /etc/sudoers.d/{username}"


def install_authorized_keys(username: str, pubkey_content: str) -> str:
    """Install SSH authorized_keys for admin user."""
    # Use printf to safely write the key content
    escaped = pubkey_content.replace("'", "'\\''")
    return (
        f"mkdir -p /home/{username}/.ssh && "
        f"printf '%s\\n' '{escaped}' >> /home/{username}/.ssh/authorized_keys && "
        f"chmod 700 /home/{username}/.ssh && "
        f"chmod 600 /home/{username}/.ssh/authorized_keys && "
        f"chown -R {username}:{username} /home/{username}/.ssh"
    )


def enable_pubkey_auth() -> str:
    """Ensure PubkeyAuthentication yes is active so admin key login can succeed.

    Some distro images ship with PubkeyAuthentication no. We must enable it and
    reload sshd before running the admin-login gate, otherwise key auth never works.
    The grep+sed pattern handles commented, uncommented, or missing lines.
    """
    return (
        "grep -q '^#\\?PubkeyAuthentication' /etc/ssh/sshd_config "
        "&& sed -i 's/^#\\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config "
        "|| echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config && "
        "systemctl reload ssh || systemctl reload sshd"
    )


def write_sshd_config_candidate(port: int) -> str:
    """Configure SSH port. Root login and password auth are deferred until gate passes."""
    return (
        "cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak && "
        f"sed -i 's/^#\\?Port .*/Port {port}/' /etc/ssh/sshd_config"
    )


def validate_sshd_config() -> str:
    return "sshd -t"


def reload_sshd() -> str:
    return "systemctl reload ssh || systemctl reload sshd"


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


def finalize_firewall() -> str:
    return "ufw default deny incoming && ufw default allow outgoing && ufw --force enable"


def restrict_ssh_to_wireguard(
    ssh_port: int,
    wg_interface: str,
    peer_ip: str | None = None,
) -> str:
    """Atomically switch the SSH firewall rule from open-to-all to WireGuard-only.

    Adds a WireGuard-restricted SSH allow rule, then removes the temporary
    open-to-all rule that was created during apply setup.

    When peer_ip is set (firewall.registered_peers_only=true):
        ufw allow in on {wg_interface} from {peer_ip} to any port {ssh_port} proto tcp
    When peer_ip is None (registered_peers_only=false, default):
        ufw allow in on {wg_interface} to any port {ssh_port} proto tcp

    MUST be the last remote SSH step — after this executes, direct SSH to
    spec.host.address stops working. All subsequent steps must be LOCAL.
    """
    from_clause = f"from {peer_ip} " if peer_ip else ""
    return (
        f"ufw allow in on {wg_interface} {from_clause}to any port {ssh_port} proto tcp && "
        f"ufw delete allow {ssh_port}/tcp"
    )
