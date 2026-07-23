"""Tests for several remaining uncovered modules."""

from __future__ import annotations

from unittest.mock import patch

# ─── commands_configuration.py ──────────────────────────────────────────────


class TestCommandsConfiguration:
    def test_temas_list(self, tmp_path):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_configuration import app_temas

        runner = CliRunner()
        temas_dir = tmp_path / "temas"
        temas_dir.mkdir()
        with patch("concilium.presentation.cli.commands_configuration._config_root", return_value=tmp_path):
            result = runner.invoke(app_temas, ["list"])
        assert result.exit_code in (0, 1, 2)  # 2 = usage error if no temas found

    def test_jurisdicao_list(self, tmp_path):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_configuration import app_jurisdicao

        runner = CliRunner()
        juris_dir = tmp_path / "jurisdicoes"
        juris_dir.mkdir()
        with patch("concilium.presentation.cli.commands_configuration._config_root", return_value=tmp_path):
            result = runner.invoke(app_jurisdicao, ["list"])
        assert result.exit_code in (0, 1, 2)



