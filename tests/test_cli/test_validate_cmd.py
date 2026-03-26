"""CLI tests for the validate command."""

from typer.testing import CliRunner

from loft_cli.cli import app

runner = CliRunner()


def test_validate_valid_spec(bootstrap_yaml):
    result = runner.invoke(app, ["validate", str(bootstrap_yaml)])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_validate_missing_file(tmp_path):
    result = runner.invoke(app, ["validate", str(tmp_path / "missing.yaml")])
    assert result.exit_code != 0


def test_validate_invalid_yaml(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("{ invalid yaml")
    result = runner.invoke(app, ["validate", str(f)])
    assert result.exit_code != 0
