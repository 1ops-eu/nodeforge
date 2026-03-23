"""Tests for kind: stack — schema, validation, and planning."""

import textwrap
from pathlib import Path

import pytest

from nodeforge_core.specs.stack_schema import (
    StackLocalBlock,
    StackLoginBlock,
    StackResourceBlock,
    StackSpec,
)
from nodeforge_core.specs.validators import has_errors, validate_stack

# ── Schema tests ─────────────────────────────────────────────────────────────


class TestStackSchema:
    def test_minimal_stack_spec(self):
        spec = StackSpec.model_validate(
            {
                "kind": "stack",
                "meta": {"name": "my-stack"},
                "host": {"name": "node1", "address": "10.0.0.1"},
                "resources": [
                    {"name": "nginx-conf", "kind": "file_template", "config": {}},
                ],
            }
        )
        assert spec.kind == "stack"
        assert spec.meta.name == "my-stack"
        assert len(spec.resources) == 1
        assert spec.resources[0].name == "nginx-conf"

    def test_login_defaults(self):
        login = StackLoginBlock()
        assert login.user == "admin"
        assert login.port == 2222

    def test_local_defaults(self):
        local = StackLocalBlock()
        assert local.state_dir == ""

    def test_resource_with_depends_on(self):
        spec = StackSpec.model_validate(
            {
                "kind": "stack",
                "meta": {"name": "app"},
                "host": {"name": "n1", "address": "10.0.0.1"},
                "resources": [
                    {"name": "db-config", "kind": "file_template"},
                    {
                        "name": "app",
                        "kind": "compose_project",
                        "depends_on": ["db-config"],
                    },
                ],
            }
        )
        assert spec.resources[1].depends_on == ["db-config"]

    def test_extra_fields_rejected(self):
        with pytest.raises(ValueError):  # Pydantic ValidationError
            StackSpec.model_validate(
                {
                    "kind": "stack",
                    "meta": {"name": "test"},
                    "host": {"name": "n1", "address": "10.0.0.1"},
                    "bogus_field": True,
                }
            )


# ── Validator tests ──────────────────────────────────────────────────────────


class TestStackValidator:
    def _make_stack(self, resources):
        return StackSpec.model_validate(
            {
                "kind": "stack",
                "meta": {"name": "test-stack"},
                "host": {"name": "n1", "address": "10.0.0.1"},
                "resources": resources,
            }
        )

    def test_empty_resources_is_error(self):
        spec = self._make_stack([])
        issues = validate_stack(spec)
        assert has_errors(issues)
        assert any("at least one resource" in i.message for i in issues)

    def test_duplicate_resource_names_is_error(self):
        spec = self._make_stack(
            [
                {"name": "dup", "kind": "file_template"},
                {"name": "dup", "kind": "compose_project"},
            ]
        )
        issues = validate_stack(spec)
        assert has_errors(issues)
        assert any("Duplicate resource name" in i.message for i in issues)

    def test_missing_dependency_is_error(self):
        spec = self._make_stack(
            [
                {
                    "name": "app",
                    "kind": "file_template",
                    "depends_on": ["nonexistent"],
                },
            ]
        )
        issues = validate_stack(spec)
        assert has_errors(issues)
        assert any("not found" in i.message for i in issues)

    def test_circular_dependency_is_error(self):
        spec = self._make_stack(
            [
                {"name": "a", "kind": "file_template", "depends_on": ["b"]},
                {"name": "b", "kind": "file_template", "depends_on": ["a"]},
            ]
        )
        issues = validate_stack(spec)
        assert has_errors(issues)
        assert any("Circular" in i.message for i in issues)

    def test_valid_stack_passes(self):
        spec = self._make_stack(
            [
                {"name": "config", "kind": "file_template"},
                {
                    "name": "app",
                    "kind": "compose_project",
                    "depends_on": ["config"],
                },
            ]
        )
        issues = validate_stack(spec)
        # May have warnings about unknown kinds (if registries aren't loaded),
        # but specifically no errors about stack structure itself should appear
        # for name uniqueness, dependencies, or cycles.
        structural_errors = [
            i
            for i in issues
            if i.severity == "error"
            and (
                "Duplicate" in i.message
                or "not found" in i.message
                or "Circular" in i.message
                or "at least one" in i.message
            )
        ]
        assert not structural_errors


# ── Planner tests ────────────────────────────────────────────────────────────


class TestStackPlanner:
    def test_topo_sort_orders_dependencies_first(self):
        from nodeforge.compiler.planner import _topo_sort

        resources = [
            StackResourceBlock(name="c", kind="file_template", depends_on=["b"]),
            StackResourceBlock(name="a", kind="file_template"),
            StackResourceBlock(name="b", kind="file_template", depends_on=["a"]),
        ]
        ordered = _topo_sort(resources)
        names = [r.name for r in ordered]
        assert names.index("a") < names.index("b")
        assert names.index("b") < names.index("c")

    def test_topo_sort_no_deps(self):
        from nodeforge.compiler.planner import _topo_sort

        resources = [
            StackResourceBlock(name="x", kind="file_template"),
            StackResourceBlock(name="y", kind="compose_project"),
        ]
        ordered = _topo_sort(resources)
        assert len(ordered) == 2

    def test_plan_stack_prefixes_step_ids(self):
        """Stack planner should prefix child step IDs with stack_{resource_name}_."""
        from nodeforge.compiler.normalizer import NormalizedContext
        from nodeforge.compiler.planner import _plan_stack

        spec = StackSpec.model_validate(
            {
                "kind": "stack",
                "meta": {"name": "test-stack"},
                "host": {"name": "n1", "address": "10.0.0.1"},
                "login": {"user": "admin", "port": 2222},
                "local": {"inventory": {"enabled": False}},
                "resources": [
                    {
                        "name": "myconf",
                        "kind": "file_template",
                        "config": {
                            "templates": [
                                {
                                    "src": "dummy.j2",
                                    "dest": "/etc/test.conf",
                                }
                            ],
                            "variables": {},
                        },
                    },
                ],
            }
        )
        ctx = NormalizedContext(spec=spec, spec_dir=Path("/tmp"))
        steps = _plan_stack(spec, ctx)
        # All steps from the child resource should be prefixed
        resource_steps = [s for s in steps if s.id.startswith("stack_myconf_")]
        assert len(resource_steps) > 0


# ── YAML loading ─────────────────────────────────────────────────────────────


class TestStackYamlLoading:
    def test_load_stack_yaml(self, tmp_path):
        spec_file = tmp_path / "stack.yaml"
        spec_file.write_text(textwrap.dedent("""\
            kind: stack
            meta:
              name: my-app
            host:
              name: web1
              address: 10.0.0.5
            resources:
              - name: config
                kind: file_template
                config:
                  templates:
                    - src: nginx.conf.j2
                      dest: /etc/nginx/nginx.conf
              - name: app
                kind: compose_project
                depends_on:
                  - config
                config:
                  project:
                    name: my-app
                    directory: /opt/my-app
                    compose_file: docker-compose.yml
        """))
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(spec_file)
        assert isinstance(spec, StackSpec)
        assert spec.meta.name == "my-app"
        assert len(spec.resources) == 2
        assert spec.resources[1].depends_on == ["config"]
