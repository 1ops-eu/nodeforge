"""High-level inventory operations built on InventoryDB."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loft_cli.local.inventory_db import InventoryDB
    from loft_cli.runtime.executor import ApplyResult
    from loft_cli_core.specs.backup_job_schema import BackupJobSpec
    from loft_cli_core.specs.bootstrap_schema import BootstrapSpec
    from loft_cli_core.specs.compose_project_schema import ComposeProjectSpec
    from loft_cli_core.specs.file_template_schema import FileTemplateSpec
    from loft_cli_core.specs.http_check_schema import HttpCheckSpec
    from loft_cli_core.specs.postgres_ensure_schema import PostgresEnsureSpec
    from loft_cli_core.specs.service_schema import ServiceSpec
    from loft_cli_core.specs.stack_schema import StackSpec
    from loft_cli_core.specs.systemd_timer_schema import SystemdTimerSpec
    from loft_cli_core.specs.systemd_unit_schema import SystemdUnitSpec


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def record_bootstrap(
    db: InventoryDB,
    spec: BootstrapSpec,
    apply_result: ApplyResult,
) -> None:
    """After a successful bootstrap apply, record server + run in inventory."""

    status = apply_result.status
    finished = apply_result.finished_at

    db.upsert_server(
        id=spec.host.name,
        name=spec.host.name,
        address=spec.host.address,
        bootstrap_status="bootstrapped" if "success" in status else "failed",
        os_family=spec.host.os_family,
        ssh_alias=spec.local.ssh_config.host_alias or spec.host.name,
        ssh_host=spec.host.address,
        ssh_user=spec.admin_user.name,
        ssh_port=spec.ssh.port,
        ssh_identity_file=spec.login.private_key,
        wireguard_enabled=spec.wireguard.enabled,
        wireguard_interface=spec.wireguard.interface if spec.wireguard.enabled else "",
        wireguard_address=spec.wireguard.address if spec.wireguard.enabled else "",
    )

    metadata = {
        "spec_name": spec.meta.name,
        "step_count": len(apply_result.step_results),
    }

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="bootstrap",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=finished,
        server_id=spec.host.name,
        metadata_json=json.dumps(metadata),
    )


def record_service_apply(
    db: InventoryDB,
    spec: ServiceSpec,
    apply_result: ApplyResult,
) -> None:
    """After a service apply, record services + run in inventory."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    if spec.postgres and spec.postgres.enabled:
        db.upsert_service(
            server_id=server_id,
            service_type="postgres",
            service_name=f"postgresql-{spec.postgres.version}",
            status="active" if "success" in status else "failed",
            metadata_json=json.dumps({"version": spec.postgres.version}),
        )

    if spec.nginx and spec.nginx.enabled:
        sites = [s.domain for s in spec.nginx.sites]
        db.upsert_service(
            server_id=server_id,
            service_type="nginx",
            service_name="nginx",
            status="active" if "success" in status else "failed",
            metadata_json=json.dumps({"sites": sites}),
        )

    if spec.docker and spec.docker.enabled:
        db.upsert_service(
            server_id=server_id,
            service_type="docker",
            service_name="docker",
            status="active" if "success" in status else "failed",
        )

    for c in spec.containers:
        db.upsert_service(
            server_id=server_id,
            service_type="container",
            service_name=c.name,
            status="running" if "success" in status else "failed",
            metadata_json=json.dumps({"image": c.image}),
        )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="service",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_file_template_apply(
    db: InventoryDB,
    spec: FileTemplateSpec,
    apply_result: ApplyResult,
) -> None:
    """After a file_template apply, record template metadata + run in inventory."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    template_dests = [t.dest for t in spec.templates]
    db.upsert_service(
        server_id=server_id,
        service_type="file_template",
        service_name=f"file_template:{spec.meta.name}",
        status="active" if "success" in status else "failed",
        metadata_json=json.dumps(
            {
                "templates": template_dests,
                "template_count": len(template_dests),
            }
        ),
    )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="file_template",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_compose_project_apply(
    db: InventoryDB,
    spec: ComposeProjectSpec,
    apply_result: ApplyResult,
) -> None:
    """After a compose_project apply, record project metadata + run in inventory."""
    import json

    server_id = spec.host.name
    status = apply_result.status
    p = spec.project

    db.upsert_service(
        server_id=server_id,
        service_type="compose_project",
        service_name=p.name,
        status="active" if "success" in status else "failed",
        metadata_json=json.dumps(
            {
                "directory": p.directory,
                "compose_file": p.compose_file,
                "template_count": len(p.templates),
            }
        ),
    )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="compose_project",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_postgres_ensure_apply(
    db: InventoryDB,
    spec: PostgresEnsureSpec,
    apply_result: ApplyResult,
) -> None:
    """After a postgres_ensure apply, record PG resource metadata + run."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    db.upsert_service(
        server_id=server_id,
        service_type="postgres_ensure",
        service_name=f"pg_ensure:{spec.meta.name}",
        status="active" if "success" in status else "failed",
        metadata_json=json.dumps(
            {
                "users": [u.name for u in spec.users],
                "databases": [d.name for d in spec.databases],
                "extensions": [e.name for e in spec.extensions],
                "grants": len(spec.grants),
            }
        ),
    )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="postgres_ensure",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_backup_job_apply(
    db: InventoryDB,
    spec: BackupJobSpec,
    apply_result: ApplyResult,
) -> None:
    """After a backup_job apply, record backup metadata + run in inventory."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    db.upsert_service(
        server_id=server_id,
        service_type="backup_job",
        service_name=f"backup:{spec.backup.name}",
        status="active" if "success" in status else "failed",
        metadata_json=json.dumps(
            {
                "name": spec.backup.name,
                "source_type": spec.backup.source.type,
                "schedule": spec.backup.schedule,
                "retention_count": spec.backup.retention.count,
            }
        ),
    )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="backup_job",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_systemd_timer_apply(
    db: InventoryDB,
    spec: SystemdTimerSpec,
    apply_result: ApplyResult,
) -> None:
    """After a systemd_timer apply, record timer metadata + run in inventory."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    db.upsert_service(
        server_id=server_id,
        service_type="systemd_timer",
        service_name=spec.timer.timer_name,
        status="active" if "success" in status else "failed",
        metadata_json=json.dumps(
            {
                "timer_name": spec.timer.timer_name,
                "on_calendar": spec.timer.on_calendar,
                "exec_start": spec.service.exec_start,
            }
        ),
    )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="systemd_timer",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_systemd_unit_apply(
    db: InventoryDB,
    spec: SystemdUnitSpec,
    apply_result: ApplyResult,
) -> None:
    """After a systemd_unit apply, record unit metadata + run in inventory."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    db.upsert_service(
        server_id=server_id,
        service_type="systemd_unit",
        service_name=spec.unit.unit_name,
        status="active" if "success" in status else "failed",
        metadata_json=json.dumps(
            {
                "unit_name": spec.unit.unit_name,
                "exec_start": spec.unit.exec_start,
                "user": spec.unit.user,
            }
        ),
    )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="systemd_unit",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_http_check_apply(
    db: InventoryDB,
    spec: HttpCheckSpec,
    apply_result: ApplyResult,
) -> None:
    """After an http_check apply, record check metadata + run in inventory."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    db.upsert_service(
        server_id=server_id,
        service_type="http_check",
        service_name=f"http_check:{spec.meta.name}",
        status="active" if "success" in status else "failed",
        metadata_json=json.dumps(
            {
                "url": spec.check.url,
                "expected_status": spec.check.expected_status,
            }
        ),
    )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="http_check",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
    )


