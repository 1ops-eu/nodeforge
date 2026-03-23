"""Server-side path management for the nodeforge agent.

Path constants are defined in nodeforge_core.agent_paths (shared with client).
This module re-exports them for convenience and adds agent-only functions.
"""

from __future__ import annotations

from nodeforge_core.agent_paths import (
    AGENT_BINARY_PATH,
    AGENT_CONFIG_DIR,
    AGENT_DESIRED_DIR,
    AGENT_LOCK_DIR,
    AGENT_LOG_DIR,
    AGENT_STATE_DIR,
    AGENT_STATE_FILE,
)

__all__ = [
    "AGENT_BINARY_PATH",
    "AGENT_CONFIG_DIR",
    "AGENT_DESIRED_DIR",
    "AGENT_LOCK_DIR",
    "AGENT_LOG_DIR",
    "AGENT_STATE_DIR",
    "AGENT_STATE_FILE",
    "ensure_agent_dirs",
]


def ensure_agent_dirs() -> None:
    """Create all agent directories if they don't exist."""
    for d in (AGENT_CONFIG_DIR, AGENT_STATE_DIR, AGENT_LOCK_DIR, AGENT_DESIRED_DIR, AGENT_LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
