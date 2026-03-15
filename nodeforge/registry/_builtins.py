"""Register the built-in core spec kinds: bootstrap and service.

All imports are lazy (inside function bodies) to avoid circular import
issues between the compiler, specs, runtime, and registry modules.
This module is called exactly once by load_addons() at CLI startup.
"""
from __future__ import annotations


def _register_builtins() -> None:
    """Register bootstrap and service kinds across all registries."""
    _register_specs()
    _register_normalizers()
    _register_validators()
    _register_planners()
    _register_step_handlers()
    _register_hooks()


def _register_specs() -> None:
    from nodeforge.registry.specs import register_spec_kind
    from nodeforge.specs.bootstrap_schema import BootstrapSpec
    from nodeforge.specs.service_schema import ServiceSpec

    register_spec_kind("bootstrap", BootstrapSpec)
    register_spec_kind("service", ServiceSpec)


def _register_normalizers() -> None:
    from nodeforge.registry.normalizers import register_normalizer
    from nodeforge.compiler.normalizer import _normalize_bootstrap, _normalize_service

    register_normalizer("bootstrap", _normalize_bootstrap)
    register_normalizer("service", _normalize_service)


def _register_validators() -> None:
    from nodeforge.registry.validators import register_validator
    from nodeforge.specs.validators import validate_bootstrap, validate_service

    register_validator("bootstrap", validate_bootstrap)
    register_validator("service", validate_service)


def _register_planners() -> None:
    from nodeforge.registry.planners import register_planner
    from nodeforge.compiler.planner import _plan_bootstrap, _plan_service

    register_planner("bootstrap", _plan_bootstrap)
    register_planner("service", _plan_service)


def _register_step_handlers() -> None:
    from nodeforge.registry.executors import register_step_handler
    from nodeforge.plan.models import StepKind

    # Wrap Executor instance methods: handler(executor, step) -> StepResult.
    # The executor's private _execute_* methods are left entirely unchanged.
    register_step_handler(StepKind.GATE,
                          lambda ex, step: ex._execute_gate(step))
    register_step_handler(StepKind.SSH_COMMAND,
                          lambda ex, step: ex._execute_ssh_command(step))
    register_step_handler(StepKind.SSH_UPLOAD,
                          lambda ex, step: ex._execute_ssh_upload(step))
    register_step_handler(StepKind.LOCAL_FILE_WRITE,
                          lambda ex, step: ex._execute_local_file_write(step))
    register_step_handler(StepKind.LOCAL_DB_WRITE,
                          lambda ex, step: ex._execute_local_db_write(step))
    register_step_handler(StepKind.LOCAL_COMMAND,
                          lambda ex, step: ex._execute_local_command(step))
    register_step_handler(StepKind.VERIFY,
                          lambda ex, step: ex._execute_verify(step))


def _register_hooks() -> None:
    from nodeforge.registry.hooks import register_kind_hooks, KindHooks
    from nodeforge.local.inventory import record_bootstrap, record_service_apply

    register_kind_hooks("bootstrap", KindHooks(
        needs_key_generation=True,
        ssh_port_fallback=True,
        on_inventory_record=record_bootstrap,
    ))
    register_kind_hooks("service", KindHooks(
        needs_key_generation=False,
        ssh_port_fallback=False,
        on_inventory_record=record_service_apply,
    ))
