"""Pydantic v2 models for kind: http_check YAML specs.

GET-only HTTP readiness probe with configurable retry, backoff, and timeout.
Usable as a dependency gate in stacks — "proceed only when this URL returns
the expected status code".  No request bodies, no mutations, no response
templating.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from loft_cli_core.specs.bootstrap_schema import (
    CheckBlock,
    HostBlock,
    InventoryBlock,
    MetaBlock,
)


class HttpCheckConfig(BaseModel):
    """Configuration for a GET-only HTTP readiness probe."""

    model_config = ConfigDict(extra="forbid")

    url: str  # GET target URL
    expected_status: int = 200
    retries: int = 5  # number of attempts
    interval: int = 3  # seconds between retries
    timeout: int = 10  # per-request timeout in seconds


class HttpCheckLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class HttpCheckLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class HttpCheckSpec(BaseModel):
    """Spec for GET-only HTTP readiness checks, usable as stack dependency gates."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["http_check"]
    meta: MetaBlock
    host: HostBlock
    login: HttpCheckLoginBlock = Field(default_factory=HttpCheckLoginBlock)
    check: HttpCheckConfig
    local: HttpCheckLocalBlock = Field(default_factory=HttpCheckLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
