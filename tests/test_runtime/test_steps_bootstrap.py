"""Tests for bootstrap step command template correctness."""

from loft_cli.runtime.steps.bootstrap import (
    allow_ssh_on_wireguard,
    create_admin_user,
    delete_open_ssh_rule,
    disable_password_auth,
    disable_root_login,
    enable_pubkey_auth,
    install_authorized_keys,
    reload_sshd,
    ufw_default_allow_outgoing,
    ufw_default_deny_incoming,
    ufw_force_enable,
    write_sshd_config_candidate,
)
from loft_cli.runtime.steps.wireguard import (
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


def test_enable_pubkey_auth_command():
    cmd = enable_pubkey_auth()
    assert "PubkeyAuthentication yes" in cmd
    assert "sshd_config" in cmd


def test_enable_pubkey_auth_socket_aware():
    """enable_pubkey_auth handles Ubuntu 24.04+ socket-activated sshd."""
    cmd = enable_pubkey_auth()
    assert "ssh.socket" in cmd
    assert "daemon-reload" in cmd


def test_sshd_config_candidate_includes_port():
    cmd = write_sshd_config_candidate(2222)
    assert "2222" in cmd
    assert "sshd_config.bak" in cmd


def test_sshd_config_candidate_appends_when_missing():
    """Port line is appended if no Port directive exists in sshd_config."""
    cmd = write_sshd_config_candidate(1677)
    assert "1677" in cmd
    # grep+sed+append pattern: falls back to echo if sed has no match
    assert "grep" in cmd
    assert "echo" in cmd


def test_ufw_default_deny_incoming():
    cmd = ufw_default_deny_incoming()
    assert "default deny incoming" in cmd


def test_ufw_default_allow_outgoing():
    cmd = ufw_default_allow_outgoing()
    assert "default allow outgoing" in cmd


def test_ufw_force_enable():
    cmd = ufw_force_enable()
    assert "ufw --force enable" in cmd


def test_reload_sshd():
    cmd = reload_sshd()
    assert "systemctl" in cmd
    assert "ssh" in cmd


def test_reload_sshd_socket_aware():
    """reload_sshd handles Ubuntu 24.04+ socket-activated sshd."""
    cmd = reload_sshd()
    # Must detect ssh.socket and use daemon-reload + restart ssh.socket
    assert "ssh.socket" in cmd
    assert "daemon-reload" in cmd
    # Must fall back to traditional reload on non-socket systems
    assert "systemctl reload ssh" in cmd


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


def test_allow_ssh_on_wireguard_interface_only():
    """registered_peers_only=False: restrict SSH to wg0 interface, any peer."""
    cmd = allow_ssh_on_wireguard(2222, "wg0", peer_ip=None)
    assert "in on wg0" in cmd
    assert "from" not in cmd
    assert "to any port 2222 proto tcp" in cmd


def test_delete_open_ssh_rule():
    """Deletes the temporary open-to-all SSH rule."""
    cmd = delete_open_ssh_rule(2222)
    assert "ufw delete allow 2222/tcp" in cmd


def test_allow_ssh_on_wireguard_specific_peer():
    """registered_peers_only=True: restrict SSH to wg0 interface AND specific peer IP."""
    cmd = allow_ssh_on_wireguard(2222, "wg0", peer_ip="10.10.0.2")
    assert "in on wg0 from 10.10.0.2" in cmd
    assert "to any port 2222 proto tcp" in cmd


def test_allow_ssh_on_wireguard_custom_port():
    """Works with non-standard SSH ports."""
    cmd = allow_ssh_on_wireguard(2222, "wg0", peer_ip="10.10.0.2")
    assert "port 2222" in cmd
