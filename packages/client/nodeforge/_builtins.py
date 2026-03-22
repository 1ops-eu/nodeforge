"""Register the built-in core spec kinds: bootstrap and service.

All imports are lazy (inside function bodies) to avoid circular import
issues between the compiler, specs, runtime, and registry modules.
This module is called exactly once by load_addons() at CLI startup.
"""

from __future__ import annotations


def _register_builtins() -> None:
    """Register bootstrap and service kinds across all registries."""
    _register_resolvers()
    _register_specs()
    _register_normalizers()
    _register_validators()
    _register_planners()
    _register_step_handlers()
    _register_hooks()


def _register_specs() -> None:
    from nodeforge_core.registry.specs import register_spec_kind
    from nodeforge_core.specs.bootstrap_schema import BootstrapSpec
    from nodeforge_core.specs.compose_project_schema import ComposeProjectSpec
    from nodeforge_core.specs.file_template_schema import FileTemplateSpec
    from nodeforge_core.specs.service_schema import ServiceSpec

    register_spec_kind("bootstrap", BootstrapSpec)
    register_spec_kind("service", ServiceSpec)
    register_spec_kind("file_template", FileTemplateSpec)
    register_spec_kind("compose_project", ComposeProjectSpec)


def _register_normalizers() -> None:
    from nodeforge.compiler.normalizer import (
        _normalize_bootstrap,
        _normalize_compose_project,
        _normalize_file_template,
        _normalize_service,
    )
    from nodeforge_core.registry.normalizers import register_normalizer

    register_normalizer("bootstrap", _normalize_bootstrap)
    register_normalizer("service", _normalize_service)
    register_normalizer("file_template", _normalize_file_template)
    register_normalizer("compose_project", _normalize_compose_project)


def _register_validators() -> None:
    from nodeforge_core.registry.validators import register_validator
    from nodeforge_core.specs.validators import (
        validate_bootstrap,
        validate_compose_project,
        validate_file_template,
        validate_service,
    )

    register_validator("bootstrap", validate_bootstrap)
    register_validator("service", validate_service)
    register_validator("file_template", validate_file_template)
    register_validator("compose_project", validate_compose_project)


def _register_planners() -> None:
    from nodeforge.compiler.planner import (
        _plan_bootstrap,
        _plan_compose_project,
        _plan_file_template,
        _plan_service,
    )
    from nodeforge_core.registry.planners import register_planner

    register_planner("bootstrap", _plan_bootstrap)
    register_planner("service", _plan_service)
    register_planner("file_template", _plan_file_template)
    register_planner("compose_project", _plan_compose_project)


def _register_step_handlers() -> None:
    from nodeforge_core.plan.models import StepKind
    from nodeforge_core.registry.executors import register_step_handler

    # Wrap Executor instance methods: handler(executor, step) -> StepResult.
    # The executor's private _execute_* methods are left entirely unchanged.
    register_step_handler(StepKind.GATE, lambda ex, step: ex._execute_gate(step))
    register_step_handler(StepKind.SSH_COMMAND, lambda ex, step: ex._execute_ssh_command(step))
    register_step_handler(StepKind.SSH_UPLOAD, lambda ex, step: ex._execute_ssh_upload(step))
    register_step_handler(
        StepKind.LOCAL_FILE_WRITE, lambda ex, step: ex._execute_local_file_write(step)
    )
    register_step_handler(
        StepKind.LOCAL_DB_WRITE, lambda ex, step: ex._execute_local_db_write(step)
    )
    register_step_handler(StepKind.LOCAL_COMMAND, lambda ex, step: ex._execute_local_command(step))
    register_step_handler(StepKind.VERIFY, lambda ex, step: ex._execute_verify(step))
    register_step_handler(
        StepKind.COMPOSE_HEALTH_CHECK,
        lambda ex, step: ex._execute_compose_health_check(step),
    )


def _register_hooks() -> None:
    from nodeforge.local.inventory import (
        record_bootstrap,
        record_compose_project_apply,
        record_file_template_apply,
        record_service_apply,
    )
    from nodeforge_core.registry.hooks import KindHooks, register_kind_hooks

    register_kind_hooks(
        "bootstrap",
        KindHooks(
            needs_key_generation=True,
            ssh_port_fallback=True,
            on_inventory_record=record_bootstrap,
        ),
    )
    register_kind_hooks(
        "service",
        KindHooks(
            needs_key_generation=False,
            ssh_port_fallback=False,
            on_inventory_record=record_service_apply,
        ),
    )
    register_kind_hooks(
        "file_template",
        KindHooks(
            needs_key_generation=False,
            ssh_port_fallback=False,
            on_inventory_record=record_file_template_apply,
        ),
    )
    register_kind_hooks(
        "compose_project",
        KindHooks(
            needs_key_generation=False,
            ssh_port_fallback=False,
            on_inventory_record=record_compose_project_apply,
        ),
    )


def _register_resolvers() -> None:
    """Register the built-in value resolvers: 'env' and 'file'."""
    import os
    from pathlib import Path

    from nodeforge_core.registry.resolvers import register_resolver

    def _resolve_env(key: str) -> str | None:
        return os.environ.get(key)

    def _resolve_file(key: str) -> str | None:
        path = Path(key).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        # Strip a single trailing newline — common in key files, config files, etc.
        return content.rstrip("\n")

    register_resolver("env", _resolve_env)
    register_resolver("file", _resolve_file)
