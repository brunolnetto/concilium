"""Tests for spec_loader helpers, MCP spec tool, commands, and query engine."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── commands_basic.py CLI ────────────────────────────────────────────────────


class TestCommandsBasic:
    def test_ps_help(self):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_basic import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

class TestRuntimeHelpersPipeline:
    def test_parse_executed_skills_returns_set(self, tmp_path):
        from concilium.application.runtime.helpers.pipeline import _parse_executed_skills

        result = _parse_executed_skills(tmp_path / "nofile.json")
        assert isinstance(result, set)

    def test_execute_skill_calls_fn(self):
        from concilium.application.runtime.helpers.pipeline import _execute_skill

        mock_fn = MagicMock()
        mock_fn.return_value = MagicMock(has_errors=False, validacoes=[])
        mock_store = MagicMock()
        _execute_skill(mock_fn, {"k": "v"}, "skill-01", "exec-1", "ts", mock_store)
        mock_fn.assert_called_once()

    def test_resolve_state_ok_result(self):
        from concilium.application.runtime.helpers.pipeline import _resolve_state

        result = MagicMock()
        result.has_errors = False
        result.canonical = MagicMock()
        state = _resolve_state("01-escopo-e-eap", result, {})
        assert state is not None

    def test_format_records_with_objects(self):
        from concilium.application.runtime.helpers.pipeline import _format_records

        rec = MagicMock()
        rec.skill_id = "01-escopo-e-eap"
        rec.status = "OK"
        rec.duration_s = 1.5
        rec.started_at = "2026-01-01"
        rec.finished_at = "2026-01-01"
        result = _format_records([rec])
        assert isinstance(result, list)
        assert len(result) == 1



