"""Tests for Markdown docs rendering."""

from loft_cli.compiler.normalizer import normalize
from loft_cli.compiler.planner import plan
from loft_cli_core.plan.render_markdown import render_markdown
from loft_cli_core.specs.loader import load_spec


def test_render_markdown_has_required_sections(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    p = plan(ctx)

    md = render_markdown(p, mode="guide")

    assert "## Remote Bootstrap" in md or "## Remote" in md
    assert "## Local Finalization" in md
    assert "## Verification" in md
    assert "## Recovery Notes" in md


def test_render_markdown_contains_spec_name(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    p = plan(ctx)

    md = render_markdown(p)
    assert "test-node" in md


def test_render_markdown_commands_mode(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    p = plan(ctx)

    md = render_markdown(p, mode="commands")
    assert "## Remote Steps" in md
