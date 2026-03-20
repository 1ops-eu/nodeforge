"""WireGuard installation and configuration commands."""

from __future__ import annotations


def install_wireguard() -> str:
    return "DEBIAN_FRONTEND=noninteractive apt-get install -y wireguard"


def generate_server_config(
    interface: str,
    address: str,
    private_key: str,
    listen_port: int,
    client_public_key: str,
    peer_address: str,
) -> str:
    """Generate the server-side /etc/wireguard/{interface}.conf.

    The server listens on ``listen_port`` and allows traffic from the peer
    whose public key is ``client_public_key`` at VPN address ``peer_address``.
    """
    return f"""\
[Interface]
Address = {address}
ListenPort = {listen_port}
PrivateKey = {private_key}

[Peer]
PublicKey = {client_public_key}
AllowedIPs = {peer_address}
"""


def generate_client_config(
    client_private_key: str,
    peer_address: str,
    server_public_key: str,
    endpoint: str,
    vpn_subnet: str,
    persistent_keepalive: int = 25,
) -> str:
    """Generate the local client wg-quick config saved to ~/.wg/nodeforge/{host}/client.conf.

    ``vpn_subnet`` is the full VPN network CIDR (e.g. ``10.10.0.0/24``) derived
    from the server's interface address — traffic to that subnet is routed
    through the tunnel.
    ``server_public_key`` is derived from the server's private key via PyNaCl.
    """
    return f"""\
[Interface]
PrivateKey = {client_private_key}
Address = {peer_address}

[Peer]
PublicKey = {server_public_key}
Endpoint = {endpoint}
AllowedIPs = {vpn_subnet}
PersistentKeepalive = {persistent_keepalive}
"""


def load_wireguard_module() -> str:
    return "modprobe wireguard"


def enable_wireguard(interface: str) -> str:
    return f"systemctl enable wg-quick@{interface} && wg-quick up {interface}"


def verify_wireguard(interface: str) -> str:
    return f"wg show {interface}"


def set_wireguard_dir_permissions() -> str:
    return "chmod 700 /etc/wireguard"
