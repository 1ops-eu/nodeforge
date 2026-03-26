"""Tests for agent runtime state management."""

from loft_cli_agent.state import (
    RuntimeState,
    load_state,
    resource_changed,
    save_state,
    update_resource,
)


def test_load_state_missing_file(tmp_path):
    """Loading state from a non-existent file returns empty state."""
    state = load_state(tmp_path / "nonexistent.json")
    assert state.version == ""
    assert state.resources == {}


def test_save_and_load_state(tmp_path):
    """State survives a save/load round-trip."""
    path = tmp_path / "state.json"
    state = RuntimeState(version="0.4.0", spec_hash="abc", plan_hash="def")
    update_resource(state, "step_1", "hash123", "applied")

    save_state(state, path)
    loaded = load_state(path)

    assert loaded.version == "0.4.0"
    assert loaded.spec_hash == "abc"
    assert "step_1" in loaded.resources
    assert loaded.resources["step_1"].content_hash == "hash123"


def test_resource_changed_new_resource():
    """A resource not in state is considered changed."""
    state = RuntimeState()
    assert resource_changed(state, "new_step", "hash1") is True


def test_resource_changed_same_hash():
    """A resource with the same hash is not changed."""
    state = RuntimeState()
    update_resource(state, "step_1", "hash1")
    assert resource_changed(state, "step_1", "hash1") is False


def test_resource_changed_different_hash():
    """A resource with a different hash is changed."""
    state = RuntimeState()
    update_resource(state, "step_1", "hash1")
    assert resource_changed(state, "step_1", "hash2") is True


def test_update_resource_overwrites():
    """Updating a resource replaces its previous state."""
    state = RuntimeState()
    update_resource(state, "step_1", "hash1")
    update_resource(state, "step_1", "hash2", status="failed")

    assert state.resources["step_1"].content_hash == "hash2"
    assert state.resources["step_1"].status == "failed"
