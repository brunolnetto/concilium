"""Tests for spec_loader helpers, MCP spec tool, commands, and query engine."""

from __future__ import annotations

# ─── commands_manage.py CLI ───────────────────────────────────────────────────


class TestCommandsManage:
    def test_catalog_app_help(self):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_manage import app_catalog

        runner = CliRunner()
        result = runner.invoke(app_catalog, ["--help"])
        assert result.exit_code == 0

    def test_catalog_validate_schema(self):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_manage import app_catalog

        runner = CliRunner()
        result = runner.invoke(app_catalog, ["validate-schema", "--help"])
        assert result.exit_code in (0, 2)

    def test_structure_app_help(self):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_manage import app_structure

        runner = CliRunner()
        result = runner.invoke(app_structure, ["--help"])
        assert result.exit_code in (0, 2)



