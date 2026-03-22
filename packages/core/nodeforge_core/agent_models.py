"""Shared agent result models.

These Pydantic models define the agent apply/step result schema shared
between the agent (which produces them) and the client (which consumes
them via agent_transport).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class AgentStepResult(BaseModel):
    step_index: int
    step_id: str
    scope: str
    status: Literal["success", "failed", "skipped", "unchanged"]
    output: str = ""
    error: str = ""
    duration_seconds: float = 0.0


class AgentApplyResult(BaseModel):
    plan_hash: str
    spec_hash: str
    step_results: list[AgentStepResult]
    status: Literal["success", "failed"]
    aborted_at: int | None = None
    started_at: str
    finished_at: str = ""
    unchanged_count: int = 0
    applied_count: int = 0
