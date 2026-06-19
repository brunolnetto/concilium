"""Tests for MCP pipeline tools, analysis routes, and runner helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# ─── MCP pipeline helpers ────────────────────────────────────────────────────


class TestMcpPipelineHelpers:
    def test_rpl_executadas_ok_filters_ok(self):
        from concilium.presentation.mcp.tools.pipeline import _rpl_executadas_ok

        # log uses "skill" key not "skill_id"
        log = [
            {"skill": "01-escopo-e-eap", "status": "OK"},
            {"skill": "02-prod", "status": "ERRO"},
            {"skill": "03-cat", "status": "OK"},
        ]
        result = _rpl_executadas_ok(log)
        assert "01-escopo-e-eap" in result
        assert "02-prod" not in result
        assert "03-cat" in result

    def test_rpl_next_pending_returns_first_missing(self):
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER
        from concilium.presentation.mcp.tools.pipeline import _rpl_next_pending

        executadas = {CANONICAL_SKILL_ORDER[0]}
        pending = _rpl_next_pending(executadas)
        assert isinstance(pending, list)
        assert CANONICAL_SKILL_ORDER[0] not in pending

    def test_rpl_next_sugerida(self):
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER
        from concilium.presentation.mcp.tools.pipeline import _rpl_next_sugerida

        result = _rpl_next_sugerida(set())
        assert result == CANONICAL_SKILL_ORDER[0]

    def test_rpl_next_sugerida_none_when_all_done(self):
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER
        from concilium.presentation.mcp.tools.pipeline import _rpl_next_sugerida

        result = _rpl_next_sugerida(set(CANONICAL_SKILL_ORDER))
        assert result is None

    def test_rpl_artifacts_out_formats(self):
        from concilium.presentation.mcp.tools.pipeline import _rpl_artifacts_out

        # Artifacts are objects with .meta attributes
        mock_art = MagicMock()
        mock_art.meta.artifact_id = "art-1"
        mock_art.meta.kind.value = "json"
        mock_art.meta.schema_name = "relatorio"
        mock_art.meta.version = "v1"
        mock_art.meta.skill_id = "09-relatorio"
        result = _rpl_artifacts_out([mock_art])
        assert len(result) == 1
        assert result[0]["artifact_id"] == "art-1"

    def test_rpl_build_result_fields(self):
        from concilium.presentation.mcp.tools.pipeline import _rpl_build_result

        r = MagicMock()
        r.has_errors = False
        r.validacoes = []
        r.canonical.cronograma = MagicMock()
        r.canonical.resultado = MagicMock()
        ps = MagicMock()
        ps.read_invocations.return_value = [{"skill_id": "01-escopo-e-eap", "status": "OK"}]
        result = _rpl_build_result(r, "01-escopo-e-eap", "02-prod", ps)
        assert "skill_executada" in result
        assert result["skill_executada"] == "01-escopo-e-eap"

    def test_register_adds_tools(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.pipeline import register

        server = FastMCP("test")
        register(server)
        names = list(server._tool_manager._tools.keys())
        assert "disparar_pipeline" in names
        assert "consultar_job_pipeline" in names
        assert "listar_jobs_pipeline" in names
        assert "cancelar_job_pipeline" in names


# ─── analysis API routes ─────────────────────────────────────────────────────


class TestAnalysisRoutes:
    def _svc(self):
        return MagicMock()

    def test_compare_ok(self):
        from concilium.presentation.api.routes.analysis import compare

        svc = self._svc()
        svc.compare_versions.return_value = {"delta": 0.05}
        req = MagicMock()
        req.left_version = "v1"
        req.right_version = "v2"
        result = compare("proj-1", req, service=svc)
        assert "delta" in result

    def test_compare_not_found(self):
        from concilium.presentation.api.routes.analysis import compare

        svc = self._svc()
        svc.compare_versions.side_effect = FileNotFoundError("not found")
        req = MagicMock()
        req.left_version = "v1"
        req.right_version = "v99"
        with pytest.raises(HTTPException) as exc:
            compare("proj-1", req, service=svc)
        assert exc.value.status_code == 404

    def test_list_artifacts_ok(self):
        from concilium.presentation.api.routes.analysis import list_artifacts

        svc = self._svc()
        svc.list_artifacts.return_value = {"items": [{"nome": "relatorio.json"}]}
        result = list_artifacts("proj-1", version=None, service=svc)
        assert "items" in result

    def test_get_diagnostico_pe_ok(self):
        from concilium.presentation.api.routes.analysis import get_diagnostico_pe

        svc = self._svc()
        svc.get_diagnostico_pe.return_value = {"status": "VERDE"}
        result = get_diagnostico_pe("proj-1", service=svc)
        assert result["status"] == "VERDE"

    def test_get_diagnostico_pe_not_found(self):
        from concilium.presentation.api.routes.analysis import get_diagnostico_pe

        svc = self._svc()
        svc.get_diagnostico_pe.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_diagnostico_pe("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_get_calendario_operacional(self):
        from concilium.presentation.api.routes.analysis import get_calendario_operacional

        svc = self._svc()
        svc.get_calendario_operacional.return_value = {"weeks": []}
        result = get_calendario_operacional("proj-1", service=svc)
        assert "weeks" in result

    def test_simulate_calendario_operacional(self):
        from concilium.presentation.api.routes.analysis import simulate_calendario_operacional

        svc = self._svc()
        svc.simulate_calendario_operacional.return_value = {"simulated": True}
        req = MagicMock()
        result = simulate_calendario_operacional("proj-1", req, service=svc)
        assert result["simulated"] is True

    def test_get_cubo_analitico_ok(self):
        from concilium.presentation.api.routes.analysis import get_cubo_analitico

        svc = self._svc()
        svc.get_cubo_analitico.return_value = {"faces": []}
        result = get_cubo_analitico("proj-1", version=None, service=svc)
        assert "faces" in result

    def test_get_cubo_analitico_not_found(self):
        from concilium.presentation.api.routes.analysis import get_cubo_analitico

        svc = self._svc()
        svc.get_cubo_analitico.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_cubo_analitico("proj-1", version=None, service=svc)
        assert exc.value.status_code == 404

    def test_get_cubo_pool_projecao(self):
        from concilium.presentation.api.routes.analysis import get_cubo_pool_projecao

        svc = self._svc()
        svc.get_cubo_pool_projection.return_value = {"rows": []}
        result = get_cubo_pool_projecao("proj-1", face="instancia_ciclo_vida", version=None, service=svc)
        assert "rows" in result

    def test_get_benchmark_reference(self):
        from concilium.presentation.api.routes.analysis import get_benchmark_reference

        svc = self._svc()
        svc.get_benchmark_reference.return_value = {"slug": "AGIS"}
        result = get_benchmark_reference("proj-1", service=svc)
        assert result["slug"] == "AGIS"

    def test_get_benchmark_reference_not_found(self):
        from concilium.presentation.api.routes.analysis import get_benchmark_reference

        svc = self._svc()
        # If returns None, it should raise 404
        svc.get_benchmark_reference.side_effect = FileNotFoundError("not found")
        with pytest.raises(HTTPException) as exc:
            get_benchmark_reference("proj-1", service=svc)
        assert exc.value.status_code == 404

    def test_list_audit_ok(self):
        from concilium.presentation.api.routes.analysis import list_audit

        svc = self._svc()
        svc.list_audit.return_value = [{"action": "run"}]
        result = list_audit("proj-1", service=svc)
        assert "items" in result

    def test_compare_query_ok(self):
        from concilium.presentation.api.routes.analysis import compare_query

        svc = self._svc()
        svc.compare_versions.return_value = {"diff": []}
        result = compare_query("proj-1", left="v1", right="v2", service=svc)
        assert "diff" in result


# ─── BenchmarkRunner helpers ──────────────────────────────────────────────────


class TestBenchmarkRunner:
    def test_from_settings_constructs(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        with patch("concilium.infrastructure.settings.get_storage") as mock_gs:
            mock_storage = MagicMock()
            mock_storage.config_root = Path("/fake/config")
            mock_storage.benchmark_projects_root = None
            mock_storage.root = Path("/fake")
            mock_gs.return_value = mock_storage
            runner = BenchmarkRunner.from_settings()
        assert runner.config_root == Path("/fake/config")

    def test_get_output_subdir_images(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("chart.png") == "visualizations"
        assert BenchmarkRunner._get_output_subdir("chart.jpg") == "visualizations"

    def test_get_output_subdir_reports(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("report.pdf") == "reports"
        assert BenchmarkRunner._get_output_subdir("data.xlsx") == "reports"
        assert BenchmarkRunner._get_output_subdir("relatorio.json") == "reports"

    def test_get_output_subdir_unknown(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("file.xyz") == "reports"
