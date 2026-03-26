"""Pydantic v2 models for kind: systemd_timer YAML specs.

Deploy scheduled execution via systemd timers.  The planner generates
both a .timer and a companion .service (Type=oneshot) unit file, writes
them to /etc/systemd/system/, and runs daemon-reload + enable --now.
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


class TimerConfig(BaseModel):
    """Configuration for the systemd timer unit."""

    model_config = ConfigDict(extra="forbid")

    timer_name: str  # name (without .timer suffix)
    description: str = ""
    on_calendar: str  # systemd calendar expression, e.g. "*-*-* 02:00:00"
    persistent: bool = True  # run missed events on boot
    accuracy_sec: str = "1min"


class TimerServiceConfig(BaseModel):
    """Configuration for the oneshot service triggered by the timer."""

    model_config = ConfigDict(extra="forbid")

    exec_start: str  # command to run
    user: str = "root"
    group: str = "root"
    working_directory: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)


class SystemdTimerLoginBlock(BaseModel):
    """Login defaults matching post-bootstrap convention (admin@2222)."""

    model_config = ConfigDict(extra="forbid")

    user: str = "admin"
    private_key: str = "~/.ssh/id_ed25519"
    password: str | None = None
    port: int = 2222


class SystemdTimerLocalBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_dir: str = ""
    inventory: InventoryBlock = Field(default_factory=InventoryBlock)


class SystemdTimerSpec(BaseModel):
    """Spec for deploying scheduled execution via systemd timers."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["systemd_timer"]
    meta: MetaBlock
    host: HostBlock
    login: SystemdTimerLoginBlock = Field(default_factory=SystemdTimerLoginBlock)
    timer: TimerConfig
    service: TimerServiceConfig
    local: SystemdTimerLocalBlock = Field(default_factory=SystemdTimerLocalBlock)
    checks: list[CheckBlock] = Field(default_factory=list)
