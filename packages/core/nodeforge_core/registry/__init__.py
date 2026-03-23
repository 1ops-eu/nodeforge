"""nodeforge addon/plugin registry.

Public API for registering and discovering spec kinds, planners, normalizers,
validators, step handlers, and lifecycle hooks.  Addons call these functions
during registration to extend nodeforge without modifying any core source files.

Built-in kinds (bootstrap, service) are registered by the ``nodeforge`` client
package via the ``nodeforge.addons`` entry_points group.

External addons also register via Python entry_points:

    # In the addon's pyproject.toml:
    [project.entry-points."nodeforge.addons"]
    my_addon = "my_addon:register"

    # In my_addon/__init__.py:
    def register():
        from nodeforge_core.registry import register_spec_kind, register_planner, ...
        register_spec_kind("my_kind", MySpec)
        register_planner("my_kind", _plan_my_kind)
        ...

load_addons() is idempotent — subsequent calls are no-ops.
"""

from __future__ import annotations

from nodeforge_core.registry.executors import get_step_handler, register_step_handler
from nodeforge_core.registry.hooks import KindHooks, get_kind_hooks, register_kind_hooks
from nodeforge_core.registry.local_paths import (
    LocalPathsConfig,
    get_local_paths,
    register_local_paths,
)
from nodeforge_core.registry.normalizers import get_normalizer, register_normalizer
from nodeforge_core.registry.planners import get_planner, register_planner
from nodeforge_core.registry.resolvers import get_resolver, list_resolvers, register_resolver
from nodeforge_core.registry.specs import get_spec_model, list_spec_kinds, register_spec_kind
from nodeforge_core.registry.validators import get_validator, register_validator

__all__ = [
    # Spec kinds
    "register_spec_kind",
    "get_spec_model",
    "list_spec_kinds",
    # Planners
    "register_planner",
    "get_planner",
    # Normalizers
    "register_normalizer",
    "get_normalizer",
    # Validators
    "register_validator",
    "get_validator",
    # Step handlers
    "register_step_handler",
    "get_step_handler",
    # Lifecycle hooks
    "register_kind_hooks",
    "get_kind_hooks",
    "KindHooks",
    # Value resolvers (7th registry)
    "register_resolver",
    "get_resolver",
    "list_resolvers",
    # Local filesystem paths (addon-overridable)
    "register_local_paths",
    "get_local_paths",
    "LocalPathsConfig",
    # Addon loader
    "load_addons",
]

_addons_loaded = False


def load_addons() -> None:
    """Load built-in kinds and discover external addons via entry_points.

    Safe to call multiple times — subsequent calls are no-ops.
    Called automatically by the CLI before any command runs, and also
    lazily by load_spec() and validate_spec() for non-CLI usage (tests, etc.).
    """
    global _addons_loaded
    if _addons_loaded:
        return
    _addons_loaded = True

    # Discover and load all addons (including built-in kinds) via entry_points.
    # The nodeforge client package registers built-in kinds (bootstrap, service,
    # file_template, compose_project) via its own entry_point.
    try:
        import importlib.metadata

        entry_points = importlib.metadata.entry_points(group="nodeforge.addons")
        for ep in entry_points:
            try:
                addon_register = ep.load()
                addon_register()
            except Exception as exc:
                import warnings

                warnings.warn(
                    f"Failed to load nodeforge addon '{ep.name}': {exc}",
                    stacklevel=2,
                )
    except Exception:
        pass
