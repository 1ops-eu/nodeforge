"""Pydantic v2 models for kind: bootstrap YAML specs (RFC section 7)."""
from __future__ import annotations

from typing import Literal

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
    port: int = 22


class AdminUserBlock(BaseModel):
    name: str = "admin"
    groups: list[str] = Field(default_factory=lambda: ["sudo"])
    pubkeys: list[str] = Field(default_factory=list)


class SSHBlock(BaseModel):
    port: int = 2222
    disable_root_login: bool = True
    disable_password_auth: bool = True


class FirewallBlock(BaseModel):
    provider: str = "ufw"
    ssh_only: bool = True


class WireGuardBlock(BaseModel):
    enabled: bool = False
    interface: str = "wg0"
    address: str = ""
    private_key_file: str = ""
    server_public_key: str = ""
    endpoint: str = ""
    allowed_ips: list[str] = Field(default_factory=list)
    persistent_keepalive: int = 25


class SSHConfigBlock(BaseModel):
    enabled: bool = True
    host_alias: str = ""
    config_path: str = "~/.ssh/config"
    preserve_legacy_entry: bool = False


class InventoryBlock(BaseModel):
    enabled: bool = True
    db_path: str = "~/.nodeforge/inventory.db"
    key_source: str = "env"
    key_env: str = "NODEFORGE_SQLCIPHER_KEY"


class LocalBlock(BaseModel):
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
