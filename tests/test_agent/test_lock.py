"""Tests for agent mutation locking."""

from nodeforge_agent import paths as agent_paths
from nodeforge_agent.lock import LockError, MutationLock


def test_lock_acquire_release(tmp_path, monkeypatch):
    """Lock can be acquired and released cleanly."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(agent_paths, "AGENT_LOCK_DIR", lock_dir)

    with MutationLock("test"):
        lock_file = lock_dir / "test.lock"
        assert lock_file.exists()

    # Lock file removed after exit
    assert not lock_file.exists()


def test_lock_contention(tmp_path, monkeypatch):
    """Second lock acquisition raises LockError."""
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    monkeypatch.setattr(agent_paths, "AGENT_LOCK_DIR", lock_dir)

    import pytest

    with (
        MutationLock("test"),
        pytest.raises(LockError, match="Another mutation is in progress"),
        MutationLock("test"),
    ):
        pass  # Should not reach here
