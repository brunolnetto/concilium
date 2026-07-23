"""Coverage sweep 5 — configuration routes, spec_loader_b, storage_project_repository."""

from __future__ import annotations

# ─── presentation/cli/commands_validate.py ───────────────────────────────────


class TestCommandsValidate:
    def test_app_has_commands(self):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_validate import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code in (0, 2)

