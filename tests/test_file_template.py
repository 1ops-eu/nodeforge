"""Tests for file_template kind — schema, validation, steps, and planning."""

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from loft_cli.runtime.steps.file_template import chmod_file, chown_file, mkdir_for_file
from loft_cli_core.specs.file_template_schema import (
    FileTemplateLoginBlock,
    FileTemplateSpec,
    TemplateFileBlock,
)
from loft_cli_core.specs.validators import has_errors, validate_file_template

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_template_spec(**overrides) -> FileTemplateSpec:
    base = {
        "kind": "file_template",
        "meta": {"name": "test-ft", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
        "templates": [
            {
                "src": "templates/app.conf.j2",
                "dest": "/etc/app/app.conf",
                "mode": "0644",
                "owner": "root",
                "group": "root",
            }
        ],
    }
    base.update(overrides)
    return FileTemplateSpec.model_validate(base)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestFileTemplateSchema:
    def test_template_file_block_defaults(self):
        block = TemplateFileBlock(src="t.j2", dest="/etc/t.conf")
        assert block.mode == "0644"
        assert block.owner == "root"
        assert block.group == "root"

    def test_template_file_block_custom(self):
        block = TemplateFileBlock(
            src="t.j2", dest="/opt/app.conf", mode="0600", owner="app", group="app"
        )
        assert block.mode == "0600"
        assert block.owner == "app"

    def test_login_defaults(self):
        login = FileTemplateLoginBlock()
        assert login.user == "admin"
        assert login.port == 2222
        assert login.private_key == "~/.ssh/id_ed25519"
        assert login.password is None

    def test_spec_round_trip(self):
        spec = _make_file_template_spec()
        assert spec.kind == "file_template"
        assert len(spec.templates) == 1
        assert spec.templates[0].dest == "/etc/app/app.conf"
        assert spec.variables == {}

    def test_spec_with_variables(self):
        spec = _make_file_template_spec(variables={"port": "8080", "host": "0.0.0.0"})
        assert spec.variables["port"] == "8080"
        assert spec.variables["host"] == "0.0.0.0"

    def test_spec_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            _make_file_template_spec(unknown_field="bad")

    def test_template_block_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            TemplateFileBlock(src="t.j2", dest="/etc/t.conf", unknown="bad")

    def test_multiple_templates(self):
        spec = _make_file_template_spec(
            templates=[
                {"src": "a.j2", "dest": "/etc/a.conf"},
                {"src": "b.j2", "dest": "/etc/b.conf"},
            ]
        )
        assert len(spec.templates) == 2


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestFileTemplateValidation:
    def test_empty_templates_error(self):
        spec = _make_file_template_spec(templates=[])
        issues = validate_file_template(spec)
        assert has_errors(issues)
        assert any("At least one template" in i.message for i in issues)

    def test_empty_src_error(self):
        spec = _make_file_template_spec(templates=[{"src": "", "dest": "/etc/app.conf"}])
        issues = validate_file_template(spec)
        assert has_errors(issues)
        assert any("source path must not be empty" in i.message for i in issues)

    def test_relative_dest_error(self):
        spec = _make_file_template_spec(templates=[{"src": "t.j2", "dest": "relative/path"}])
        issues = validate_file_template(spec)
        assert has_errors(issues)
        assert any("absolute path" in i.message for i in issues)

    def test_empty_dest_error(self):
        spec = _make_file_template_spec(templates=[{"src": "t.j2", "dest": ""}])
        issues = validate_file_template(spec)
        assert has_errors(issues)
        assert any("absolute path" in i.message for i in issues)

    def test_invalid_mode_error(self):
        spec = _make_file_template_spec(
            templates=[{"src": "t.j2", "dest": "/etc/t.conf", "mode": "9999"}]
        )
        issues = validate_file_template(spec)
        assert has_errors(issues)
        assert any("Invalid file mode" in i.message for i in issues)

    def test_valid_mode_no_error(self):
        for mode in ["0644", "0755", "0600", "644", "755"]:
            spec = _make_file_template_spec(
                templates=[{"src": "t.j2", "dest": "/etc/t.conf", "mode": mode}]
            )
            issues = validate_file_template(spec)
            errors = [i for i in issues if i.severity == "error"]
            assert not errors, f"Mode {mode} should be valid"

    def test_duplicate_dest_error(self):
        spec = _make_file_template_spec(
            templates=[
                {"src": "a.j2", "dest": "/etc/app.conf"},
                {"src": "b.j2", "dest": "/etc/app.conf"},
            ]
        )
        issues = validate_file_template(spec)
        assert has_errors(issues)
        assert any("Duplicate destination" in i.message for i in issues)

    def test_valid_spec_no_errors(self):
        spec = _make_file_template_spec()
        issues = validate_file_template(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors


# ---------------------------------------------------------------------------
# Steps (command generation)
# ---------------------------------------------------------------------------


class TestFileTemplateSteps:
    def test_mkdir_for_file(self):
        cmd = mkdir_for_file("/etc/nginx/sites-available/app.conf")
        assert cmd == "mkdir -p /etc/nginx/sites-available"

    def test_mkdir_for_file_root(self):
        cmd = mkdir_for_file("/etc/app.conf")
        assert "mkdir -p" in cmd

    def test_chmod_file(self):
        cmd = chmod_file("/etc/app.conf", "0644")
        assert cmd == "chmod 0644 /etc/app.conf"

    def test_chown_file(self):
        cmd = chown_file("/etc/app.conf", "root", "root")
        assert cmd == "chown root:root /etc/app.conf"

    def test_chown_file_custom_owner(self):
        cmd = chown_file("/opt/app/config.yml", "app", "app")
        assert cmd == "chown app:app /opt/app/config.yml"


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class TestFileTemplatePlanner:
    @pytest.fixture
    def ft_yaml(self, tmp_path) -> Path:
        """Create a file_template spec with a real Jinja2 template."""
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        tpl = tpl_dir / "app.conf.j2"
        tpl.write_text("server_name {{ domain }};\nlisten {{ port }};\n")

        content = textwrap.dedent("""\
            kind: file_template
            meta:
              name: ft-test
              description: Test file_template planning
            host:
              name: test-node-1
              address: 192.168.1.100
              os_family: debian
            login:
              user: admin
              private_key: ~/.ssh/id_ed25519
              port: 2222
            templates:
              - src: templates/app.conf.j2
                dest: /etc/nginx/sites-available/app.conf
                mode: "0644"
                owner: root
                group: root
            variables:
              domain: example.com
              port: "80"
            local:
              inventory:
                enabled: false
            checks: []
        """)
        f = tmp_path / "file-template.yaml"
        f.write_text(content)
        return f

    def test_plan_has_file_template_steps(self, ft_yaml):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan
        from loft_cli_core.specs.loader import load_spec

        spec = load_spec(ft_yaml)
        ctx = normalize(spec, spec_dir=ft_yaml.parent)
        p = plan(ctx)

        ft_steps = [s for s in p.steps if "file_template" in s.tags]
        assert len(ft_steps) > 0

    def test_plan_has_preflight(self, ft_yaml):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan
        from loft_cli_core.specs.loader import load_spec

        spec = load_spec(ft_yaml)
        ctx = normalize(spec, spec_dir=ft_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "preflight_connect_admin" in step_ids

    def test_plan_has_per_template_steps(self, ft_yaml):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan
        from loft_cli_core.specs.loader import load_spec

        spec = load_spec(ft_yaml)
        ctx = normalize(spec, spec_dir=ft_yaml.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        # Each template produces: mkdir, upload, chmod, chown
        assert any(s.startswith("mkdir_") for s in step_ids)
        assert any(s.startswith("upload_") for s in step_ids)
        assert any(s.startswith("chmod_") for s in step_ids)
        assert any(s.startswith("chown_") for s in step_ids)

    def test_upload_step_has_rendered_content(self, ft_yaml):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan
        from loft_cli_core.specs.loader import load_spec

        spec = load_spec(ft_yaml)
        ctx = normalize(spec, spec_dir=ft_yaml.parent)
        p = plan(ctx)

        upload_steps = [s for s in p.steps if s.id.startswith("upload_")]
        assert len(upload_steps) == 1
        # Rendered content should contain the substituted domain
        assert "example.com" in upload_steps[0].file_content
        assert "listen 80" in upload_steps[0].file_content

    def test_file_template_remote_steps_are_sudo(self, ft_yaml):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan
        from loft_cli_core.specs.loader import load_spec

        spec = load_spec(ft_yaml)
        ctx = normalize(spec, spec_dir=ft_yaml.parent)
        p = plan(ctx)

        ft_remote = [s for s in p.steps if "file_template" in s.tags and s.scope.value == "remote"]
        for step in ft_remote:
            assert step.sudo is True, f"Step {step.id} should be sudo"

    def test_step_indices_sequential(self, ft_yaml):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan
        from loft_cli_core.specs.loader import load_spec

        spec = load_spec(ft_yaml)
        ctx = normalize(spec, spec_dir=ft_yaml.parent)
        p = plan(ctx)

        indices = [s.index for s in p.steps]
        assert indices == list(range(len(p.steps)))

    @pytest.fixture
    def ft_yaml_with_inventory(self, tmp_path) -> Path:
        """Spec with inventory enabled to test local steps."""
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        tpl = tpl_dir / "app.conf.j2"
        tpl.write_text("content = {{ value }}")

        content = textwrap.dedent("""\
            kind: file_template
            meta:
              name: ft-inv-test
              description: Test file_template with inventory
            host:
              name: test-node-1
              address: 192.168.1.100
              os_family: debian
            login:
              user: admin
              private_key: ~/.ssh/id_ed25519
              port: 2222
            templates:
              - src: templates/app.conf.j2
                dest: /etc/app/config.ini
            variables:
              value: "42"
            local:
              inventory:
                enabled: true
            checks: []
        """)
        f = tmp_path / "file-template-inv.yaml"
        f.write_text(content)
        return f

    def test_plan_with_inventory_has_local_steps(self, ft_yaml_with_inventory):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.planner import plan
        from loft_cli_core.specs.loader import load_spec

        spec = load_spec(ft_yaml_with_inventory)
        ctx = normalize(spec, spec_dir=ft_yaml_with_inventory.parent)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "open_or_init_local_inventory" in step_ids
        assert "update_file_template_metadata" in step_ids
        assert "record_file_template_run" in step_ids
