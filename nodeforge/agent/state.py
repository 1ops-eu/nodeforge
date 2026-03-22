"""Runtime state management for the nodeforge agent.

Tracks which resources have been applied and their content hashes,
enabling idempotent re-apply (skip unchanged resources).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from nodeforge.agent.paths import AGENT_STATE_FILE


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


def load_state(state_path: Path | None = None) -> RuntimeState:
    """Load runtime state from disk. Returns empty state if file doesn't exist."""
    path = state_path or AGENT_STATE_FILE
    if not path.exists():
        return RuntimeState()
    try:
        content = path.read_text(encoding="utf-8")
        return RuntimeState.model_validate_json(content)
    except Exception:
        return RuntimeState()


def save_state(state: RuntimeState, state_path: Path | None = None) -> None:
    """Atomically write runtime state to disk (write to tmp, rename)."""
    path = state_path or AGENT_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory, then rename for atomicity
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, state.model_dump_json(indent=2).encode("utf-8"))
        os.close(fd)
        os.rename(tmp_path, str(path))
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def resource_changed(state: RuntimeState, resource_id: str, content_hash: str) -> bool:
    """Return True if the resource has changed or was never applied."""
    existing = state.resources.get(resource_id)
    if existing is None:
        return True
    return existing.content_hash != content_hash


def update_resource(
    state: RuntimeState,
    resource_id: str,
    content_hash: str,
    status: str = "applied",
) -> None:
    """Update a resource's state after execution."""
    state.resources[resource_id] = ResourceState(
        resource_id=resource_id,
        content_hash=content_hash,
        applied_at=datetime.now(UTC).isoformat(),
        status=status,
    )
    state.last_applied = datetime.now(UTC).isoformat()
