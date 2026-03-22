"""Server-side path constants for the nodeforge agent.

These constants are shared between the client (for SSH commands targeting
the agent) and the agent (for local filesystem operations).

All agent state lives under well-known paths on the managed server.
These paths are deterministic and do not depend on user configuration.
"""

from __future__ import annotations

from pathlib import Path

# Configuration (read-only after bootstrap)
AGENT_CONFIG_DIR = Path("/etc/nodeforge")

# Runtime state (mutable: locks, state tracking, desired state)
AGENT_STATE_DIR = Path("/var/lib/nodeforge")
AGENT_LOCK_DIR = AGENT_STATE_DIR / "locks"
AGENT_DESIRED_DIR = AGENT_STATE_DIR / "desired"
AGENT_STATE_FILE = AGENT_STATE_DIR / "runtime-state.json"

# Logs
AGENT_LOG_DIR = Path("/var/log/nodeforge")

# Agent binary location
AGENT_BINARY_PATH = Path("/usr/local/bin/nodeforge-agent")
