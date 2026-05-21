from typer.testing import CliRunner

from concilium.presentation.main import app

runner = CliRunner()


def test_catalog_help_lists_flat_commands() -> None:
    result = runner.invoke(app, ["catalog", "--help"])

    assert result.exit_code == 0
    assert "quality" in result.stdout
    assert "simulate" in result.stdout
    assert "export" in result.stdout
    assert "survey" in result.stdout
    assert "promote" in result.stdout
    assert "search" in result.stdout
    assert "validate-schema" in result.stdout


def test_project_catalog_help_is_flat() -> None:
    result = runner.invoke(app, ["project", "catalog", "--help"])

    assert result.exit_code == 0
    assert "quality" in result.stdout
    assert "promote" in result.stdout
    assert "validate-schema" in result.stdout


def test_benchmark_help_renders_without_encoding_error() -> None:
    result = runner.invoke(app, ["benchmark", "--help"])
    # Just check that help renders without encoding/exception errors
    assert result.exit_code == 0
    assert "run" in result.stdout or "benchmark" in result.stdout
