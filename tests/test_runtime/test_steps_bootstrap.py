"""Tests for bootstrap step command template correctness."""

from nodeforge.runtime.steps.bootstrap import (
    create_admin_user,
    disable_password_auth,
    disable_root_login,
    finalize_firewall,
    install_authorized_keys,
    reload_sshd,
    restrict_ssh_to_wireguard,
    write_sshd_config_candidate,
)
from nodeforge.runtime.steps.wireguard import (
    enable_wireguard,
    generate_client_config,
    generate_server_config,
)


def test_create_admin_user_idempotent():
    cmd = create_admin_user("deploy", ["sudo"])
    assert "id deploy" in cmd
    assert "adduser" in cmd
    assert "usermod" in cmd


def test_create_admin_user_groups():
    cmd = create_admin_user("deploy", ["sudo", "docker"])
    assert "sudo,docker" in cmd


def test_install_authorized_keys():
    cmd = install_authorized_keys("deploy", "ssh-ed25519 AAAAA test@host")
    assert "/home/deploy/.ssh" in cmd
    assert "authorized_keys" in cmd
    assert "chmod 700" in cmd
    assert "chmod 600" in cmd


def test_disable_root_login_command():
    cmd = disable_root_login()
    assert "PermitRootLogin no" in cmd
    assert "sshd_config" in cmd


def test_disable_password_auth_command():
    cmd = disable_password_auth()
    assert "PasswordAuthentication no" in cmd
    assert "sshd_config" in cmd


def test_sshd_config_candidate_includes_port():
    cmd = write_sshd_config_candidate(2222)
    assert "2222" in cmd
    assert "sshd_config.bak" in cmd


def test_finalize_firewall():
    cmd = finalize_firewall()
    assert "default deny incoming" in cmd
    assert "ufw --force enable" in cmd


def test_reload_sshd():
    cmd = reload_sshd()
    assert "systemctl reload" in cmd
    assert "ssh" in cmd


def test_generate_server_config():
    conf = generate_server_config(
        interface="wg0",
        address="10.0.0.1/24",
        private_key="SERVER_PRIVATE",
        listen_port=51820,
        client_public_key="CLIENT_PUBLIC",
        peer_address="10.0.0.2/32",
    )
    assert "[Interface]" in conf
    assert "Address = 10.0.0.1/24" in conf
    assert "ListenPort = 51820" in conf
    assert "PrivateKey = SERVER_PRIVATE" in conf
    assert "[Peer]" in conf
    assert "PublicKey = CLIENT_PUBLIC" in conf
    assert "AllowedIPs = 10.0.0.2/32" in conf
    # Server config must NOT have Endpoint (server listens, does not connect out)
    assert "Endpoint" not in conf


def test_generate_client_config():
    conf = generate_client_config(
        client_private_key="CLIENT_PRIVATE",
        peer_address="10.0.0.2/32",
        server_public_key="SERVER_PUBLIC",
        endpoint="vpn.example.com:51820",
        vpn_subnet="10.0.0.0/24",
        persistent_keepalive=25,
    )
    assert "[Interface]" in conf
    assert "PrivateKey = CLIENT_PRIVATE" in conf
    assert "Address = 10.0.0.2/32" in conf
    assert "[Peer]" in conf
    assert "PublicKey = SERVER_PUBLIC" in conf
    assert "Endpoint = vpn.example.com:51820" in conf
    assert "AllowedIPs = 10.0.0.0/24" in conf
    assert "PersistentKeepalive = 25" in conf


def test_enable_wireguard():
    cmd = enable_wireguard("wg0")
    assert "wg-quick@wg0" in cmd
    assert "enable" in cmd


def test_restrict_ssh_to_wireguard_interface_only():
    """registered_peers_only=False: restrict SSH to wg0 interface, any peer."""
    cmd = restrict_ssh_to_wireguard(2222, "wg0", peer_ip=None)
    assert "in on wg0" in cmd
    assert "from" not in cmd
    assert "to any port 2222 proto tcp" in cmd
    assert "ufw delete allow 2222/tcp" in cmd


def test_restrict_ssh_to_wireguard_specific_peer():
    """registered_peers_only=True: restrict SSH to wg0 interface AND specific peer IP."""
    cmd = restrict_ssh_to_wireguard(2222, "wg0", peer_ip="10.10.0.2")
    assert "in on wg0 from 10.10.0.2" in cmd
    assert "to any port 2222 proto tcp" in cmd
    assert "ufw delete allow 2222/tcp" in cmd


def test_restrict_ssh_to_wireguard_custom_port():
    """Works with non-standard SSH ports."""
    cmd = restrict_ssh_to_wireguard(2222, "wg0", peer_ip="10.10.0.2")
    assert "port 2222" in cmd
    assert "ufw delete allow 2222/tcp" in cmd
