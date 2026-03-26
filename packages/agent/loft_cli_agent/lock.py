"""Mutation locking for the loft-cli agent.

Only one mutation (apply) can run at a time on a managed server.
Uses file-based locking with fcntl for atomic, non-blocking acquisition.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time

from loft_cli_agent import paths as agent_paths


class LockError(RuntimeError):
    """Raised when the mutation lock cannot be acquired."""


class MutationLock:
    """Context manager for exclusive mutation locking.

    Usage::

        with MutationLock():
            # Only one apply runs at a time
            agent_executor.apply(plan)
    """

    def __init__(self, lock_name: str = "apply") -> None:
        self._lock_name = lock_name
        self._fd: int | None = None

    @property
    def _lock_path(self):
        return agent_paths.AGENT_LOCK_DIR / f"{self._lock_name}.lock"

    def __enter__(self) -> MutationLock:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)

        self._fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._fd)
            self._fd = None
            # Try to read who holds the lock
            holder = self._read_holder()
            raise LockError(
                f"Another mutation is in progress. Lock: {self._lock_path}"
                + (f" (held by PID {holder.get('pid')})" if holder else "")
            ) from None

        # Write PID and timestamp to lock file
        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        info = json.dumps({"pid": os.getpid(), "started_at": time.time()})
        os.write(self._fd, info.encode())
        return self

    def __exit__(self, *exc) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
            # Remove lock file on clean exit
            with contextlib.suppress(OSError):
                self._lock_path.unlink(missing_ok=True)

    def _read_holder(self) -> dict | None:
        try:
            content = self._lock_path.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception:
            return None
