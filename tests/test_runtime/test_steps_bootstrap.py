"""Tests for bootstrap step command template correctness."""
from nodeforge.runtime.steps.bootstrap import (
    create_admin_user,
    install_authorized_keys,
    disable_root_login,
    disable_password_auth,
    write_sshd_config_candidate,
    finalize_firewall,
    reload_sshd,
)
from nodeforge.runtime.steps.wireguard import generate_wireguard_config, enable_wireguard


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


def test_wireguard_config_generation():
    conf = generate_wireguard_config(
        interface="wg0",
        address="10.0.0.2/24",
        private_key="PRIVATE_KEY",
        server_public_key="PUBLIC_KEY",
        endpoint="vpn.example.com:51820",
        allowed_ips=["10.0.0.0/24"],
    )
    assert "[Interface]" in conf
    assert "Address = 10.0.0.2/24" in conf
    assert "PrivateKey = PRIVATE_KEY" in conf
    assert "[Peer]" in conf
    assert "PublicKey = PUBLIC_KEY" in conf
    assert "Endpoint = vpn.example.com:51820" in conf


def test_enable_wireguard():
    cmd = enable_wireguard("wg0")
    assert "wg-quick@wg0" in cmd
    assert "enable" in cmd
