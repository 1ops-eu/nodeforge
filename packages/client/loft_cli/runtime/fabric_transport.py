"""Fabric-based transport implementation.

Wraps the existing SSHSession to satisfy the Transport protocol.
This is the default transport used by the client when no agent is available.
"""

from __future__ import annotations

from pathlib import Path

from loft_cli.runtime.ssh import CommandResult, SSHSession


class FabricTransport:
    """Transport implementation backed by Fabric SSH.

    Delegates all operations to the underlying SSHSession. Implements the
    Transport protocol via structural typing (no explicit inheritance needed).
    """

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 22,
        password: str | None = None,
        key_path: str | None = None,
        connect_timeout: int = 10,
    ) -> None:
        self._session = SSHSession(
            host=host,
            user=user,
            port=port,
            password=password,
            key_path=key_path,
            connect_timeout=connect_timeout,
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
        return self._session.run(cmd, sudo=sudo, warn=warn, hide=hide)

    def upload(self, local_path: Path | str, remote_path: str) -> None:
        self._session.upload(local_path, remote_path)

    def upload_content(self, content: str, remote_path: str, sudo: bool = False) -> CommandResult:
        return self._session.upload_content(content, remote_path, sudo=sudo)

    def download(self, remote_path: str) -> str:
        """Download a remote file's content by reading it via SSH."""
        result = self.run(f"cat {remote_path}", sudo=False, warn=True)
        if not result.ok:
            raise RuntimeError(f"Failed to download {remote_path}: {result.stderr}")
        return result.stdout

    def test_connection(self) -> bool:
        return self._session.test_connection()

    def close(self) -> None:
        self._session.close()
