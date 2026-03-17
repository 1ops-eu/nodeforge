"""Pydantic v2 models for kind: bootstrap YAML specs (RFC section 7)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class MetaBlock(BaseModel):
    name: str
    description: str = ""


class HostBlock(BaseModel):
    name: str
    address: str
    os_family: str = "debian"


class LoginBlock(BaseModel):
    user: str = "root"
    private_key: str = "~/.ssh/id_ed25519"
    password: Optional[str] = None
    port: int = 22


class AdminUserBlock(BaseModel):
    name: str = "admin"
    groups: list[str] = Field(default_factory=lambda: ["sudo"])
    pubkeys: list[str] = Field(default_factory=list)


class SSHBlock(BaseModel):
    port: int = 2222
    disable_root_login: bool = True
    disable_password_auth: bool = False


class FirewallBlock(BaseModel):
    provider: str = "ufw"
    ssh_only: bool = True
    registered_peers_only: bool = False
    # When wireguard.enabled=true and registered_peers_only=true:
    #   SSH is restricted to the declared peer IP only (in on wg0 from {peer_ip} to any port {ssh_port})
    # When wireguard.enabled=true and registered_peers_only=false (default):
    #   SSH is restricted to the WireGuard interface only (in on wg0 to any port {ssh_port})
    # Has no effect when wireguard.enabled=false.


class WireGuardBlock(BaseModel):
    enabled: bool = False
    interface: str = "wg0"
    address: str = ""  # server VPN interface CIDR, e.g. 10.10.0.1/24
    private_key_file: str = ""  # path to server's Curve25519 private key file
    endpoint: str = ""  # server's public endpoint, e.g. 192.168.56.10:51820
    peer_address: str = ""  # client/peer VPN IP CIDR, e.g. 10.10.0.2/32
    persistent_keepalive: int = 25


class SSHConfigBlock(BaseModel):
    enabled: bool = True
    host_alias: str = ""
    config_path: str = "~/.ssh/config"


class InventoryBlock(BaseModel):
    enabled: bool = True
    db_path: str = "~/.nodeforge/inventory.db"


class LocalBlock(BaseModel):
    state_dir: str = ""
    ssh_config: SSHConfigBlock = Field(default_factory=SSHConfigBlock)
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class CheckBlock(BaseModel):
    type: str
    port: int | None = None
    user: str | None = None
    interface: str | None = None
    host: str | None = None


class BootstrapSpec(BaseModel):
    kind: Literal["bootstrap"]
    meta: MetaBlock
    host: HostBlock
    login: LoginBlock = Field(default_factory=LoginBlock)
    admin_user: AdminUserBlock = Field(default_factory=AdminUserBlock)
    ssh: SSHBlock = Field(default_factory=SSHBlock)
    firewall: FirewallBlock = Field(default_factory=FirewallBlock)
    wireguard: WireGuardBlock = Field(default_factory=WireGuardBlock)
    local: LocalBlock = Field(default_factory=LocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
