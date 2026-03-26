"""Pydantic v2 models for kind: systemd_unit YAML specs.

Deploy and manage host-native systemd services.  The planner generates
a complete .service unit file from structured declarations, writes it
to /etc/systemd/system/, and runs daemon-reload + enable + start.
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


class SystemdUnitConfig(BaseModel):
    """Configuration for a systemd service unit."""

    model_config = ConfigDict(extra="forbid")

    unit_name: str  # service name (without .service suffix)
    description: str = ""
    exec_start: str  # command to run
    exec_stop: str | None = None
    working_directory: str | None = None
    user: str = "root"
    group: str = "root"
    restart: str = "on-failure"  # no, always, on-failure, on-abnormal
    restart_sec: int = 5
    after: list[str] = Field(default_factory=lambda: ["network.target"])
    environment: dict[str, str] = Field(default_factory=dict)
    environment_file: str | None = None
    type: str = "simple"  # simple, forking, oneshot, notify
    wanted_by: str = "multi-user.target"


class LogRotateConfig(BaseModel):
    """Optional logrotate configuration for the service."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    path: str = ""  # log file path pattern (e.g. /var/log/myapp/*.log)
    rotate: int = 7
    frequency: str = "daily"  # daily, weekly, monthly
    compress: bool = True
    max_size: str = ""  # e.g. "100M" — rotate when log exceeds this size


class SystemdUnitLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class SystemdUnitLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class SystemdUnitSpec(BaseModel):
    """Spec for deploying and managing a host-native systemd service."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["systemd_unit"]
    meta: MetaBlock
    host: HostBlock
    login: SystemdUnitLoginBlock = Field(default_factory=SystemdUnitLoginBlock)
    unit: SystemdUnitConfig
    logrotate: LogRotateConfig | None = None
    local: SystemdUnitLocalBlock = Field(default_factory=SystemdUnitLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
