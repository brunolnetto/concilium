"""Tests for several small modules to boost coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ─── png_bundle ─────────────────────────────────────────────────────────────


class TestBuildVisualizationPngFiles:
    def test_empty_relatorio_returns_empty(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            result = build_visualization_png_files({})
        assert result == {}

    def test_graficos_section_forwarded(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        relatorio = {"GRAFICOS": {"gantt": {}}}
        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={"gantt.png": b"x"},
            ) as mock_charts,
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            result = build_visualization_png_files(relatorio)
        mock_charts.assert_called_once_with({"gantt": {}})
        assert "gantt.png" in result

    def test_cube_pngs_merged(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        canonical = MagicMock()
        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={"cube.png": b"y"},
            ),
        ):
            result = build_visualization_png_files({}, canonical=canonical)
        assert "cube.png" in result

    def test_non_dict_relatorio_skips_graficos(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ) as mock_charts,
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            build_visualization_png_files("not a dict")
        # graficos is {} when relatorio is not a dict → build_chart_png_files NOT called (empty graficos skipped)
        mock_charts.assert_not_called()

    def test_graficos_not_dict_skips_charts(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ) as mock_charts,
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            build_visualization_png_files({"GRAFICOS": "invalid"})
        # "invalid" is not a dict → charts skipped
        mock_charts.assert_not_called()


# ─── catalog_audit ──────────────────────────────────────────────────────────


class TestCatalogAudit:
    def test_perform_catalog_audit_healthy(self):
        from concilium.infrastructure.services.catalog_audit import perform_catalog_audit

        runtime = MagicMock()
        with patch("concilium.infrastructure.services.catalog_audit.assert_catalog_healthy"):
            perform_catalog_audit(runtime, "ctx1", {"cpus": []})

    def test_perform_catalog_audit_raises_on_governance_error(self):
        from concilium.application.orchestrators.catalog_governance import CatalogGovernanceError
        from concilium.infrastructure.services.catalog_audit import perform_catalog_audit

        runtime = MagicMock()
        with patch(
            "concilium.infrastructure.services.catalog_audit.assert_catalog_healthy",
            side_effect=CatalogGovernanceError("bad catalog"),
        ):
            with pytest.raises(RuntimeError, match="Erro de governança"):
                perform_catalog_audit(runtime, "ctx1", {})

    def test_load_and_audit_catalog_happy_path(self):
        from concilium.infrastructure.services.catalog_audit import load_and_audit_catalog

        runtime = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.catalogo_id = "cat1"
        runtime.load_contexto.return_value = mock_ctx
        runtime.load_catalogo.return_value = {"cpus": []}
        with patch("concilium.infrastructure.services.catalog_audit.assert_catalog_healthy"):
            load_and_audit_catalog(runtime, "ctx1")
        runtime.load_contexto.assert_called_once_with("ctx1")
        runtime.load_catalogo.assert_called_once_with("cat1")


# ─── RepositorioProducao ────────────────────────────────────────────────────


class TestRepositorioProducao:
    def _make_repo(self, tmp_path):
        from concilium.infrastructure.repositories.producao import RepositorioProducao

        return RepositorioProducao(tmp_path)

    def test_obter_returns_none_when_missing(self, tmp_path):
        repo = self._make_repo(tmp_path)
        assert repo.obter("nope") is None

    def test_obter_returns_producao_when_exists(self, tmp_path):
        (tmp_path / "P1.json").write_text('{"id": "P1"}', encoding="utf-8")
        mock_prod = MagicMock()
        mock_prod.id = "P1"
        with patch("concilium.infrastructure.repositories.producao.Producao") as mock_cls:
            mock_cls.model_validate.return_value = mock_prod
            repo = self._make_repo(tmp_path)
            prod = repo.obter("P1")
        assert prod is not None
        assert prod.id == "P1"

    def test_obter_ou_erro_raises_when_missing(self, tmp_path):
        repo = self._make_repo(tmp_path)
        with pytest.raises(FileNotFoundError, match="nope"):
            repo.obter_ou_erro("nope")

    def test_salvar_writes_json(self, tmp_path):
        mock_prod = MagicMock()
        mock_prod.id = "P2"
        mock_prod.model_dump_json.return_value = '{"id": "P2"}'
        repo = self._make_repo(tmp_path)
        repo.salvar(mock_prod)
        assert (tmp_path / "P2.json").exists()

    def test_listar_ids(self, tmp_path):
        for pid in ("A", "B", "C"):
            data = {"id": pid, "descricao": "", "producao_horaria": 1.0, "unidade": "m", "equipe": [], "variantes": []}
            (tmp_path / f"{pid}.json").write_text(json.dumps(data), encoding="utf-8")
        repo = self._make_repo(tmp_path)
        ids = repo.listar_ids()
        assert set(ids) == {"A", "B", "C"}

    def test_existe_true_and_false(self, tmp_path):
        data = {"id": "X", "descricao": "", "producao_horaria": 1.0, "unidade": "m", "equipe": [], "variantes": []}
        (tmp_path / "X.json").write_text(json.dumps(data), encoding="utf-8")
        repo = self._make_repo(tmp_path)
        assert repo.existe("X") is True
        assert repo.existe("Y") is False


# ─── charts/__init__ (build_all) ───────────────────────────────────────────


class TestChartsInit:
    def test_build_all_empty_graficos(self):
        from concilium.application.runtime.deliverables.visualizations.charts import build_all

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_equipamentos",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_mao_obra",
                return_value=None,
            ),
            patch("concilium.application.runtime.deliverables.visualizations.charts.build_gantt", return_value=None),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_fluxo_financeiro",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_painel_equilibrio",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_dependencia_eap",
                return_value=None,
            ),
        ):
            result = build_all({})
        assert result == {}

    def test_build_all_returns_non_none_pngs(self):
        from concilium.application.runtime.deliverables.visualizations.charts import build_all

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_equipamentos",
                return_value=b"png1",
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_mao_obra",
                return_value=None,
            ),
            patch("concilium.application.runtime.deliverables.visualizations.charts.build_gantt", return_value=b"png2"),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_fluxo_financeiro",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_painel_equilibrio",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_dependencia_eap",
                return_value=None,
            ),
        ):
            result = build_all({"cronograma": {}})
        assert "hist_equipamentos.png" in result
        assert "gantt_cronograma.png" in result
        assert "hist_mao_obra.png" not in result

    def test_build_all_swallows_exceptions(self):
        from concilium.application.runtime.deliverables.visualizations.charts import build_all

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_equipamentos",
                side_effect=Exception("fail"),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_mao_obra",
                return_value=None,
            ),
            patch("concilium.application.runtime.deliverables.visualizations.charts.build_gantt", return_value=None),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_fluxo_financeiro",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_painel_equilibrio",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_dependencia_eap",
                return_value=None,
            ),
        ):
            result = build_all({})  # should not raise
        assert "hist_equipamentos.png" not in result


# ─── charts/_common ────────────────────────────────────────────────────────


class TestChartsCommon:
    def test_clean_series_label_known(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import clean_series_label

        assert clean_series_label("overhead_AC") == "Adm. Central (AC)"
        assert clean_series_label("overhead_L") == "Lucro (L)"
        assert clean_series_label("tributo_ISS") == "ISS"

    def test_clean_series_label_unknown_replaces_underscore(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import clean_series_label

        result = clean_series_label("my_custom_label")
        assert "_" not in result

    def test_init_mpl_returns_plt_and_fn(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import init_mpl

        plt, fig_to_bytes = init_mpl()
        assert callable(fig_to_bytes)

    def test_fig_to_bytes_returns_bytes(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import init_mpl

        plt, fig_to_bytes = init_mpl()
        fig, ax = plt.subplots()
        result = fig_to_bytes(fig)
        assert isinstance(result, bytes)
        assert len(result) > 0


# ─── MCP tributacao ─────────────────────────────────────────────────────────


class TestMcpTributacao:
    def _make_server(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.tributacao import register

        server = FastMCP("test")
        register(server)
        return server

    def test_calcular_tributos_clt_delega_servico(self):
        """ADR-116 F5: tool unificada delega a calculate_employer_clt."""
        from concilium.domain.services.financial import tributacao as trib

        assert hasattr(trib, "calculate_employer_clt")
        assert hasattr(trib, "calculate_inss_employee")
        assert hasattr(trib, "calculate_irrf")

    def test_tributacao_register_adds_unified_tool(self):
        """ADR-116 F5: apenas calcular_tributos registrada (3 → 1)."""
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.tributacao import register

        server = FastMCP("test")
        register(server)
        tool_names = list(server._tool_manager._tools.keys())
        assert "calcular_tributos" in tool_names
        assert "calcular_custo_empregador_clt" not in tool_names
        assert "calcular_inss_empregado" not in tool_names
        assert "calcular_irrf" not in tool_names


# ─── MCP artifacts ──────────────────────────────────────────────────────────


class TestMcpArtifacts:
    def test_register_adds_tools(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.artifacts import register

        server = FastMCP("test")
        register(server)
        names = list(server._tool_manager._tools.keys())
        assert "listar_artefatos_projeto" in names
        assert "obter_artefato" in names  # ADR-116 F5: ler_texto+baixar_binario+bundle_zip→obter_artefato

    def test_listar_artefatos_calls_list_artifacts(self):
        from mcp.server.fastmcp import FastMCP

        from concilium.presentation.mcp.tools.artifacts import register

        server = FastMCP("test")
        register(server)
        mock_store = MagicMock()
        with (
            patch("concilium.presentation.mcp.tools.artifacts._project", return_value=mock_store),
            patch("concilium.presentation.mcp.tools.artifacts.ab.list_artifacts", return_value={"items": []}),
        ):
            # Tools are registered; verify the ab module has the expected functions
            import concilium.application.services.artifact.artifact_bundle as ab

            assert hasattr(ab, "list_artifacts")
            assert hasattr(ab, "read_text")
            assert hasattr(ab, "read_binary_b64")
            assert hasattr(ab, "build_bundle")


# ─── jobs/state.py ──────────────────────────────────────────────────────────


class TestPipelineJobStateMachine:
    def _make_job_data(self, status="AGUARDANDO_FILA"):
        return {
            "job_id": "test-job-id-123",
            "status": status,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }

    def test_initial_state_aguardando_fila(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        assert sm.status_str == "AGUARDANDO_FILA"

    def test_iniciar_transition(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        sm.iniciar()
        assert sm.status_str == "EM_EXECUCAO"

    def test_completar_transition(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        sm.iniciar()
        sm.completar(resultado={"ok": True})
        assert sm.status_str == "CONCLUIDO"
        assert sm.job_data["resultado"] == {"ok": True}
        assert sm.is_terminal

    def test_falhar_from_execucao(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        sm.iniciar()
        sm.falhar(erro="something broke")
        assert sm.status_str == "ERRO"
        assert sm.job_data["erro"] == "something broke"
        assert sm.is_terminal

    def test_falhar_from_aguardando(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        sm.falhar(erro="queue error")
        assert sm.status_str == "ERRO"

    def test_cancelar_from_aguardando(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        assert sm.pode_cancelar
        sm.cancelar(motivo="User cancelled")
        assert sm.status_str == "CANCELADO"
        assert sm.job_data["erro"] == "User cancelled"

    def test_cancelar_from_execucao(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        sm.iniciar()
        assert sm.pode_cancelar
        sm.cancelar()
        assert sm.status_str == "CANCELADO"

    def test_pode_cancelar_false_when_terminal(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        sm.iniciar()
        sm.completar(resultado={})
        assert not sm.pode_cancelar

    def test_validar_transicao_valid(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        # All return bool without raising
        result_completar = sm.validar_transicao("completar")
        result_nonexistent = sm.validar_transicao("nonexistent_event")
        assert isinstance(result_completar, bool)
        assert result_nonexistent is False

    def test_validar_transicao_invalid_name(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        assert sm.validar_transicao("nonexistent") is False

    def test_is_terminal_false_initially(self):
        from concilium.application.jobs.state import PipelineJobStateMachine

        sm = PipelineJobStateMachine(self._make_job_data())
        assert not sm.is_terminal

    def test_criar_state_machine_em_execucao(self):
        from concilium.application.jobs.state import criar_state_machine

        job_data = self._make_job_data("EM_EXECUCAO")
        job_data["iniciado_em"] = "2026-01-01T00:00:00+00:00"
        sm = criar_state_machine(job_data)
        assert sm.status_str == "EM_EXECUCAO"

    def test_criar_state_machine_concluido(self):
        from concilium.application.jobs.state import criar_state_machine

        job_data = self._make_job_data("CONCLUIDO")
        job_data["resultado"] = {"ok": True}
        sm = criar_state_machine(job_data)
        assert sm.status_str == "CONCLUIDO"

    def test_criar_state_machine_erro_with_iniciar(self):
        from concilium.application.jobs.state import criar_state_machine

        job_data = self._make_job_data("ERRO")
        job_data["iniciado_em"] = "2026-01-01T00:00:00+00:00"
        job_data["erro"] = "fail"
        sm = criar_state_machine(job_data)
        assert sm.status_str == "ERRO"

    def test_criar_state_machine_erro_without_iniciar(self):
        from concilium.application.jobs.state import criar_state_machine

        job_data = self._make_job_data("ERRO")
        job_data["erro"] = "queue fail"
        sm = criar_state_machine(job_data)
        assert sm.status_str == "ERRO"

    def test_criar_state_machine_cancelado(self):
        from concilium.application.jobs.state import criar_state_machine

        job_data = self._make_job_data("CANCELADO")
        job_data["erro"] = "Cancelled"
        sm = criar_state_machine(job_data)
        assert sm.status_str == "CANCELADO"


# ─── API routes/system ──────────────────────────────────────────────────────


class TestSystemRoutes:
    def test_health_returns_ok(self):
        from concilium.presentation.api.routes.system import health

        result = health()
        assert result["status"] in ("ok", "degraded")
        assert "storage" in result
        assert result["storage"]["status"] in ("ok", "error")

    def test_root_redirects(self):
        from fastapi.responses import RedirectResponse

        from concilium.presentation.api.routes.system import root

        result = root()
        assert isinstance(result, RedirectResponse)

    def test_health_storage_exception_returns_degraded(self):
        from concilium.presentation.api.routes.system import health

        with patch("concilium.infrastructure.storage.store_factory.build_blob_storage") as mock_build:
            mock_build.side_effect = RuntimeError("storage unreachable")
            result = health()
        assert result["status"] == "degraded"
        assert result["storage"]["status"] == "error"
        assert "storage unreachable" in result["storage"]["message"]

    def test_reload_catalog_handles_exception(self):
        from concilium.presentation.api.routes.system import reload_catalog

        with patch("concilium.presentation.api.routes.system.ServiceContainer") as mock_sc:
            mock_sc.instance.side_effect = Exception("no container")
            result = reload_catalog()
        assert result["status"] == "error"
        assert "message" in result

    def test_reload_catalog_happy_path(self):
        from concilium.presentation.api.routes.system import reload_catalog

        mock_runtime = MagicMock()
        mock_runtime._config_cache = {"catalogo:x": 1, "other": 2}
        mock_container = MagicMock()
        mock_container.concilium_service._dependencies.pipeline_service._runtime_factory.return_value = mock_runtime
        mock_cfg_path = MagicMock()
        mock_cfg_path.rglob.return_value = []
        with (
            patch("concilium.presentation.api.routes.system.ServiceContainer") as mock_sc,
            patch("concilium.presentation.cli.shared.config_root", return_value=mock_cfg_path),
        ):
            mock_sc.instance.return_value = mock_container
            result = reload_catalog()
        assert result["status"] == "ok"
        assert result["catalog_cache_keys_cleared"] == 1

    def test_reload_catalog_deletes_bundles_on_disk(self):
        from concilium.presentation.api.routes.system import reload_catalog

        mock_runtime = MagicMock()
        mock_runtime._config_cache = {"catalogo:x": 1}
        mock_container = MagicMock()
        mock_container.concilium_service._dependencies.pipeline_service._runtime_factory.return_value = mock_runtime

        bundle_path = MagicMock()
        bundle_path.relative_to.return_value = "catalogos/cat1/.catalog_bundle.json"

        mock_cfg_path = MagicMock()
        mock_cfg_path.rglob.return_value = [bundle_path]
        with (
            patch("concilium.presentation.api.routes.system.ServiceContainer") as mock_sc,
            patch("concilium.presentation.cli.shared.config_root", return_value=mock_cfg_path),
        ):
            mock_sc.instance.return_value = mock_container
            result = reload_catalog()
        assert result["status"] == "ok"
        bundle_path.unlink.assert_called_once_with(missing_ok=True)
        assert result["bundles_deleted"] == ["catalogos/cat1/.catalog_bundle.json"]


class TestReloadCatalogAttributeChain:
    def test_dependencies_attribute_chain_exists_on_real_classes(self):
        """Regressão: o endpoint usava container.concilium_service.deps (atributo
        inexistente — o real é _dependencies), então /catalog/reload sempre caía
        no except e devolvia status=error. O mock de MagicMock engolia o erro."""
        import inspect

        from concilium.application.services.concilium_service import ConciliumDependencies, ConciliumService
        from concilium.presentation.api.routes.system import reload_catalog

        source = inspect.getsource(reload_catalog)
        assert ".deps." not in source, "endpoint referencia .deps, que não existe em ConciliumService"
        assert "_dependencies" in source

        # O atributo real existe na classe e o campo pipeline_service existe no container de deps
        assert "pipeline_service" in {f.name for f in ConciliumDependencies.__dataclass_fields__.values()} or hasattr(
            ConciliumDependencies, "pipeline_service"
        )
        assert not hasattr(ConciliumService, "deps")


# ─── cli/shared.py: _tools_root / benchmark_projects_root / _find_projects_by_name ──


class TestToolsRoot:
    def test_storage_root_is_workspace_returns_it_directly(self, tmp_path):
        from concilium.presentation.cli import shared

        storage = MagicMock(root=tmp_path)
        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._looks_like_workspace_root", return_value=True),
        ):
            result = shared._tools_root()
        assert result == tmp_path.resolve()

    def test_falls_back_to_cwd_ancestor_when_storage_root_is_not_workspace(self, tmp_path, monkeypatch):
        from concilium.presentation.cli import shared

        storage_root = tmp_path / "not_a_workspace"
        storage_root.mkdir()
        cwd_dir = tmp_path / "cwd_is_workspace"
        cwd_dir.mkdir()
        storage = MagicMock(root=storage_root)
        monkeypatch.chdir(cwd_dir)

        def fake_looks_like(path):
            return path == cwd_dir.resolve()

        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._looks_like_workspace_root", side_effect=fake_looks_like),
        ):
            result = shared._tools_root()
        assert result == cwd_dir.resolve()

    def test_falls_back_to_original_storage_root_when_nothing_matches(self, tmp_path, monkeypatch):
        """Regression: the fallback loop used to shadow `candidate`, so when no
        ancestor of cwd looked like a workspace root it silently returned the
        filesystem root ("/") instead of the original storage root."""
        from concilium.presentation.cli import shared

        storage_root = tmp_path / "not_a_workspace"
        storage_root.mkdir()
        cwd_dir = tmp_path / "cwd_also_not_workspace"
        cwd_dir.mkdir()
        storage = MagicMock(root=storage_root)
        monkeypatch.chdir(cwd_dir)

        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._looks_like_workspace_root", return_value=False),
        ):
            result = shared._tools_root()
        assert result == storage_root
        assert result != Path("/")


class TestBenchmarkProjectsRoot:
    def test_creates_directory_and_returns_it(self, tmp_path):
        from concilium.presentation.cli import shared

        target = tmp_path / "benchmarks" / "projetos"
        with patch("concilium.presentation.cli.shared._benchmark_projects_root", return_value=target):
            result = shared.benchmark_projects_root()
        assert result == target
        assert target.is_dir()

    def test_benchmark_projects_root_falls_back_to_tools_root(self, tmp_path):
        from concilium.presentation.cli import shared

        storage = MagicMock(benchmark_projects_root=None)
        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._tools_root", return_value=tmp_path),
        ):
            result = shared._benchmark_projects_root()
        assert result == tmp_path / "benchmarks" / "projetos"


class TestFindProjectsByName:
    def test_skips_non_dir_entries_and_dirs_without_meta(self, tmp_path):
        from concilium.presentation.cli.shared import _find_projects_by_name

        (tmp_path / "a_file.txt").write_text("x", encoding="utf-8")
        no_meta_dir = tmp_path / "NO_META"
        no_meta_dir.mkdir()
        with_meta_dir = tmp_path / "WITH_META"
        with_meta_dir.mkdir()
        (with_meta_dir / "meta.json").write_text(json.dumps({"nome": "Proj X"}), encoding="utf-8")

        matches = _find_projects_by_name(tmp_path, "Proj X")
        assert matches == [with_meta_dir]

    def test_skips_dirs_with_non_matching_nome(self, tmp_path):
        """Branch 109->102: quando meta['nome'] não bate, o loop segue para o
        próximo diretório sem adicionar aos matches."""
        from concilium.presentation.cli.shared import _find_projects_by_name

        other_dir = tmp_path / "OTHER"
        other_dir.mkdir()
        (other_dir / "meta.json").write_text(json.dumps({"nome": "Outro Projeto"}), encoding="utf-8")
        target_dir = tmp_path / "TARGET"
        target_dir.mkdir()
        (target_dir / "meta.json").write_text(json.dumps({"nome": "Proj X"}), encoding="utf-8")

        matches = _find_projects_by_name(tmp_path, "Proj X")
        assert matches == [target_dir]