def record_stack_apply(
    db: InventoryDB,
    spec: StackSpec,
    apply_result: ApplyResult,
) -> None:
    """After a stack apply, record stack metadata + per-resource services + run."""
    import json

    server_id = spec.host.name
    status = apply_result.status

    # Record each resource as a service entry
    for res in spec.resources:
        db.upsert_service(
            server_id=server_id,
            service_type="stack_resource",
            service_name=f"{spec.meta.name}/{res.name}",
            status="active" if "success" in status else "failed",
            metadata_json=json.dumps(
                {
                    "stack": spec.meta.name,
                    "resource_kind": res.kind,
                    "depends_on": res.depends_on,
                }
            ),
        )

    db.record_run(
        id=apply_result.started_at.replace(":", "-").replace("+", "Z"),
        kind="stack",
        spec_hash=apply_result.plan.spec_hash,
        plan_hash=apply_result.plan.plan_hash,
        status=status,
        started_at=apply_result.started_at,
        finished_at=apply_result.finished_at,
        server_id=server_id,
        metadata_json=json.dumps(
            {
                "stack_name": spec.meta.name,
                "resource_count": len(spec.resources),
                "resources": [r.name for r in spec.resources],
            }
        ),
    )


def show_server(db: InventoryDB, server_id: str) -> dict | None:
    """Return server record with its services."""
    server = db.get_server(server_id)
    if server is None:
        return None
    server["services"] = db.get_services(server_id)
    return server


def list_inventory(db: InventoryDB) -> list[dict]:
    """Return all active server records."""
    return db.list_servers()
