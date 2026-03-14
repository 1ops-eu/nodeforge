"""High-level inventory operations built on InventoryDB."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodeforge.local.sqlcipher import InventoryDB
    from nodeforge.runtime.executor import ApplyResult
    from nodeforge.specs.bootstrap_schema import BootstrapSpec
    from nodeforge.specs.service_schema import ServiceSpec


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_bootstrap(
    db: "InventoryDB",
    spec: "BootstrapSpec",
    apply_result: "ApplyResult",
) -> None:
    """After a successful bootstrap apply, record server + run in inventory."""
    from nodeforge.plan.models import StepKind

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
    db: "InventoryDB",
    spec: "ServiceSpec",
    apply_result: "ApplyResult",
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


def show_server(db: "InventoryDB", server_id: str) -> dict | None:
    """Return server record with its services."""
    server = db.get_server(server_id)
    if server is None:
        return None
    server["services"] = db.get_services(server_id)
    return server


def list_inventory(db: "InventoryDB") -> list[dict]:
    """Return all active server records."""
    return db.list_servers()
