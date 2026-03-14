"""Tests for Rich text plan rendering."""
from rich.console import Console
from io import StringIO

from nodeforge.specs.loader import load_spec
from nodeforge.compiler.normalizer import normalize
from nodeforge.compiler.planner import plan
from nodeforge.plan.render_text import render_plan


def test_render_plan_produces_output(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    p = plan(ctx)

    buf = StringIO()
    console = Console(file=buf, no_color=True)
    render_plan(p, console=console)
    output = buf.getvalue()

    assert "test-node" in output
    assert "bootstrap" in output
    assert "verify_admin_login_on_new_port" in output


def test_render_plan_shows_gate(bootstrap_yaml):
    spec = load_spec(bootstrap_yaml)
    ctx = normalize(spec)
    p = plan(ctx)

    buf = StringIO()
    console = Console(file=buf, no_color=True, width=200)
    render_plan(p, console=console)
    output = buf.getvalue()

    assert "YES" in output  # gate column
