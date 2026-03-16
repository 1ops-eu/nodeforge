"""nodeforge addon/plugin registry.

Public API for registering and discovering spec kinds, planners, normalizers,
validators, step handlers, and lifecycle hooks.  Addons call these functions
during registration to extend nodeforge without modifying any core source files.

Built-in kinds (bootstrap, service) are registered via _register_builtins()
which is called once by load_addons() at CLI startup.

External addons register via Python entry_points:

    # In the addon's pyproject.toml:
    [project.entry-points."nodeforge.addons"]
    my_addon = "my_addon:register"

    # In my_addon/__init__.py:
    def register():
        from nodeforge.registry import register_spec_kind, register_planner, ...
        register_spec_kind("my_kind", MySpec)
        register_planner("my_kind", _plan_my_kind)
        ...

load_addons() is idempotent — subsequent calls are no-ops.
"""

from __future__ import annotations

from nodeforge.registry.specs import register_spec_kind, get_spec_model, list_spec_kinds
from nodeforge.registry.planners import register_planner, get_planner
from nodeforge.registry.normalizers import register_normalizer, get_normalizer
from nodeforge.registry.validators import register_validator, get_validator
from nodeforge.registry.executors import register_step_handler, get_step_handler
from nodeforge.registry.hooks import register_kind_hooks, get_kind_hooks, KindHooks
from nodeforge.registry.local_paths import (
    register_local_paths,
    get_local_paths,
    LocalPathsConfig,
)

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

    # Register built-in core kinds (bootstrap, service)
    from nodeforge.registry._builtins import _register_builtins

    _register_builtins()

    # Discover and load external addons registered via entry_points
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
