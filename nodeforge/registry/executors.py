"""Step handler registry: maps step kind strings to executor callables.

A step handler callable has the signature:
    (executor: Executor, step: Step) -> StepResult

The executor instance is passed as the first argument so handlers can
access session, inventory_db, ctx, spec, and console as needed.

Built-in step kinds (ssh_command, ssh_upload, etc.) are registered by
_builtins._register_builtins() at addon load time.  External addons
register new step kinds the same way:

    from nodeforge.registry import register_step_handler
    register_step_handler("compose_up", _handle_compose_up)
"""
from __future__ import annotations

from typing import Callable

_STEP_HANDLER_REGISTRY: dict[str, Callable] = {}


def register_step_handler(kind: str, fn: Callable) -> None:
    """Register an executor handler for a step kind string."""
    _STEP_HANDLER_REGISTRY[kind] = fn


def get_step_handler(kind: str) -> Callable | None:
    """Return the handler for a step kind, or None if not registered."""
    return _STEP_HANDLER_REGISTRY.get(kind)
