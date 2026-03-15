"""Spec kind registry: maps kind strings to Pydantic model classes."""
from __future__ import annotations

from typing import Any

_SPEC_REGISTRY: dict[str, type] = {}


def register_spec_kind(kind: str, model_class: type) -> None:
    """Register a spec kind and its Pydantic model class."""
    _SPEC_REGISTRY[kind] = model_class


def get_spec_model(kind: str) -> type | None:
    """Return the model class for a given kind, or None if not registered."""
    return _SPEC_REGISTRY.get(kind)


def list_spec_kinds() -> list[str]:
    """Return all registered spec kind names."""
    return list(_SPEC_REGISTRY.keys())
