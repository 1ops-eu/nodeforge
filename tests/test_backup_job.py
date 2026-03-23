"""Tests for backup_job kind -- schema, validation, step helpers, and planning."""

import pytest
from pydantic import ValidationError

from nodeforge.runtime.steps.backup import render_backup_script
from nodeforge_core.specs.backup_job_schema import (
    BackupJobSpec,
    BackupRetention,
    BackupSource,
)
from nodeforge_core.specs.validators import has_errors, validate_backup_job

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_backup_job_spec(**overrides) -> BackupJobSpec:
    base = {
        "kind": "backup_job",
        "meta": {"name": "test-bj", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "backup": {
            "name": "app-db",
            "source": {
                "type": "postgres_dump",
                "database": "myapp",
            },
            "destination": {"path": "/var/backups/nodeforge"},
        },
    }
    base.update(overrides)
    return BackupJobSpec.model_validate(base)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestBackupJobSchema:
    def test_retention_defaults(self):
        r = BackupRetention()
        assert r.count == 7

    def test_source_postgres_dump(self):
        s = BackupSource(type="postgres_dump", database="mydb")
        assert s.host == "localhost"
        assert s.port == 5432
        assert s.user == "postgres"

    def test_spec_round_trip(self):
        spec = _make_backup_job_spec()
        assert spec.kind == "backup_job"
        assert spec.backup.name == "app-db"
        assert spec.backup.source.type == "postgres_dump"
        assert spec.backup.schedule == "*-*-* 02:00:00"

    def test_spec_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_backup_job_spec(extra_field="nope")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestBackupJobValidation:
    def test_valid_spec(self):
        spec = _make_backup_job_spec()
        issues = validate_backup_job(spec)
        assert not has_errors(issues)

    def test_empty_name(self):
        spec = _make_backup_job_spec(
            backup={
                "name": "",
                "source": {"type": "postgres_dump", "database": "x"},
                "destination": {"path": "/var/backups"},
            }
        )
        issues = validate_backup_job(spec)
        assert has_errors(issues)

    def test_relative_destination(self):
        spec = _make_backup_job_spec(
            backup={
                "name": "x",
                "source": {"type": "postgres_dump", "database": "x"},
                "destination": {"path": "relative/path"},
            }
        )
        issues = validate_backup_job(spec)
        assert has_errors(issues)

    def test_postgres_dump_no_database(self):
        spec = _make_backup_job_spec(
            backup={
                "name": "x",
                "source": {"type": "postgres_dump"},
                "destination": {"path": "/var/backups"},
            }
        )
        issues = validate_backup_job(spec)
        assert has_errors(issues)

    def test_directory_no_path(self):
        spec = _make_backup_job_spec(
            backup={
                "name": "x",
                "source": {"type": "directory"},
                "destination": {"path": "/var/backups"},
            }
        )
        issues = validate_backup_job(spec)
        assert has_errors(issues)

    def test_directory_relative_path(self):
        spec = _make_backup_job_spec(
            backup={
                "name": "x",
                "source": {"type": "directory", "path": "relative"},
                "destination": {"path": "/var/backups"},
            }
        )
        issues = validate_backup_job(spec)
        assert has_errors(issues)

    def test_zero_retention(self):
        spec = _make_backup_job_spec(
            backup={
                "name": "x",
                "source": {"type": "postgres_dump", "database": "x"},
                "destination": {"path": "/var/backups"},
                "retention": {"count": 0},
            }
        )
        issues = validate_backup_job(spec)
        assert has_errors(issues)


# ---------------------------------------------------------------------------
# Step Helpers
# ---------------------------------------------------------------------------


class TestBackupStepHelpers:
    def test_render_postgres_dump_script(self):
        content = render_backup_script(
            name="app-db",
            source_type="postgres_dump",
            destination_path="/var/backups",
            retention_count=7,
            database="myapp",
            pg_host="localhost",
            pg_port=5432,
            pg_user="postgres",
        )
        assert "#!/bin/bash" in content
        assert "pg_dump" in content
        assert "myapp" in content
        assert "tail -n +8" in content  # retention: 7+1

    def test_render_postgres_dump_docker(self):
        content = render_backup_script(
            name="app-db",
            source_type="postgres_dump",
            destination_path="/var/backups",
            retention_count=3,
            database="mydb",
            docker_exec="pg-container",
        )
        assert "docker exec pg-container" in content

    def test_render_directory_script(self):
        content = render_backup_script(
            name="data",
            source_type="directory",
            destination_path="/var/backups",
            retention_count=5,
            source_path="/opt/app/data",
        )
        assert "tar czf" in content
        assert "/opt/app/data" in content


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


class TestBackupJobPlanning:
    def test_plan_generates_backup_steps(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_backup_job_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        assert p.spec_kind == "backup_job"
        step_ids = [s.id for s in p.steps]
        assert "write_backup_script_app-db" in step_ids
        assert "chmod_backup_script_app-db" in step_ids
        assert "write_backup_service_app-db" in step_ids
        assert "write_backup_timer_app-db" in step_ids
        assert "systemd_daemon_reload" in step_ids
        assert "enable_start_backup_timer_app-db" in step_ids

    def test_plan_backup_script_content(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_backup_job_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        script_step = next(s for s in p.steps if s.id == "write_backup_script_app-db")
        assert "pg_dump" in script_step.file_content
        assert "myapp" in script_step.file_content

    def test_plan_service_is_oneshot(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_backup_job_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        svc_step = next(s for s in p.steps if s.id == "write_backup_service_app-db")
        assert "Type=oneshot" in svc_step.file_content

    def test_plan_has_inventory_steps(self):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan

        spec = _make_backup_job_spec()
        ctx = normalize(spec)
        p = plan(ctx)

        inv_steps = [s for s in p.steps if "inventory" in s.tags]
        assert len(inv_steps) == 3
