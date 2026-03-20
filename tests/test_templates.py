"""Tests for the shared Jinja2 template rendering utilities."""

from pathlib import Path

import pytest

from nodeforge.utils.templates import (
    TemplateRenderError,
    content_hash,
    render_template_file,
    render_template_string,
)


# ---------------------------------------------------------------------------
# render_template_string
# ---------------------------------------------------------------------------


class TestRenderTemplateString:
    def test_simple_substitution(self):
        result = render_template_string("Hello {{ name }}!", {"name": "World"})
        assert result == "Hello World!"

    def test_multiple_variables(self):
        tpl = "{{ host }}:{{ port }}"
        result = render_template_string(tpl, {"host": "127.0.0.1", "port": "8080"})
        assert result == "127.0.0.1:8080"

    def test_empty_variables(self):
        result = render_template_string("static content", {})
        assert result == "static content"

    def test_undefined_variable_raises(self):
        with pytest.raises(TemplateRenderError, match="Failed to render"):
            render_template_string("{{ undefined_var }}", {})

    def test_jinja2_control_structures(self):
        tpl = "{% for i in items %}{{ i }} {% endfor %}"
        result = render_template_string(tpl, {"items": ["a", "b", "c"]})
        assert result == "a b c "

    def test_jinja2_conditionals(self):
        tpl = "{% if enabled %}on{% else %}off{% endif %}"
        assert render_template_string(tpl, {"enabled": True}) == "on"
        assert render_template_string(tpl, {"enabled": False}) == "off"

    def test_preserves_trailing_newline(self):
        result = render_template_string("line1\n", {})
        assert result.endswith("\n")


# ---------------------------------------------------------------------------
# render_template_file
# ---------------------------------------------------------------------------


class TestRenderTemplateFile:
    def test_renders_file(self, tmp_path: Path):
        tpl = tmp_path / "test.conf.j2"
        tpl.write_text("server_name {{ domain }};")
        result = render_template_file(tpl, {"domain": "example.com"})
        assert result == "server_name example.com;"

    def test_file_not_found(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.j2"
        with pytest.raises(TemplateRenderError, match="not found"):
            render_template_file(missing, {})

    def test_undefined_variable_in_file(self, tmp_path: Path):
        tpl = tmp_path / "test.j2"
        tpl.write_text("{{ missing_var }}")
        with pytest.raises(TemplateRenderError, match="Failed to render"):
            render_template_file(tpl, {})

    def test_multiline_template(self, tmp_path: Path):
        tpl = tmp_path / "nginx.conf.j2"
        tpl.write_text("server {\n    listen {{ port }};\n    server_name {{ domain }};\n}\n")
        result = render_template_file(tpl, {"port": "80", "domain": "example.com"})
        assert "listen 80;" in result
        assert "server_name example.com;" in result

    def test_template_with_sibling_includes(self, tmp_path: Path):
        """Jinja2's FileSystemLoader allows include/extends from the same directory."""
        base = tmp_path / "base.j2"
        base.write_text("BASE: {% block body %}{% endblock %}")
        child = tmp_path / "child.j2"
        child.write_text("{% extends 'base.j2' %}{% block body %}{{ content }}{% endblock %}")
        result = render_template_file(child, {"content": "hello"})
        assert result == "BASE: hello"


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self):
        h1 = content_hash("hello")
        h2 = content_hash("hello")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = content_hash("hello")
        h2 = content_hash("world")
        assert h1 != h2

    def test_returns_hex_string(self):
        h = content_hash("test")
        assert len(h) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)
