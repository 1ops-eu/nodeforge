"""Write structured apply logs.

The default log directory is determined by ``get_local_paths().log_dir``
which respects the ``NODEFORGE_STATE_DIR`` environment variable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodeforge.runtime.executor import ApplyResult


def _default_log_dir() -> Path:
    from nodeforge_core.registry.local_paths import get_local_paths

    return get_local_paths().log_dir


def write_log(result: ApplyResult, log_dir: Path | None = None) -> Path:
    """Write JSON log of apply result. Returns path to the log file."""
    d = (log_dir or _default_log_dir()).expanduser()
    d.mkdir(parents=True, exist_ok=True)

    ts = result.started_at.replace(":", "-").replace("+", "Z")[:19]
    spec_name = result.plan.spec_name.replace(" ", "_").lower()
    log_path = d / f"{ts}_{spec_name}.json"

    data = {
        "run_id": ts,
        "spec_name": result.plan.spec_name,
        "spec_kind": result.plan.spec_kind,
        "target_host": result.plan.target_host,
        "spec_hash": result.plan.spec_hash,
        "plan_hash": result.plan.plan_hash,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "aborted_at_step": result.aborted_at,
        "steps": [
            {
                "index": r.step_index,
                "id": r.step_id,
                "scope": r.scope,
                "status": r.status,
                "duration_seconds": r.duration_seconds,
                "output": r.output[:500] if r.output else "",
                "error": r.error[:500] if r.error else "",
            }
            for r in result.step_results
        ],
    }

    log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return log_path
