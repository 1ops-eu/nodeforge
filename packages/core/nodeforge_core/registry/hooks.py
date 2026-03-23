"""Kind lifecycle hooks: per-spec-kind callbacks used by the CLI.

Hooks allow spec kinds to declare special CLI behaviours without
requiring the CLI to contain isinstance() checks for each concrete type.

Built-in hooks are registered by _builtins._register_builtins().
External addons register hooks for their own spec kinds:

    from nodeforge_core.registry import register_kind_hooks, KindHooks
    register_kind_hooks("compose_project", KindHooks(
        on_inventory_record=_record_compose_project,
    ))
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

_HOOKS_REGISTRY: dict[str, KindHooks] = {}


@dataclass
class KindHooks:
    """Lifecycle hooks for a spec kind, invoked by the CLI at key moments."""

    # Bootstrap-style specs: ensure SSH key pairs exist before normalization.
    needs_key_generation: bool = False

    # Bootstrap-style specs: attempt SSH port fallback on re-runs when
    # login.port is unreachable but ssh.port is reachable.
    ssh_port_fallback: bool = False

    # Called post-apply to record spec results in the local inventory.
    # Signature: (db: InventoryDB, spec: AnySpec, result: ApplyResult) -> None
    on_inventory_record: Callable | None = None


def register_kind_hooks(kind: str, hooks: KindHooks) -> None:
    """Register lifecycle hooks for a spec kind."""
    _HOOKS_REGISTRY[kind] = hooks


def get_kind_hooks(kind: str) -> KindHooks:
    """Return hooks for a kind, or a default no-op KindHooks if not registered."""
    return _HOOKS_REGISTRY.get(kind, KindHooks())
