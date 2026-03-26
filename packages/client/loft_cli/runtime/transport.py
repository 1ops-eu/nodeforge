"""Transport protocol for remote execution.

Defines the structural protocol that all transport implementations must satisfy.
This decouples the executor from the concrete SSH library (Fabric), enabling
the agent transport path introduced in v0.4.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from loft_cli.runtime.ssh import CommandResult


@runtime_checkable
class Transport(Protocol):
    """Structural protocol for remote command execution and file transfer.

    Any class implementing these methods satisfies the protocol — no
    inheritance required (duck typing via ``runtime_checkable``).
    """

    host: str
    user: str
    port: int

    def run(
        self,
        cmd: str,
        sudo: bool = False,
        warn: bool = True,
        hide: bool = True,
    ) -> CommandResult: ...

    def upload(self, local_path, remote_path: str) -> None: ...

    def upload_content(
        self, content: str, remote_path: str, sudo: bool = False
    ) -> CommandResult: ...

    def test_connection(self) -> bool: ...

    def close(self) -> None: ...
