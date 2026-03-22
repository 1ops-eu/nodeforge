"""Pydantic v2 models for kind: compose_project YAML specs.

Manages Docker Compose projects: upload compose file and templates,
pull images, start the stack, and verify container health.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from nodeforge_core.specs.bootstrap_schema import (
    CheckBlock,
    HostBlock,
    InventoryBlock,
    MetaBlock,
)


class ComposeTemplateBlock(BaseModel):
    """A file to render from a Jinja2 template and upload into the project directory."""

    model_config = ConfigDict(extra="forbid")

    src: str  # local Jinja2 template path (spec-relative)
    dest: str  # filename relative to project directory


class ManagedDirectoryBlock(BaseModel):
    """An additional directory to create under (or outside) the project root."""

    model_config = ConfigDict(extra="forbid")

    path: str  # relative to project directory (or absolute)
    mode: str = "0755"
    owner: str = "root"
    group: str = "root"


class ComposeHealthCheckBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    timeout: int = 120  # total seconds to wait for all containers healthy
    interval: int = 5  # seconds between polls


class ComposeProjectLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class ComposeProjectLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class ComposeProjectBlock(BaseModel):
    """The core project configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str  # docker compose project name
    directory: str  # remote base directory (absolute)
    compose_file: str = "docker-compose.yml"  # compose filename (in project dir or spec-relative)
    templates: list[ComposeTemplateBlock] = Field(default_factory=list)
    variables: dict[str, str] = Field(default_factory=dict)
    directories: list[ManagedDirectoryBlock] = Field(default_factory=list)
    pull_before_up: bool = True
    healthcheck: ComposeHealthCheckBlock = Field(default_factory=ComposeHealthCheckBlock)


class ComposeProjectSpec(BaseModel):
    """Spec for deploying a Docker Compose project on a remote host."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["compose_project"]
    meta: MetaBlock
    host: HostBlock
    login: ComposeProjectLoginBlock = Field(default_factory=ComposeProjectLoginBlock)
    project: ComposeProjectBlock
    local: ComposeProjectLocalBlock = Field(default_factory=ComposeProjectLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
