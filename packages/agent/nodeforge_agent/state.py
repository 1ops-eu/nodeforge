"""Runtime state management for the nodeforge agent.

Tracks which resources have been applied and their content hashes,
enabling idempotent re-apply (skip unchanged resources).

The state models (RuntimeState, ResourceState) live in nodeforge_core.state
so that both the client (for diff rendering) and the agent can use them.
This module provides the I/O functions for loading and saving state on disk.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from nodeforge_core.agent_paths import AGENT_STATE_FILE
from nodeforge_core.state import ResourceState, RuntimeState


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
