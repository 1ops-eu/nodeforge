"""Tests for compose_project kind — schema, validation, steps, and planning."""

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from nodeforge.runtime.steps.compose import (
    compose_config,
    compose_down,
    compose_pull,
    compose_up,
    mkdir_with_permissions,
)
from nodeforge_core.specs.compose_project_schema import (
    ComposeHealthCheckBlock,
    ComposeProjectBlock,
    ComposeProjectSpec,
    ComposeTemplateBlock,
    ManagedDirectoryBlock,
)
from nodeforge_core.specs.validators import has_errors, validate_compose_project

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compose_spec(**overrides) -> ComposeProjectSpec:
    base = {
        "kind": "compose_project",
        "meta": {"name": "test-compose", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "project": {
            "name": "demo",
            "directory": "/opt/demo",
            "compose_file": "docker-compose.yml",
        },
    }
    base.update(overrides)
    return ComposeProjectSpec.model_validate(base)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestComposeProjectSchema:
    def test_compose_template_block(self):
        block = ComposeTemplateBlock(src="templates/app.j2", dest="app.conf")
        assert block.src == "templates/app.j2"
        assert block.dest == "app.conf"

    def test_managed_directory_defaults(self):
        d = ManagedDirectoryBlock(path="data")
        assert d.mode == "0755"
        assert d.owner == "root"
        assert d.group == "root"

    def test_managed_directory_custom(self):
        d = ManagedDirectoryBlock(path="/var/data", mode="0700", owner="app", group="app")
        assert d.path == "/var/data"
        assert d.mode == "0700"

    def test_healthcheck_defaults(self):
        hc = ComposeHealthCheckBlock()
        assert hc.enabled is True
        assert hc.timeout == 120
        assert hc.interval == 5

    def test_project_block_defaults(self):
        p = ComposeProjectBlock(name="test", directory="/opt/test")
        assert p.compose_file == "docker-compose.yml"
        assert p.templates == []
        assert p.variables == {}
        assert p.directories == []
        assert p.pull_before_up is True
        assert p.healthcheck.enabled is True

    def test_spec_round_trip(self):
        spec = _make_compose_spec()
        assert spec.kind == "compose_project"
        assert spec.project.name == "demo"
        assert spec.project.directory == "/opt/demo"

    def test_spec_with_templates_and_dirs(self):
        spec = _make_compose_spec(
            project={
                "name": "demo",
                "directory": "/opt/demo",
                "templates": [{"src": "t.j2", "dest": "app.conf"}],
                "variables": {"port": "8080"},
                "directories": [{"path": "data"}],
            }
        )
        assert len(spec.project.templates) == 1
        assert spec.project.variables["port"] == "8080"
        assert len(spec.project.directories) == 1

    def test_spec_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_compose_spec(unknown_field="bad")

    def test_project_block_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            ComposeProjectBlock(name="test", directory="/opt/test", unknown_field="bad")

    def test_template_block_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            ComposeTemplateBlock(src="t.j2", dest="d", unknown="bad")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestComposeProjectValidation:
    def test_empty_project_name_error(self):
        spec = _make_compose_spec(project={"name": "", "directory": "/opt/test"})
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("project name must not be empty" in i.message.lower() for i in issues)

    def test_relative_directory_error(self):
        spec = _make_compose_spec(project={"name": "test", "directory": "relative/path"})
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("absolute path" in i.message for i in issues)

    def test_empty_template_src_error(self):
        spec = _make_compose_spec(
            project={
                "name": "test",
                "directory": "/opt/test",
                "templates": [{"src": "", "dest": "app.conf"}],
            }
        )
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("source path must not be empty" in i.message for i in issues)

    def test_empty_template_dest_error(self):
        spec = _make_compose_spec(
            project={
                "name": "test",
                "directory": "/opt/test",
                "templates": [{"src": "t.j2", "dest": ""}],
            }
        )
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("destination filename must not be empty" in i.message.lower() for i in issues)

    def test_duplicate_template_dest_error(self):
        spec = _make_compose_spec(
            project={
                "name": "test",
                "directory": "/opt/test",
                "templates": [
                    {"src": "a.j2", "dest": "app.conf"},
                    {"src": "b.j2", "dest": "app.conf"},
                ],
            }
        )
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("Duplicate template destination" in i.message for i in issues)

    def test_negative_timeout_error(self):
        spec = _make_compose_spec(
            project={
                "name": "test",
                "directory": "/opt/test",
                "healthcheck": {"timeout": -1, "interval": 5},
            }
        )
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("timeout must be positive" in i.message.lower() for i in issues)

    def test_negative_interval_error(self):
        spec = _make_compose_spec(
            project={
                "name": "test",
                "directory": "/opt/test",
                "healthcheck": {"timeout": 120, "interval": 0},
            }
        )
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("interval must be positive" in i.message.lower() for i in issues)

    def test_absolute_directory_path_warning(self):
        spec = _make_compose_spec(
            project={
                "name": "test",
                "directory": "/opt/test",
                "directories": [{"path": "/absolute/dir"}],
            }
        )
        issues = validate_compose_project(spec)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("absolute" in w.message.lower() for w in warnings)

    def test_invalid_directory_mode_error(self):
        spec = _make_compose_spec(
            project={
                "name": "test",
                "directory": "/opt/test",
                "directories": [{"path": "data", "mode": "9999"}],
            }
        )
        issues = validate_compose_project(spec)
        assert has_errors(issues)
        assert any("Invalid directory mode" in i.message for i in issues)

    def test_valid_spec_no_errors(self):
        spec = _make_compose_spec()
        issues = validate_compose_project(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors


# ---------------------------------------------------------------------------
# Steps (command generation)
# ---------------------------------------------------------------------------


class TestComposeSteps:
    def test_mkdir_with_permissions(self):
        cmd = mkdir_with_permissions("/opt/demo/data", "0755", "root", "root")
        assert "mkdir -p /opt/demo/data" in cmd
        assert "chmod 0755 /opt/demo/data" in cmd
        assert "chown root:root /opt/demo/data" in cmd
        assert cmd.startswith("bash -c '")

    def test_compose_config(self):
        cmd = compose_config("/opt/demo", "docker-compose.yml", "demo")
        assert "cd /opt/demo" in cmd
        assert "docker compose" in cmd
        assert "-f docker-compose.yml" in cmd
        assert "-p demo" in cmd
        assert "config" in cmd

    def test_compose_pull(self):
        cmd = compose_pull("/opt/demo", "docker-compose.yml", "demo")
        assert "cd /opt/demo" in cmd
        assert "pull" in cmd
        assert "-p demo" in cmd

    def test_compose_up(self):
        cmd = compose_up("/opt/demo", "docker-compose.yml", "demo")
        assert "cd /opt/demo" in cmd
        assert "up -d" in cmd
        assert "-p demo" in cmd

    def test_compose_down(self):
        cmd = compose_down("/opt/demo", "docker-compose.yml", "demo")
        assert "cd /opt/demo" in cmd
        assert "down" in cmd
        assert "-p demo" in cmd

    def test_all_commands_use_bash_wrapper(self):
        """All compose commands must use bash -c for Fabric sudo compatibility."""
        for cmd in [
            mkdir_with_permissions("/opt/x", "0755", "root", "root"),
            compose_config("/opt/x", "dc.yml", "proj"),
            compose_pull("/opt/x", "dc.yml", "proj"),
            compose_up("/opt/x", "dc.yml", "proj"),
            compose_down("/opt/x", "dc.yml", "proj"),
        ]:
            assert cmd.startswith("bash -c '"), f"Command should use bash wrapper: {cmd}"


# ---------------------------------------------------------------------------
# Compose health check parsing
# ---------------------------------------------------------------------------


class TestComposeHealthCheckParsing:
    def test_parse_ndjson(self):
        from nodeforge.checks.compose import _parse_compose_ps

        stdout = (
            '{"Name":"demo-app-1","State":"running","Health":"healthy","Service":"app"}\n'
            '{"Name":"demo-redis-1","State":"running","Health":"","Service":"redis"}\n'
        )
        containers = _parse_compose_ps(stdout)
        assert len(containers) == 2
        assert containers[0]["name"] == "demo-app-1"
        assert containers[0]["state"] == "running"
        assert containers[1]["name"] == "demo-redis-1"

    def test_parse_json_array(self):
        from nodeforge.checks.compose import _parse_compose_ps

        stdout = '[{"Name":"app","State":"running","Health":"","Service":"app"}]'
        containers = _parse_compose_ps(stdout)
        assert len(containers) == 1

    def test_parse_empty(self):
        from nodeforge.checks.compose import _parse_compose_ps

        assert _parse_compose_ps("") == []
        assert _parse_compose_ps("  \n  ") == []

    def test_container_healthy_running(self):
        from nodeforge.checks.compose import _is_container_healthy

        assert _is_container_healthy({"state": "running", "health": "healthy"}) is True

    def test_container_healthy_no_healthcheck(self):
        from nodeforge.checks.compose import _is_container_healthy

        assert _is_container_healthy({"state": "running", "health": ""}) is True

    def test_container_unhealthy(self):
        from nodeforge.checks.compose import _is_container_healthy

        assert _is_container_healthy({"state": "running", "health": "unhealthy"}) is False

    def test_container_not_running(self):
        from nodeforge.checks.compose import _is_container_healthy

        assert _is_container_healthy({"state": "exited", "health": ""}) is False

    def test_parse_lowercase_fields(self):
        """Docker Compose v2 may use lowercase field names."""
        from nodeforge.checks.compose import _parse_compose_ps

        stdout = '{"name":"app","state":"running","health":"healthy","service":"app"}\n'
        containers = _parse_compose_ps(stdout)
        assert len(containers) == 1
        assert containers[0]["name"] == "app"
        assert containers[0]["state"] == "running"


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class TestComposeProjectPlanner:
    @pytest.fixture
    def compose_yaml(self, tmp_path) -> Path:
        """Create a compose_project spec with real template and compose files."""
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        tpl = tpl_dir / "nginx.conf.j2"
        tpl.write_text("server_name {{ domain }};\n")

        dc = tmp_path / "docker-compose.yml"
        dc.write_text("services:\n  app:\n    image: nginx:alpine\n")

        content = textwrap.dedent("""\
            kind: compose_project
            meta:
              name: compose-test
              description: Test compose_project planning
            host:
              name: test-node-1
              address: 192.168.1.100
              os_family: debian
            login:
              user: admin
              private_key: ~/.ssh/id_ed25519
              port: 2222
            project:
              name: demo-stack
              directory: /opt/demo-stack
              compose_file: docker-compose.yml
              templates:
                - src: templates/nginx.conf.j2
                  dest: nginx.conf
              variables:
                domain: example.com
              directories:
                - path: data
                  mode: "0755"
                  owner: root
                  group: root
              pull_before_up: true
              healthcheck:
                enabled: true
                timeout: 60
                interval: 3
            local:
              inventory:
                enabled: false
            checks: []
        """)
        f = tmp_path / "compose-project.yaml"
        f.write_text(content)
        return f

    def test_plan_has_compose_steps(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        compose_steps = [s for s in p.steps if "compose" in s.tags]
        assert len(compose_steps) > 0

    def test_plan_has_preflight(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "preflight_connect_admin" in step_ids

    def test_plan_has_project_dir_step(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "mkdir_project_dir" in step_ids

    def test_plan_has_managed_directory_step(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        # "data" directory relative to /opt/demo-stack -> /opt/demo-stack/data
        mkdir_steps = [
            sid for sid in step_ids if sid.startswith("mkdir_") and sid != "mkdir_project_dir"
        ]
        assert len(mkdir_steps) >= 1

    def test_plan_has_template_upload(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        upload_steps = [s for s in p.steps if s.id.startswith("upload_template_")]
        assert len(upload_steps) == 1
        # Should contain rendered content
        assert "example.com" in upload_steps[0].file_content

    def test_plan_has_compose_file_upload(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "upload_compose_file" in step_ids
        # Compose file content should be the raw docker-compose.yml
        upload_step = [s for s in p.steps if s.id == "upload_compose_file"][0]
        assert "nginx:alpine" in upload_step.file_content

    def test_plan_has_compose_lifecycle_steps(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "compose_config_validate" in step_ids
        assert "compose_pull" in step_ids
        assert "compose_up" in step_ids

    def test_plan_has_health_check(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "compose_health_check" in step_ids
        hc_step = [s for s in p.steps if s.id == "compose_health_check"][0]
        # Command encodes the health check parameters
        assert "compose_health:" in hc_step.command
        assert ":60:" in hc_step.command  # timeout
        assert ":3" in hc_step.command  # interval

    def test_compose_remote_steps_are_sudo(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        compose_remote = [s for s in p.steps if "compose" in s.tags and s.scope.value == "remote"]
        for step in compose_remote:
            assert step.sudo is True, f"Step {step.id} should be sudo"

    def test_step_indices_sequential(self, compose_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml)
        ctx = normalize(spec, spec_dir=compose_yaml.parent)
        p = plan(ctx)

        indices = [s.index for s in p.steps]
        assert indices == list(range(len(p.steps)))

    @pytest.fixture
    def compose_yaml_no_pull(self, tmp_path) -> Path:
        """Spec with pull_before_up=false."""
        dc = tmp_path / "docker-compose.yml"
        dc.write_text("services:\n  app:\n    image: nginx:alpine\n")

        content = textwrap.dedent("""\
            kind: compose_project
            meta:
              name: compose-no-pull
              description: Test without pull
            host:
              name: test-node-1
              address: 192.168.1.100
              os_family: debian
            project:
              name: demo
              directory: /opt/demo
              compose_file: docker-compose.yml
              pull_before_up: false
              healthcheck:
                enabled: false
            local:
              inventory:
                enabled: false
            checks: []
        """)
        f = tmp_path / "compose-no-pull.yaml"
        f.write_text(content)
        return f

    def test_plan_without_pull(self, compose_yaml_no_pull):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml_no_pull)
        ctx = normalize(spec, spec_dir=compose_yaml_no_pull.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "compose_pull" not in step_ids
        assert "compose_health_check" not in step_ids
        # But compose_up should still be there
        assert "compose_up" in step_ids

    @pytest.fixture
    def compose_yaml_with_inventory(self, tmp_path) -> Path:
        """Spec with inventory enabled."""
        dc = tmp_path / "docker-compose.yml"
        dc.write_text("services:\n  app:\n    image: nginx:alpine\n")

        content = textwrap.dedent("""\
            kind: compose_project
            meta:
              name: compose-inv
              description: Test with inventory
            host:
              name: test-node-1
              address: 192.168.1.100
              os_family: debian
            project:
              name: demo
              directory: /opt/demo
              compose_file: docker-compose.yml
              healthcheck:
                enabled: false
            local:
              inventory:
                enabled: true
            checks: []
        """)
        f = tmp_path / "compose-inv.yaml"
        f.write_text(content)
        return f

    def test_plan_with_inventory_has_local_steps(self, compose_yaml_with_inventory):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(compose_yaml_with_inventory)
        ctx = normalize(spec, spec_dir=compose_yaml_with_inventory.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "open_or_init_local_inventory" in step_ids
        assert "update_compose_project_metadata" in step_ids
        assert "record_compose_project_run" in step_ids
