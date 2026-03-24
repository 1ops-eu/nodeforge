"""Pydantic v2 models for kind: backup_job YAML specs.

Define host-local backup operations with retention semantics.
The planner generates a backup shell script and a systemd timer
to run it on schedule.
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


class BackupSource(BaseModel):
    """Source definition for backup operations."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["postgres_dump", "directory"]
    # postgres_dump fields
    database: str | None = None
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    docker_exec: str | None = None  # container name for docker exec
    # directory fields
    path: str | None = None


class BackupDestination(BaseModel):
    """Destination for backup files."""

    model_config = ConfigDict(extra="forbid")

    path: str  # local directory for backups


class BackupRetention(BaseModel):
    """Retention policy for backups."""

    model_config = ConfigDict(extra="forbid")

    count: int = 7  # keep N most recent backups


class BackupJobConfig(BaseModel):
    """Configuration for a backup job."""

    model_config = ConfigDict(extra="forbid")

    name: str  # job name (used for script/timer naming)
    source: BackupSource
    destination: BackupDestination
    retention: BackupRetention = Field(default_factory=BackupRetention)
    schedule: str = "*-*-* 02:00:00"  # systemd OnCalendar expression


class BackupJobLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class BackupJobLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class BackupJobSpec(BaseModel):
    """Spec for defining backup operations with retention and scheduling."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["backup_job"]
    meta: MetaBlock
    host: HostBlock
    login: BackupJobLoginBlock = Field(default_factory=BackupJobLoginBlock)
    backup: BackupJobConfig
    local: BackupJobLocalBlock = Field(default_factory=BackupJobLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
