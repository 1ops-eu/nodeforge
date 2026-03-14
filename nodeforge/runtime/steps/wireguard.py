"""WireGuard installation and configuration commands."""
from __future__ import annotations


def install_wireguard() -> str:
    return "DEBIAN_FRONTEND=noninteractive apt-get install -y wireguard"


def generate_wireguard_config(
    interface: str,
    address: str,
    private_key: str,
    server_public_key: str,
    endpoint: str,
    allowed_ips: list[str],
    persistent_keepalive: int = 25,
) -> str:
    """Generate /etc/wireguard/{interface}.conf content."""
    allowed = ", ".join(allowed_ips)
    return f"""\
[Interface]
Address = {address}
PrivateKey = {private_key}

[Peer]
PublicKey = {server_public_key}
Endpoint = {endpoint}
AllowedIPs = {allowed}
PersistentKeepalive = {persistent_keepalive}
"""


def enable_wireguard(interface: str) -> str:
    return f"systemctl enable --now wg-quick@{interface}"


def verify_wireguard(interface: str) -> str:
    return f"wg show {interface}"


def set_wireguard_dir_permissions() -> str:
    return "chmod 700 /etc/wireguard"
