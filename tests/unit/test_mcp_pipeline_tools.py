"""Tests for MCP pipeline tools (disparar, consultar, listar, cancelar, estatísticas)."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP

_PIPELINE_MOD = "concilium.presentation.mcp.tools.pipeline"


def _register_tools(monkeypatch, tmp_path: Path) -> dict:
    import importlib

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))

    mod = importlib.import_module(_PIPELINE_MOD)
    server = FastMCP("test-pipeline")
    with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):
        mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def _make_job_dto(job_id="job-1", status="CONCLUIDO"):
    from concilium.application.jobs.service import JobDTO

    dto = MagicMock(spec=JobDTO)
    dto.job_id = job_id
    dto.status = status
    dto.erro = None
    dto.model_dump.return_value = {"job_id": job_id, "status": status}
    return dto


class TestDispararPipeline:
    def test_disparar_happy(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        svc_mock.disparar_pipeline.return_value = _make_job_dto()

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            result = tools["disparar_pipeline"](project_id="proj-1")
        assert "job_id" in result or "status" in result


class TestConsultarJobPipeline:
    def test_consultar_happy(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        svc_mock.consultar_job.return_value = _make_job_dto()

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            result = tools["consultar_job_pipeline"](job_id="job-1")
        assert "job_id" in result or "status" in result

    def test_consultar_not_found(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        svc_mock.consultar_job.side_effect = ValueError("not found")

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            result = tools["consultar_job_pipeline"](job_id="bad")
        assert "error" in result


class TestListarJobsPipeline:
    def test_listar_all(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        list_dto = MagicMock()
        list_dto.model_dump.return_value = {"jobs": [], "total": 0}
        svc_mock.listar_jobs.return_value = list_dto

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            result = tools["listar_jobs_pipeline"]()
        assert "jobs" in result or "total" in result

    def test_listar_filtered(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        list_dto = MagicMock()
        list_dto.model_dump.return_value = {"jobs": [{"job_id": "j1"}], "total": 1}
        svc_mock.listar_jobs.return_value = list_dto

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            tools["listar_jobs_pipeline"](project_id="proj-1")
        svc_mock.listar_jobs.assert_called_once_with("proj-1")


class TestObterEstatisticasJobs:
    """ADR-116 F5: obter_estatisticas_jobs absorvida em listar_jobs_pipeline(incluir_estatisticas=True)."""

    def test_estatisticas_happy(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        job_list_dto = MagicMock()
        stats_dto = MagicMock()
        job_list_dto.model_dump.return_value = {"jobs": []}
        stats_dto.model_dump.return_value = {"max_concurrent_jobs": 4, "health": "OK"}
        svc_mock.listar_jobs.return_value = job_list_dto
        svc_mock.obter_estatisticas.return_value = stats_dto

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            result = tools["listar_jobs_pipeline"](incluir_estatisticas=True)
        assert "estatisticas" in result or "max_concurrent_jobs" in str(result)


class TestCancelarJobPipeline:
    def test_cancelar_happy(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        dto = _make_job_dto(status="CANCELADO")
        svc_mock.cancelar_job.return_value = dto

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            result = tools["cancelar_job_pipeline"](job_id="job-1", motivo="teste")
        assert result.get("status") == "CANCELADO" or "job_id" in result

    def test_cancelar_not_found(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        svc_mock = MagicMock()
        svc_mock.cancelar_job.side_effect = ValueError("cannot cancel")

        with patch("concilium.application.jobs.get_job_service", return_value=svc_mock):
            result = tools["cancelar_job_pipeline"](job_id="bad")
        assert "erro" in result


class TestPipelineHelpers:
    def test_rpl_executadas_ok(self):
        from concilium.presentation.mcp.tools.pipeline import _rpl_executadas_ok

        log = [
            {"skill": "01-escopo-e-eap", "status": "OK"},
            {"skill": "02-prod", "status": "ERRO"},
        ]
        result = _rpl_executadas_ok(log)
        assert "01-escopo-e-eap" in result
        assert "02-prod" not in result

    def test_rpl_next_pending(self):
        from concilium.presentation.mcp.tools.pipeline import _rpl_next_pending

        executadas = {"01-escopo-e-eap"}
        result = _rpl_next_pending(executadas)
        assert "01-escopo-e-eap" not in result
        assert len(result) > 0

    def test_rpl_next_sugerida_has_next(self):
        from concilium.presentation.mcp.tools.pipeline import _rpl_next_sugerida

        result = _rpl_next_sugerida(set())
        assert result is not None

    def test_rpl_next_sugerida_all_done(self):
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER
        from concilium.presentation.mcp.tools.pipeline import _rpl_next_sugerida

        result = _rpl_next_sugerida(set(CANONICAL_SKILL_ORDER))
        assert result is None

    def test_rpl_artifacts_out(self):
        from datetime import datetime

        from concilium.presentation.mcp.tools.pipeline import _rpl_artifacts_out

        art = MagicMock()
        art.meta.artifact_id = "art-1"
        art.meta.kind.value = "report"
        art.meta.schema_name = "relatorio"
        art.meta.schema_version = "1.0"
        art.meta.created_at = datetime.now(UTC)
        art.meta.content_hash = "abc"
        result = _rpl_artifacts_out([art])
        assert len(result) == 1
        assert result[0]["artifact_id"] == "art-1"

    def test_run_pipeline_on_plano_no_pending(self):
        """Cover lines 254-257: pipeline completo → info message."""
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER
        from concilium.presentation.mcp.tools.pipeline import _run_pipeline_on_plano

        # All skills already executed
        set(CANONICAL_SKILL_ORDER)
        ps = MagicMock()
        ps.read_invocations.return_value = [{"skill": sid, "status": "OK"} for sid in CANONICAL_SKILL_ORDER]
        ps.plano_id = "plano-1"
        result = _run_pipeline_on_plano(MagicMock(), MagicMock(), ps, None, {})
        assert "info" in result

    def test_run_pipeline_on_plano_precondition_error(self):
        """Cover lines 265-266: ConciliumRuntimeError → ERRO_PRECONDICAO."""
        from concilium.presentation.mcp._context import ConciliumRuntimeError
        from concilium.presentation.mcp.tools.pipeline import _run_pipeline_on_plano

        ps = MagicMock()
        ps.read_invocations.return_value = []
        ps.plano_id = "plano-1"
        coord = MagicMock()
        coord.avancar_plano.side_effect = ConciliumRuntimeError("precond")
        with patch("concilium.presentation.mcp.tools.pipeline._lifecycle_coordinator", return_value=coord):
            with patch("concilium.presentation.mcp.tools.pipeline._get_or_create_trace_id"):
                result = _run_pipeline_on_plano(MagicMock(), MagicMock(), ps, "01-escopo-e-eap", {})
        assert result.get("status") == "ERRO_PRECONDICAO"

    def test_run_pipeline_on_plano_generic_exception(self):
        """Cover lines 267-268: generic Exception → ERRO_EXCECAO."""
        from concilium.presentation.mcp.tools.pipeline import _run_pipeline_on_plano

        ps = MagicMock()
        ps.read_invocations.return_value = []
        ps.plano_id = "plano-1"
        coord = MagicMock()
        coord.avancar_plano.side_effect = RuntimeError("unexpected")
        with patch("concilium.presentation.mcp.tools.pipeline._lifecycle_coordinator", return_value=coord):
            with patch("concilium.presentation.mcp.tools.pipeline._get_or_create_trace_id"):
                result = _run_pipeline_on_plano(MagicMock(), MagicMock(), ps, "01-escopo-e-eap", {})
        assert result.get("status") == "ERRO_EXCECAO"

    def test_rpl_build_result(self):
        from concilium.presentation.mcp.tools.pipeline import _rpl_build_result

        r = MagicMock()
        r.has_errors = False
        r.validacoes = []
        r.artifacts = []
        ps = MagicMock()
        ps.plano_id = "plano-1"
        result = _rpl_build_result(r, "04-cronograma", "05-financeiro", ps)
        assert result["skill_executada"] == "04-cronograma"
        assert result["status"] == "OK"
        assert result["proxima_sugerida"] == "05-financeiro"
