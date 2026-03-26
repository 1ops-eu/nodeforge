"""Pydantic v2 models for kind: service YAML specs (RFC section 8)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from loft_cli_core.specs.bootstrap_schema import (
    CheckBlock,
    HostBlock,
    InventoryBlock,
    MetaBlock,
)


class ServiceLoginBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class CreateRoleBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    password_env: str = ""


class CreateDatabaseBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    owner: str = ""


class PostgresBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    version: str = "16"
    listen_addresses: list[str] = Field(default_factory=lambda: ["127.0.0.1"])
    create_role: CreateRoleBlock | None = None
    create_database: CreateDatabaseBlock | None = None


class NginxSiteBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str
    upstream: str = ""
    upstream_port: int = 8080
    listen_port: int = 80
    ssl: bool = False
    ssl_certificate: str = ""
    ssl_certificate_key: str = ""


class NginxBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    sites: list[NginxSiteBlock] = Field(default_factory=list)


class DockerBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class HealthCheckBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "http"
    url: str = ""
    expect_status: int = 200


class ContainerBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    image: str
    ports: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    env_file: str | None = None
    restart: str = "unless-stopped"
    healthcheck: HealthCheckBlock | None = None


class ServiceLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class ServiceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["service"]
    meta: MetaBlock
    host: HostBlock
    login: ServiceLoginBlock = Field(default_factory=ServiceLoginBlock)
    postgres: PostgresBlock | None = None
    nginx: NginxBlock | None = None
    docker: DockerBlock | None = None
    containers: list[ContainerBlock] = Field(default_factory=list)
    local: ServiceLocalBlock = Field(default_factory=ServiceLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
