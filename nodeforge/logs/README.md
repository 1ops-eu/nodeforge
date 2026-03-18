# nodeforge/logs/ — Apply Execution Logs

This package writes and reads structured JSON logs for every `nodeforge apply` execution.

---

## Files

| File | Purpose |
|---|---|
| `writer.py` | Writes a JSON log file after each apply, capturing the full execution trace |
| `reader.py` | Reads and queries log files for the `nodeforge inspect run` command |
| `__init__.py` | Empty package marker |

---

## Log Directory

Default: `~/.nodeforge/runs/`

Overridable via `NODEFORGE_STATE_DIR` (becomes `{state_dir}/runs/`) or programmatically via `register_local_paths()`.

---

## Writer (`writer.py`)

`write_log(result: ApplyResult, log_dir=None) -> Path`

Writes a JSON file named `{timestamp}_{spec_name}.json` with:

- `run_id` — ISO timestamp identifier
- `spec_name`, `spec_kind`, `target_host` — spec metadata
- `spec_hash`, `plan_hash` — integrity hashes
- `status` — overall result (success/failed/success_with_local_warnings)
- `started_at`, `finished_at` — execution timestamps
- `aborted_at_step` — step index where the plan aborted (if applicable)
- `steps[]` — per-step details: index, id, scope, status, duration, output (truncated to 500 chars), error

---

## Reader (`reader.py`)

- `list_logs(log_dir=None)` — returns all logs (newest first) with summary info
- `read_log(log_path)` — reads a single log file into a dict
- `find_log(run_id, log_dir=None)` — finds a log file by run_id prefix match

Used by `nodeforge inspect run <run-id>` to display past execution details.

---

## Design Decisions

- **JSON format**: human-readable and easy to parse programmatically.
- **Output truncation**: step output and error strings are capped at 500 characters to keep log files manageable.
- **Prefix matching**: `find_log()` supports partial run_id matches for convenience.
