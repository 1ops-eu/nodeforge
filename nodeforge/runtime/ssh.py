"""Fabric SSH session wrapper.

Adapted from vm_wizard's run_fabric_process() pattern.
Fabric is transport only — business logic lives in plan/executor layers.
"""

from __future__ import annotations

from pathlib import Path

import paramiko
from fabric import Connection
from pydantic import BaseModel


class _AutoAddConnection(Connection):
    """Fabric Connection that auto-accepts unknown host keys.

    Provisioning tools connect to fresh VMs whose keys are not yet in
    ~/.ssh/known_hosts.  Paramiko's default RejectPolicy would abort the
    connection; AutoAddPolicy accepts the key and adds it to known_hosts.
    """

    def create_client(self) -> paramiko.SSHClient:  # type: ignore[override]
        client = super().create_client()  # type: ignore[misc]
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client


class CommandResult(BaseModel):
    ok: bool
    stdout: str
    stderr: str
    return_code: int


class SSHSession:
    """Wraps a Fabric Connection with a clean API for nodeforge."""

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 22,
        password: str | None = None,
        key_path: str | None = None,
    ) -> None:
        connect_kwargs: dict = {}
        if password:
            connect_kwargs["password"] = password
            # When using password auth without a key, tell Paramiko not to
            # try key-based auth. This prevents "allowed types: ['publickey']"
            # errors when the server has both auth methods available.
            if not key_path:
                connect_kwargs["look_for_keys"] = False
        if key_path:
            connect_kwargs["key_filename"] = str(Path(key_path).expanduser())

        self._conn = _AutoAddConnection(
            host=host,
            user=user,
            port=port,
            connect_kwargs=connect_kwargs,
        )
        self.host = host
        self.user = user
        self.port = port

    def run(
        self,
        cmd: str,
        sudo: bool = False,
        warn: bool = True,
        hide: bool = True,
    ) -> CommandResult:
        """Execute a command on the remote host."""
        try:
            if sudo:
                result = self._conn.sudo(cmd, warn=warn, hide=hide)
            else:
                result = self._conn.run(cmd, warn=warn, hide=hide)

            return CommandResult(
                ok=result.ok,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                return_code=result.return_code,
            )
        except Exception as e:
            return CommandResult(
                ok=False,
                stdout="",
                stderr=str(e),
                return_code=1,
            )

    def upload(self, local_path: Path | str, remote_path: str) -> None:
        """Upload a local file to the remote host."""
        self._conn.put(str(local_path), remote=remote_path)

    def upload_content(
        self, content: str, remote_path: str, sudo: bool = False
    ) -> None:
        """Write string content to a remote file via /tmp."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        try:
            tmp_remote = f"/tmp/{Path(remote_path).name}.nodeforge_tmp"
            self._conn.put(tmp_path, remote=tmp_remote)
            if sudo:
                self.run(f"mv {tmp_remote} {remote_path}", sudo=True)
                self.run(f"chmod 600 {remote_path}", sudo=True)
            else:
                self.run(f"mv {tmp_remote} {remote_path}")
        finally:
            os.unlink(tmp_path)

    def test_connection(self) -> bool:
        """Return True if SSH connection succeeds."""
        result = self.run("echo ok", warn=True)
        return result.ok and "ok" in result.stdout

    def close(self) -> None:
        """Close the Fabric connection."""
        try:
            self._conn.close()
        except Exception:
            pass
