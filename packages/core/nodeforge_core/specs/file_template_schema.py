"""Pydantic v2 models for kind: file_template YAML specs.

Renders managed configuration files from Jinja2 templates and variables.
Templates are rendered at plan time — the full rendered content appears in
step.file_content, making plans fully reviewable and deterministic.
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


class TemplateFileBlock(BaseModel):
    """A single managed file rendered from a Jinja2 template."""

    model_config = ConfigDict(extra="forbid")

    src: str  # local template path (spec-relative)
    dest: str  # remote absolute destination path
    mode: str = "0644"  # file permissions (octal string)
    owner: str = "root"
    group: str = "root"


class FileTemplateLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class FileTemplateLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class FileTemplateSpec(BaseModel):
    """Spec for rendering and uploading managed configuration files."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["file_template"]
    meta: MetaBlock
    host: HostBlock
    login: FileTemplateLoginBlock = Field(default_factory=FileTemplateLoginBlock)
    templates: list[TemplateFileBlock]  # at least 1 required
    variables: dict[str, str] = Field(default_factory=dict)
    local: FileTemplateLocalBlock = Field(default_factory=FileTemplateLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
