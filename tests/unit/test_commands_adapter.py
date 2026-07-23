"""Tests for several remaining uncovered modules."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ─── commands_adapter.py ────────────────────────────────────────────────────


class TestCommandsAdapter:
    def test_adapter_run_no_version(self):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_adapter import app

        runner = CliRunner()
        mock_project = MagicMock()
        mock_project.current_version.return_value = None
        with (
            patch("concilium.presentation.cli.shared.resolve_project", return_value=mock_project),
            patch("concilium.presentation.cli.shared.parse_project_version", return_value=("proj", None)),
            patch("concilium.presentation.cli.commands_adapter.config_root", return_value=Path("/fake")),
            patch("concilium.presentation.cli.commands_adapter.resolve_project", return_value=mock_project),
            patch("concilium.presentation.cli.commands_adapter.parse_project_version", return_value=("proj", None)),
        ):
            result = runner.invoke(app, ["run", "proj"])
        assert result.exit_code != 0

    def test_adapter_run_with_errors(self):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_adapter import app

        runner = CliRunner()
        mock_project = MagicMock()
        mock_project.current_version.return_value = "v1"
        mock_result = MagicMock()
        mock_result.has_errors = True
        mock_result.validacoes = []
        with (
            patch("concilium.presentation.cli.commands_adapter.resolve_project", return_value=mock_project),
            patch("concilium.presentation.cli.commands_adapter.parse_project_version", return_value=("proj", None)),
            patch("concilium.presentation.cli.commands_adapter.config_root", return_value=Path("/fake")),
            patch("concilium.application.runtime.Runtime") as mock_rt_cls,
        ):
            mock_rt = MagicMock()
            mock_rt.run_skill.return_value = mock_result
            mock_rt_cls.return_value = mock_rt
            result = runner.invoke(app, ["run", "proj"])
        assert result.exit_code != 0



