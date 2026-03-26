"""Ship a goss spec to the remote server and run it.

Responsibilities:
  1. Ensure goss binary is present on the remote server (install via curl if missing).
  2. Create ~/.goss/ directory on the remote (resolved dynamically via $HOME
     so it works for any connecting user, not just root).
  3. Upload the generated goss YAML to ~/.goss/<spec_name>.yaml.
  4. Read-modify-write the master gossfile ~/.goss/goss.yaml so every shipped
     spec is included in a single umbrella run.
  5. Run `goss -g ~/.goss/goss.yaml validate --format json` and return the
     parsed result dict, plus the raw stdout for debugging.

The caller (executor) decides what to do with the result dict.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from loft_cli.runtime.ssh import SSHSession

# Install command: idempotent — only runs curl if goss is not already on PATH.
# Installs to /usr/local/bin so it is available system-wide.
_GOSS_INSTALL_CMD = (
    "command -v goss >/dev/null 2>&1 || (curl -fsSL https://goss.rocks/install | sudo sh)"
)


def _resolve_goss_remote_dir(session: SSHSession) -> str:
    """Return the absolute path to the goss directory on the remote.

    Runs ``echo $HOME`` on the remote to determine the connecting user's home
    directory, then appends ``/.goss``.  This mirrors the ``~`` expansion in
    ``executor._execute_ssh_upload()`` and ensures goss files land in the
    correct home regardless of whether we connect as root or as the admin user
    (e.g. on an idempotent re-run where credential fallback activates).

    Falls back to ``/root/.goss`` if the probe fails (should never happen in
    practice — $HOME is always set for SSH sessions).
    """
    result = session.run("echo $HOME", sudo=False, warn=True)
    if result.ok and result.stdout.strip():
        return f"{result.stdout.strip()}/.goss"
    return "/root/.goss"


def ship_and_run(
    session: SSHSession,
    spec_name: str,
    goss_yaml_content: str,
    admin_user: str,
) -> dict:
    """Ship spec, update master gossfile, run validate.

    Returns a dict with keys:
      - "results":     list of individual check result dicts (from goss JSON)
      - "summary":     top-level summary dict from goss JSON
      - "raw_output":  raw stdout string (for debugging)
      - "exit_ok":     bool — True if goss reported zero failures
      - "error":       str — non-empty when something failed before goss ran
    """
    # ------------------------------------------------------------------ #
    # 0. Resolve the remote goss directory for the connecting user
    # ------------------------------------------------------------------ #
    goss_dir = _resolve_goss_remote_dir(session)
    goss_master = f"{goss_dir}/goss.yaml"

    # ------------------------------------------------------------------ #
    # 1. Install goss if absent
    # ------------------------------------------------------------------ #
    install_result = session.run(_GOSS_INSTALL_CMD, sudo=False, warn=True)
    if not install_result.ok:
        return _error(f"goss install failed: {install_result.stderr}")

    # ------------------------------------------------------------------ #
    # 2. Ensure ~/.goss/ directory exists
    # ------------------------------------------------------------------ #
    mkdir_result = session.run(f"mkdir -p {goss_dir}", sudo=False, warn=True)
    if not mkdir_result.ok:
        return _error(f"mkdir {goss_dir} failed: {mkdir_result.stderr}")

    # ------------------------------------------------------------------ #
    # 3. Upload the generated goss spec
    # ------------------------------------------------------------------ #
    spec_remote_path = f"{goss_dir}/{spec_name}.yaml"
    try:
        session.upload_content(goss_yaml_content, spec_remote_path, sudo=False)
    except Exception as exc:
        return _error(f"upload of goss spec failed: {exc}")

    # ------------------------------------------------------------------ #
    # 4. Read-modify-write the master gossfile
    # ------------------------------------------------------------------ #
    master_result = session.run(
        f"cat {goss_master} 2>/dev/null || echo '{{}}'",
        sudo=False,
        warn=True,
    )
    try:
        existing_master = yaml.safe_load(master_result.stdout or "{}") or {}
    except yaml.YAMLError:
        existing_master = {}

    if "gossfile" not in existing_master or not isinstance(existing_master["gossfile"], dict):
        existing_master["gossfile"] = {}

    # Register this spec in the master; key is the remote path
    existing_master["gossfile"][spec_remote_path] = {}

    master_yaml = yaml.dump(existing_master, default_flow_style=False, sort_keys=True)

    try:
        session.upload_content(master_yaml, goss_master, sudo=False)
    except Exception as exc:
        return _error(f"upload of master gossfile failed: {exc}")

    # ------------------------------------------------------------------ #
    # 5. Run goss validate (JSON output for machine-readable results)
    # ------------------------------------------------------------------ #
    # sudo=True because goss internally runs privileged commands (e.g.
    # ``ufw status verbose``, ``wg show``).  On a first run the session
    # connects as root so sudo is a no-op; on an idempotent re-run the
    # session connects as the admin user who has passwordless sudo.
    goss_cmd = f"goss -g {goss_master} validate --format json --no-color"
    goss_result = session.run(goss_cmd, sudo=True, warn=True)

    raw_output = goss_result.stdout.strip()

    # goss exits non-zero when checks fail, but still emits valid JSON.
    # We parse regardless and use the summary to determine pass/fail.
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        # goss may not be in PATH for non-interactive sessions on some distros
        # (e.g. /usr/local/bin not in PATH). Try the full path.
        goss_result2 = session.run(
            f"/usr/local/bin/goss -g {goss_master} validate --format json --no-color",
            sudo=True,
            warn=True,
        )
        raw_output = goss_result2.stdout.strip()
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError:
            return _error(
                f"goss produced non-JSON output. stderr: {goss_result2.stderr!r}. "
                f"stdout: {raw_output[:300]!r}"
            )

    results = parsed.get("results", [])
    summary = parsed.get("summary", {})
    failed_count = summary.get("failed-count", 0)

    return {
        "results": results,
        "summary": summary,
        "raw_output": raw_output,
        "exit_ok": failed_count == 0,
        "error": "",
    }


def _error(msg: str) -> dict:
    return {
        "results": [],
        "summary": {},
        "raw_output": "",
        "exit_ok": False,
        "error": msg,
    }
