"""CLI tests for the plan command."""

from typer.testing import CliRunner

from nodeforge.cli import app

runner = CliRunner()


def test_plan_shows_steps(bootstrap_yaml):
    result = runner.invoke(app, ["plan", str(bootstrap_yaml)])
    assert result.exit_code == 0
    assert "verify_admin_login_on_new_port" in result.output


def test_plan_shows_target(bootstrap_yaml):
    result = runner.invoke(app, ["plan", str(bootstrap_yaml)])
    assert result.exit_code == 0
    assert "192.168.1.100" in result.output


def test_docs_produces_markdown(bootstrap_yaml, tmp_path):
    out = tmp_path / "docs.md"
    result = runner.invoke(app, ["docs", str(bootstrap_yaml), "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    content = out.read_text()
    assert "## Recovery Notes" in content
