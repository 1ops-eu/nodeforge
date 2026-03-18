"""Validator registry: maps kind strings to validator callables.

A validator callable has the signature:
    (spec: AnySpec) -> list[ValidationIssue]
"""

from __future__ import annotations

from collections.abc import Callable

_VALIDATOR_REGISTRY: dict[str, Callable] = {}


def register_validator(kind: str, fn: Callable) -> None:
    """Register a validator function for a spec kind."""
    _VALIDATOR_REGISTRY[kind] = fn


def get_validator(kind: str) -> Callable | None:
    """Return the validator for a kind, or None if not registered."""
    return _VALIDATOR_REGISTRY.get(kind)
