"""Agent installation utilities.

Handles uploading and installing the nodeforge-agent binary on target servers,
and verifying agent availability.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from nodeforge.agent.paths import (
    AGENT_BINARY_PATH,
    AGENT_CONFIG_DIR,
    AGENT_LOG_DIR,
    AGENT_STATE_DIR,
)

if TYPE_CHECKING:
    from nodeforge.runtime.transport import Transport


def detect_agent(transport: Transport) -> str | None:
    """Check if nodeforge-agent is installed on the target and return its version.

    Returns the version string, or None if not installed.
    """
    result = transport.run(f"{AGENT_BINARY_PATH} version", sudo=False, warn=True)
    if result.ok and result.stdout.strip():
        # Output format: "nodeforge-agent X.Y.Z"
        parts = result.stdout.strip().split()
        return parts[-1] if parts else result.stdout.strip()
    return None


def install_agent_commands() -> list[str]:
    """Return the shell commands to create agent directories on the target.

    The actual binary upload is handled by the planner as an ssh_upload step.
    These commands are embedded in plan steps.
    """
    dirs = [str(AGENT_CONFIG_DIR), str(AGENT_STATE_DIR), str(AGENT_LOG_DIR)]
    return [f"mkdir -p {d}" for d in dirs]


def get_local_agent_binary() -> Path | None:
    """Locate the nodeforge-agent binary on the local system.

    Checks: 1) alongside the current nodeforge binary, 2) on PATH.
    Returns None if not found.
    """
    # Check alongside the running nodeforge binary
    import sys

    current = Path(sys.executable).parent / "nodeforge-agent"
    if current.exists():
        return current

    # Check PATH
    found = shutil.which("nodeforge-agent")
    if found:
        return Path(found)

    return None
