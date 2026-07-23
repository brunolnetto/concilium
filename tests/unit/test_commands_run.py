"""Coverage sweep 3 — files with 20-35 lines missing."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ─── presentation/cli/commands_run.py helpers ────────────────────────────────


class TestCommandsRunHelpers:
    def test_run_parse_inputs_empty(self):
        from concilium.presentation.cli.commands_run import _run_parse_inputs

        result = _run_parse_inputs(None)
        assert result == {}

    def test_run_parse_inputs_valid_json(self):
        import json

        from concilium.presentation.cli.commands_run import _run_parse_inputs

        data = {"key": "value"}
        result = _run_parse_inputs(json.dumps(data))
        assert result == data

    def test_run_parse_inputs_invalid_json_raises(self):
        import typer

        from concilium.presentation.cli.commands_run import _run_parse_inputs

        with pytest.raises((typer.Exit, SystemExit, Exception)):
            _run_parse_inputs("not json")

    def test_run_report_result_no_errors(self):
        from concilium.presentation.cli.commands_run import _run_report_result

        result = MagicMock()
        result.has_errors = False
        result.validacoes = []
        _run_report_result(result, "01-escopo-e-eap")  # should not raise

    def test_approve_load_pending_overrides_empty(self):
        from concilium.presentation.cli.commands_run import _approve_load_pending_overrides

        project = MagicMock()
        project.read_json.return_value = {}
        result = _approve_load_pending_overrides(project)
        assert isinstance(result, list)



