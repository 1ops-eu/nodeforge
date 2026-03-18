"""Planner registry: maps kind strings to plan-builder callables.

A planner callable has the signature:
    (spec: AnySpec, ctx: NormalizedContext) -> list[Step]
"""

from __future__ import annotations

from collections.abc import Callable

_PLANNER_REGISTRY: dict[str, Callable] = {}


def register_planner(kind: str, fn: Callable) -> None:
    """Register a plan-builder function for a spec kind."""
    _PLANNER_REGISTRY[kind] = fn


def get_planner(kind: str) -> Callable | None:
    """Return the plan-builder for a kind, or None if not registered."""
    return _PLANNER_REGISTRY.get(kind)
