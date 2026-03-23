"""Read and display apply logs.

The default log directory is determined by ``get_local_paths().log_dir``
which respects the ``NODEFORGE_STATE_DIR`` environment variable.
"""

from __future__ import annotations

import json
from pathlib import Path


def _default_log_dir() -> Path:
    from nodeforge_core.registry.local_paths import get_local_paths

    return get_local_paths().log_dir


def list_logs(log_dir: Path | None = None) -> list[dict]:
    """List all apply logs with summary info, newest first."""
    d = (log_dir or _default_log_dir()).expanduser()
    if not d.exists():
        return []
    logs = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            logs.append(
                {
                    "file": str(f),
                    "run_id": data.get("run_id"),
                    "spec_name": data.get("spec_name"),
                    "target_host": data.get("target_host"),
                    "status": data.get("status"),
                    "started_at": data.get("started_at"),
                }
            )
        except Exception:
            pass
    return logs


def read_log(log_path: Path) -> dict:
    """Read a single apply log file."""
    return json.loads(log_path.read_text(encoding="utf-8"))


def find_log(run_id: str, log_dir: Path | None = None) -> Path | None:
    """Find a log file by run_id prefix."""
    d = (log_dir or _default_log_dir()).expanduser()
    if not d.exists():
        return None
    for f in d.glob(f"{run_id}*.json"):
        return f
    return None
