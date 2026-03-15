"""Normalizer registry: maps kind strings to normalizer callables.

A normalizer callable has the signature:
    (spec: AnySpec, ctx: NormalizedContext) -> None
"""
from __future__ import annotations

from typing import Callable

_NORMALIZER_REGISTRY: dict[str, Callable] = {}


def register_normalizer(kind: str, fn: Callable) -> None:
    """Register a normalizer function for a spec kind."""
    _NORMALIZER_REGISTRY[kind] = fn


def get_normalizer(kind: str) -> Callable | None:
    """Return the normalizer for a kind, or None if not registered."""
    return _NORMALIZER_REGISTRY.get(kind)
