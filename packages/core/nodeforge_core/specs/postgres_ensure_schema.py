"""Pydantic v2 models for kind: postgres_ensure YAML specs.

Ensure PostgreSQL resources exist on a running instance (container via
docker exec or host/port).  Structured declarations only: users,
databases, extensions, grants.  Every action appears as a discrete,
reviewable plan step.  No arbitrary SQL passthrough.
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


class PgConnection(BaseModel):
    """Connection parameters for the PostgreSQL instance."""

    model_config = ConfigDict(extra="forbid")

    host: str = "localhost"
    port: int = 5432
    admin_user: str = "postgres"
    docker_exec: str | None = None  # container name for docker exec


class PgUser(BaseModel):
    """A PostgreSQL user/role to ensure exists."""

    model_config = ConfigDict(extra="forbid")

    name: str
    password_env: str | None = None  # env var holding password (resolved at plan time)


class PgDatabase(BaseModel):
    """A PostgreSQL database to ensure exists."""

    model_config = ConfigDict(extra="forbid")

    name: str
    owner: str = "postgres"


class PgExtension(BaseModel):
    """A PostgreSQL extension to ensure is installed."""

    model_config = ConfigDict(extra="forbid")

    name: str
    database: str


class PgGrant(BaseModel):
    """A PostgreSQL privilege grant."""

    model_config = ConfigDict(extra="forbid")

    privilege: str  # ALL, SELECT, INSERT, etc.
    on_database: str
    to_user: str


class PostgresEnsureLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class PostgresEnsureLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class PostgresEnsureSpec(BaseModel):
    """Spec for ensuring PostgreSQL resources exist on a running instance."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["postgres_ensure"]
    meta: MetaBlock
    host: HostBlock
    login: PostgresEnsureLoginBlock = Field(default_factory=PostgresEnsureLoginBlock)
    connection: PgConnection = Field(default_factory=PgConnection)
    users: list[PgUser] = Field(default_factory=list)
    databases: list[PgDatabase] = Field(default_factory=list)
    extensions: list[PgExtension] = Field(default_factory=list)
    grants: list[PgGrant] = Field(default_factory=list)
    local: PostgresEnsureLocalBlock = Field(default_factory=PostgresEnsureLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
