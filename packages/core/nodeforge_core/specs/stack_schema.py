"""Pydantic v2 models for kind: stack YAML specs.

A stack groups related resources (file_template, compose_project, etc.)
into a single deployable application boundary.  Stack members are
declared inline and executed in dependency order.

Design principles
-----------------
- Stacks expand into normal resource steps during planning.
- Operators still see the final concrete plan (no opaque magic bundles).
- Circular dependencies are rejected at validation time.
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


class StackLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class StackLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class StackResourceBlock(BaseModel):
    """A single resource within a stack.

    Each resource references a spec kind (file_template, compose_project,
    etc.) and carries its kind-specific configuration inline.  Optional
    ``depends_on`` declares ordering dependencies between resources in
    the same stack.
    """

    model_config = ConfigDict(extra="forbid")

    name: str  # unique within the stack, e.g. "traefik-config"
    kind: str  # the spec kind: "file_template", "compose_project", etc.
    config: dict = Field(default_factory=dict)  # kind-specific config block
    depends_on: list[str] = Field(default_factory=list)  # other resource names


class StackSpec(BaseModel):
    """Spec for deploying a stack of related resources on a single host."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["stack"]
    meta: MetaBlock
    host: HostBlock
    login: StackLoginBlock = Field(default_factory=StackLoginBlock)
    local: StackLocalBlock = Field(default_factory=StackLocalBlock)
    resources: list[StackResourceBlock] = Field(default_factory=list)
    checks: list[CheckBlock] = Field(default_factory=list)
