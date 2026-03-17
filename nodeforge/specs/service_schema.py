"""Pydantic v2 models for kind: service YAML specs (RFC section 8)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from nodeforge.specs.bootstrap_schema import (
    CheckBlock,
    HostBlock,
    InventoryBlock,
    MetaBlock,
)


class ServiceLoginBlock(BaseModel):
    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: Optional[str] = None
    port: int = 2222


class CreateRoleBlock(BaseModel):
    name: str
    password_env: str = ""


class CreateDatabaseBlock(BaseModel):
    name: str
    owner: str = ""


class PostgresBlock(BaseModel):
    enabled: bool = True
    version: str = "16"
    listen_addresses: list[str] = Field(default_factory=lambda: ["127.0.0.1"])
    create_role: CreateRoleBlock | None = None
    create_database: CreateDatabaseBlock | None = None


class DockerBlock(BaseModel):
    enabled: bool = True


class HealthCheckBlock(BaseModel):
    type: str = "http"
    url: str = ""
    expect_status: int = 200


class ContainerBlock(BaseModel):
    name: str
    image: str
    ports: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    env_file: str | None = None
    restart: str = "unless-stopped"
    healthcheck: HealthCheckBlock | None = None


class ServiceLocalBlock(BaseModel):
    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class ServiceSpec(BaseModel):
    kind: Literal["service"]
    meta: MetaBlock
    host: HostBlock
    login: ServiceLoginBlock = Field(default_factory=ServiceLoginBlock)
    postgres: PostgresBlock | None = None
    docker: DockerBlock | None = None
    containers: list[ContainerBlock] = Field(default_factory=list)
    local: ServiceLocalBlock = Field(default_factory=ServiceLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
