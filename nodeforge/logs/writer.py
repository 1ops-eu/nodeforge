"""Write structured apply logs to ~/.nodeforge/runs/."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodeforge.runtime.executor import ApplyResult

_LOG_DIR = Path("~/.nodeforge/runs").expanduser()


def write_log(result: "ApplyResult", log_dir: Path | None = None) -> Path:
    """Write JSON log of apply result. Returns path to the log file."""
    d = (log_dir or _LOG_DIR).expanduser()
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
