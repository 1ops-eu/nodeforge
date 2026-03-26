"""Shared state models for the loft-cli agent.

These Pydantic models define the runtime state schema shared between
the client (for diff rendering) and the agent (for state tracking).

State management functions (load_state, save_state, etc.) live in
the loft_cli_agent package since they perform server-side I/O.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResourceState(BaseModel):
    """State of a single applied resource (step)."""

    resource_id: str
    content_hash: str  # SHA-256 of step command + file_content + target_path
    applied_at: str  # ISO timestamp
    status: str = "applied"  # "applied" | "failed"


class RuntimeState(BaseModel):
    """Complete runtime state of the agent on this server."""

    version: str = ""  # Agent version that last applied
    last_applied: str = ""  # ISO timestamp of last apply
    spec_hash: str = ""  # Hash of the last applied spec
    plan_hash: str = ""  # Hash of the last applied plan
    resources: dict[str, ResourceState] = Field(default_factory=dict)
