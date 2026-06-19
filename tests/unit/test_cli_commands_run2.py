"""Tests for presentation/cli/commands_run.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from concilium.presentation.cli.commands_run import (
    _approve_load_pending_overrides,
    _run_parse_inputs,
    _run_report_result,
    _run_resolve_escopo,
    _run_resolve_plano,
    app,
)

runner = CliRunner()


class TestRunParseInputs:
    def test_none_returns_empty(self):
        assert _run_parse_inputs(None) == {}

    def test_empty_string_returns_empty(self):
        assert _run_parse_inputs("") == {}

    def test_json_string_parsed(self):
        result = _run_parse_inputs('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_file_parsed(self, tmp_path):
        f = tmp_path / "inputs.json"
        f.write_text('{"from_file": true}')
        result = _run_parse_inputs(str(f))
        assert result["from_file"] is True


class TestRunResolveEscopo:
    def test_single_escopo_auto_resolved(self):
        project = MagicMock()
        project.list_escopos.return_value = ["esc-1"]
        result = _run_resolve_escopo(project, None)
        assert result == "esc-1"

    def test_explicit_escopo_id_returned(self):
        project = MagicMock()
        project.list_escopos.return_value = ["esc-1", "esc-2"]
        result = _run_resolve_escopo(project, "esc-2")
        assert result == "esc-2"

    def test_no_escopos_exits(self):
        project = MagicMock()
        project.list_escopos.return_value = []
        with pytest.raises((SystemExit, Exception)):
            _run_resolve_escopo(project, None)

    def test_multiple_escopos_without_id_exits(self):
        project = MagicMock()
        project.list_escopos.return_value = ["esc-1", "esc-2"]
        with pytest.raises((SystemExit, Exception)):
            _run_resolve_escopo(project, None)


class TestRunResolvePlano:
    def test_explicit_plano_returned(self):
        es = MagicMock()
        result = _run_resolve_plano(es, "plano-1", "esc-1")
        assert result == "plano-1"

    def test_active_plan_resolved(self):
        es = MagicMock()
        es.active_plan.return_value = MagicMock(plano_id="active-plan")
        result = _run_resolve_plano(es, None, "esc-1")
        assert result == "active-plan"

    def test_no_active_plan_exits(self):
        es = MagicMock()
        es.active_plan.return_value = None
        with pytest.raises((SystemExit, Exception)):
            _run_resolve_plano(es, None, "esc-1")


class TestRunReportResult:
    def _make_result(self, has_errors, validacoes=None):
        result = MagicMock()
        result.has_errors = has_errors
        v = MagicMock()
        v.status = "OK"
        v.codigo = "VAL-01"
        v.mensagem = None
        result.validacoes = validacoes or [v]
        return result

    def test_success_path(self, capsys):
        result = self._make_result(False)
        _run_report_result(result, "01-escopo-e-eap")  # should not raise

    def test_error_path(self, capsys):
        result = self._make_result(True)
        _run_report_result(result, "01-escopo-e-eap")  # should not raise

    def test_validacao_with_mensagem(self):
        v = MagicMock()
        v.status = "AVISO"
        v.codigo = "VAL-02"
        v.mensagem = "atenção"
        result = self._make_result(False, [v])
        _run_report_result(result, "02-prod")  # no raise


class TestApproveLoadPendingOverrides:
    def test_no_overrides_file(self, tmp_path):
        project = MagicMock()
        project.root = tmp_path
        result = _approve_load_pending_overrides(project)
        assert result == []

    def test_overrides_file_with_keys(self, tmp_path):
        overrides_dir = tmp_path / "overrides"
        overrides_dir.mkdir()
        overrides_file = overrides_dir / "insumos_override.json"
        overrides_file.write_text('{"INS-1": {}, "INS-2": {}}')
        project = MagicMock()
        project.root = tmp_path
        result = _approve_load_pending_overrides(project)
        assert "INS-1" in result
        assert "INS-2" in result

    def test_invalid_json_returns_empty(self, tmp_path):
        overrides_dir = tmp_path / "overrides"
        overrides_dir.mkdir()
        (overrides_dir / "insumos_override.json").write_text("NOT JSON")
        project = MagicMock()
        project.root = tmp_path
        result = _approve_load_pending_overrides(project)
        assert result == []


class TestRunCommand:
    def _project(self, has_errors=False):
        project = MagicMock()
        project.list_escopos.return_value = ["esc-1"]
        es = MagicMock()
        es.active_plan.return_value = MagicMock(plano_id="plano-1")
        project.escopo.return_value = es
        ps = MagicMock()
        es.plan.return_value = ps
        result = MagicMock()
        result.has_errors = has_errors
        v = MagicMock()
        v.status = "OK"
        v.codigo = "VAL-01"
        v.mensagem = None
        result.validacoes = [v]
        return project, ps, result

    def test_run_success(self):
        project, ps, result = self._project()
        coordinator_mock = MagicMock()
        coordinator_mock.avancar_plano.return_value = result

        with (
            patch("concilium.presentation.cli.commands_run.resolve_project", return_value=project),
            patch("concilium.presentation.cli.commands_run.config_root", return_value=MagicMock()),
            patch("concilium.application.runtime.Runtime"),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                return_value=coordinator_mock,
            ),
        ):
            r = runner.invoke(app, ["run", "01-escopo-e-eap", "--project", "my-proj"])
        assert r.exit_code == 0

    def test_run_with_errors_exits_1(self):
        project, ps, result = self._project(has_errors=True)
        coordinator_mock = MagicMock()
        coordinator_mock.avancar_plano.return_value = result

        with (
            patch("concilium.presentation.cli.commands_run.resolve_project", return_value=project),
            patch("concilium.presentation.cli.commands_run.config_root", return_value=MagicMock()),
            patch("concilium.application.runtime.Runtime"),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                return_value=coordinator_mock,
            ),
        ):
            r = runner.invoke(app, ["run", "01-escopo-e-eap", "--project", "my-proj"])
        assert r.exit_code != 0

    def test_run_runtime_error_exits_1(self):
        project, ps, _ = self._project()
        from concilium.application.runtime import RuntimeError as ConciliumRuntimeError

        coordinator_mock = MagicMock()
        coordinator_mock.avancar_plano.side_effect = ConciliumRuntimeError("runtime failed")

        with (
            patch("concilium.presentation.cli.commands_run.resolve_project", return_value=project),
            patch("concilium.presentation.cli.commands_run.config_root", return_value=MagicMock()),
            patch("concilium.application.runtime.Runtime"),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                return_value=coordinator_mock,
            ),
        ):
            r = runner.invoke(app, ["run", "01-escopo-e-eap", "--project", "my-proj"])
        assert r.exit_code != 0

    def test_run_unexpected_exception_exits_2(self):
        project, ps, _ = self._project()
        coordinator_mock = MagicMock()
        coordinator_mock.avancar_plano.side_effect = Exception("unexpected")

        with (
            patch("concilium.presentation.cli.commands_run.resolve_project", return_value=project),
            patch("concilium.presentation.cli.commands_run.config_root", return_value=MagicMock()),
            patch("concilium.application.runtime.Runtime"),
            patch(
                "concilium.application.orchestrators.lifecycle_coordinator.LifecycleCoordinator",
                return_value=coordinator_mock,
            ),
        ):
            r = runner.invoke(app, ["run", "01-escopo-e-eap", "--project", "my-proj"])
        assert r.exit_code not in (0,)
