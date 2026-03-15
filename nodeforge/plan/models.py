"""Central Plan data structures. All downstream modules consume these."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class StepScope(str, Enum):
    REMOTE = "remote"
    LOCAL = "local"
    VERIFY = "verify"


class StepKind:
    """Open string constants for step execution kinds.

    Unlike a closed Enum, new step kinds can be added by addons simply by
    registering a handler in the executor registry -- no core edits required:

        from nodeforge.registry import register_step_handler
        register_step_handler("compose_up", _handle_compose_up)

    All built-in kind strings are preserved as class attributes so existing
    code using StepKind.SSH_COMMAND continues to work unchanged.
    """

    SSH_COMMAND = "ssh_command"
    SSH_UPLOAD = "ssh_upload"
    LOCAL_COMMAND = "local_command"
    LOCAL_FILE_WRITE = "local_file_write"
    LOCAL_DB_WRITE = "local_db_write"
    VERIFY = "verify"
    GATE = "gate"  # must pass before subsequent steps that depend on it execute


class Step(BaseModel):
    id: str                         # e.g. "create_admin_user", "verify_admin_login"
    index: int
    description: str
    scope: StepScope
    kind: str                       # StepKind constant or addon-defined string
    command: str | None = None      # shell command for SSH/local
    file_content: str | None = None # for file writes/uploads
    target_path: str | None = None  # for file operations
    sudo: bool = False
    check_command: str | None = None
    rollback_hint: str | None = None
    depends_on: list[int] = Field(default_factory=list)
    gate: bool = False
    tags: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    spec_name: str
    spec_kind: str
    target_host: str
    spec_hash: str
    plan_hash: str
    steps: list[Step]
    created_at: str

    def remote_steps(self) -> list[Step]:
        return [s for s in self.steps if s.scope == StepScope.REMOTE]

    def local_steps(self) -> list[Step]:
        return [s for s in self.steps if s.scope == StepScope.LOCAL]

    def gates(self) -> list[Step]:
        return [s for s in self.steps if s.gate]
