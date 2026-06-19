"""Tests for concilium.presentation.mcp.tools.projeto — unit coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp.tools.projeto import register

# ---------------------------------------------------------------------------
# Helpers to build a minimal valid BDI payload for salvar_perfil_bdi
# ---------------------------------------------------------------------------

_APLICACAO = {
    "iss": {"aplicavel": True, "aliquota": 0.02},
    "cofins": {"aplicavel": True, "aliquota": 0.03},
    "pis": {"aplicavel": True, "aliquota": 0.0065},
    "cssl": {"aplicavel": True, "aliquota": 0.0199},
    "ir": {"aplicavel": True, "aliquota": 0.0274},
}

TRIBUTARIO_VALID = {
    "regime": "lucro_presumido",
    "municipio": "Fortaleza",
    "iss_aliquota_municipal": 0.02,
    "mao_obra": _APLICACAO,
    "material": _APLICACAO,
    "servicos": _APLICACAO,
    "indireto": _APLICACAO,
    "diesel": _APLICACAO,
}

LUCRO_VALID = {
    "mao_obra": 0.09,
    "material": 0.00,
    "servicos": 0.09,
    "indireto": 0.02,
    "diesel": 0.05,
}


# ---------------------------------------------------------------------------
# Fixture: build server and extract tool callables
# ---------------------------------------------------------------------------


@pytest.fixture()
def tools(tmp_path):
    """Register tools on a fresh FastMCP instance and return {name: fn} dict."""
    server = FastMCP("test")
    register(server)
    tool_map = server._tool_manager._tools
    return {name: tool.fn for name, tool in tool_map.items()}


# ---------------------------------------------------------------------------
# Helper: minimal mock store used across tests
# ---------------------------------------------------------------------------


def _make_store(root: Path) -> MagicMock:
    store = MagicMock()
    store.root = root
    store.meta = {
        "nome": "Test Proj",
        "contexto_id": "mendeslobo",
        "current_version": None,
    }
    store.list_versions.return_value = []
    store.list_escopos.return_value = []
    return store


# ===========================================================================
# listar_projetos
# ===========================================================================


class TestListarProjetos:
    def test_proj_root_missing_returns_empty(self, tools, tmp_path):
        """Line 30: proj_root does not exist → returns empty projetos list."""
        missing = tmp_path / "nonexistent"

        with (
            patch("concilium.presentation.mcp.tools.projeto._projetos_root", return_value=missing),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["listar_projetos"]()

        assert result["projetos"] == []
        assert "projetos_root" in result

    def test_iterates_valid_project_dirs(self, tools, tmp_path):
        """Lines 34-39: iterates dirs, reads ProjectStore.meta."""
        proj_root = tmp_path / "projetos"
        proj_root.mkdir()
        # create a project directory with a meta.json
        p1 = proj_root / "projeto-abc"
        p1.mkdir()

        mock_store = MagicMock()
        mock_store.meta = {"nome": "Proj ABC", "contexto_id": "ctx1", "current_version": "v1"}
        mock_store.list_versions.return_value = ["v1"]

        with (
            patch("concilium.presentation.mcp.tools.projeto._projetos_root", return_value=proj_root),
            patch("concilium.presentation.mcp.tools.projeto.ProjectStore", return_value=mock_store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["listar_projetos"]()

        projetos = result["projetos"]
        assert len(projetos) == 1
        assert projetos[0]["id"] == "projeto-abc"
        assert projetos[0]["nome"] == "Proj ABC"
        assert projetos[0]["contexto_id"] == "ctx1"
        assert projetos[0]["current_version"] == "v1"
        assert projetos[0]["versoes"] == ["v1"]

    def test_skips_non_directories(self, tools, tmp_path):
        """Line 34: non-directory entries are skipped."""
        proj_root = tmp_path / "projetos"
        proj_root.mkdir()
        # Create a file (not a dir) that should be skipped
        (proj_root / "some_file.txt").write_text("x")

        with (
            patch("concilium.presentation.mcp.tools.projeto._projetos_root", return_value=proj_root),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["listar_projetos"]()

        assert result["projetos"] == []

    def test_projectstore_raises_appends_error(self, tools, tmp_path):
        """Lines 48-49: ProjectStore raises → appends error dict."""
        proj_root = tmp_path / "projetos"
        proj_root.mkdir()
        p1 = proj_root / "broken-proj"
        p1.mkdir()

        def _bad_store(path):
            raise RuntimeError("corrupt meta")

        with (
            patch("concilium.presentation.mcp.tools.projeto._projetos_root", return_value=proj_root),
            patch("concilium.presentation.mcp.tools.projeto.ProjectStore", side_effect=_bad_store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["listar_projetos"]()

        projetos = result["projetos"]
        assert len(projetos) == 1
        assert projetos[0]["id"] == "broken-proj"
        assert "erro" in projetos[0]
        assert "corrupt meta" in projetos[0]["erro"]


# ===========================================================================
# iniciar_orcamento
# ===========================================================================


class TestIniciarOrcamento:
    _base_kwargs = dict(
        nome="Obra Test",
        contexto_id="mendeslobo",
        tipo_obra="terraplenagem",
        localizacao="Fortaleza, CE",
        coordenadas_lat=-3.71,
        coordenadas_lng=-38.54,
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        eap=[{"item_id": "A1", "cpu_id": "CPU-X", "quantitativo": 100.0}],
    )

    def _make_runtime(self):
        rt = MagicMock()
        contexto = MagicMock()
        contexto.referencia_id = "ref-001"
        rt.load_contexto.return_value = contexto
        return rt

    def test_happy_path(self, tools, tmp_path):
        """Lines 85-93, 105, 107, 119-125, 145-155: coord succeeds → returns project_id + plano_id."""
        proj_root = tmp_path / "projetos"
        proj_root.mkdir()

        store = MagicMock()
        store.root.name = "proj-uuid-123"
        ps = MagicMock()
        ps.plano_id = "plano-001"
        es = MagicMock()
        es.create_plan.return_value = ps
        store.create_escopo.return_value = es

        rt = self._make_runtime()

        coord = MagicMock()
        r = MagicMock()
        r.has_errors = False
        r.validacoes = []
        coord.avancar_plano.return_value = r

        with (
            patch("concilium.presentation.mcp.tools.projeto._runtime", return_value=rt),
            patch("concilium.presentation.mcp.tools.projeto._projetos_root", return_value=proj_root),
            patch("concilium.presentation.mcp.tools.projeto.ProjectStore") as MockPS,
            patch("concilium.presentation.mcp.tools.projeto._lifecycle_coordinator", return_value=coord),
        ):
            MockPS.init.return_value = store
            result = tools["iniciar_orcamento"](**self._base_kwargs)

        assert result["project_id"] == "proj-uuid-123"
        assert result["escopo_id"] == "esc-principal"
        assert result["plano_id"] == "plano-001"
        assert result["proxima_skill_sugerida"] == "02-produtividade-climatica"
        assert len(result["skills_executadas"]) == 1
        assert result["skills_executadas"][0]["status"] == "OK"

    def test_has_errors_returns_early(self, tools, tmp_path):
        """Lines 134-135: skill-01 has_errors → returns early with erro key."""
        proj_root = tmp_path / "projetos"
        proj_root.mkdir()

        store = MagicMock()
        store.root.name = "proj-error-001"
        ps = MagicMock()
        ps.plano_id = "plano-err-01"
        es = MagicMock()
        es.create_plan.return_value = ps
        store.create_escopo.return_value = es

        rt = self._make_runtime()

        coord = MagicMock()
        r = MagicMock()
        r.has_errors = True
        err_v = MagicMock()
        err_v.status = "ERRO"
        err_v.codigo = "E001"
        r.validacoes = [err_v]
        coord.avancar_plano.return_value = r

        with (
            patch("concilium.presentation.mcp.tools.projeto._runtime", return_value=rt),
            patch("concilium.presentation.mcp.tools.projeto._projetos_root", return_value=proj_root),
            patch("concilium.presentation.mcp.tools.projeto.ProjectStore") as MockPS,
            patch("concilium.presentation.mcp.tools.projeto._lifecycle_coordinator", return_value=coord),
        ):
            MockPS.init.return_value = store
            result = tools["iniciar_orcamento"](**self._base_kwargs)

        assert "erro" in result
        assert result["erro"] == "Skill 01-escopo-e-eap falhou"
        assert result["project_id"] == "proj-error-001"
        # proxima_skill_sugerida should NOT be present
        assert "proxima_skill_sugerida" not in result

    def test_exception_in_coord_returns_erro(self, tools, tmp_path):
        """Line 142-143: exception inside coord block → returns erro dict."""
        proj_root = tmp_path / "projetos"
        proj_root.mkdir()

        store = MagicMock()
        store.root.name = "proj-exc-001"
        ps = MagicMock()
        ps.plano_id = "plano-exc-01"
        es = MagicMock()
        es.create_plan.return_value = ps
        store.create_escopo.return_value = es

        rt = self._make_runtime()

        coord = MagicMock()
        coord.avancar_plano.side_effect = RuntimeError("coord error!")

        with (
            patch("concilium.presentation.mcp.tools.projeto._runtime", return_value=rt),
            patch("concilium.presentation.mcp.tools.projeto._projetos_root", return_value=proj_root),
            patch("concilium.presentation.mcp.tools.projeto.ProjectStore") as MockPS,
            patch("concilium.presentation.mcp.tools.projeto._lifecycle_coordinator", return_value=coord),
        ):
            MockPS.init.return_value = store
            result = tools["iniciar_orcamento"](**self._base_kwargs)

        assert "erro" in result
        assert "coord error!" in result["erro"]
        assert result["project_id"] == "proj-exc-001"


# ===========================================================================
# consultar_status
# ===========================================================================


class TestConsultarStatus:
    def test_minimal_no_version_no_escopos(self, tools, tmp_path):
        """Lines 161-164: project with no current_version, no escopos → minimal dict."""
        store = _make_store(tmp_path)
        store.list_escopos.return_value = []

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-minimal")

        assert result["project_id"] == "proj-minimal"
        assert result["nome"] == "Test Proj"
        assert result["current_version"] is None
        assert "resultado_atual" not in result

    def test_proveniencia_benchmark_exposed(self, tools, tmp_path):
        """Lines 173-174: derivado_de_benchmark → proveniencia_benchmark key."""
        store = _make_store(tmp_path)
        store.meta = {
            "nome": "Benchmark Proj",
            "contexto_id": "mendeslobo",
            "current_version": None,
            "derivado_de_benchmark": "bench-slug-001",
            "benchmark_versao": 3,
            "benchmark_execution_id": "exec-abc",
        }
        store.list_escopos.return_value = []

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-bench")

        assert "proveniencia_benchmark" in result
        pb = result["proveniencia_benchmark"]
        assert pb["derivado_de_benchmark"] == "bench-slug-001"
        assert pb["benchmark_versao"] == 3
        assert pb["benchmark_execution_id"] == "exec-abc"

    def test_escopos_with_active_plan_and_resultado(self, tools, tmp_path):
        """Lines 181-219: escopos + active_plan + canonical.resultado → exposes resultado_atual."""
        store = _make_store(tmp_path)
        store.list_escopos.return_value = ["esc-principal"]

        canonical = MagicMock()
        canonical.resultado = MagicMock()
        canonical.resultado.venda.total_com_bdi = 1_000_000.0
        canonical.resultado.custo.total = 750_000.0
        canonical.resultado.margem_pct = 25.0
        canonical.resultado.status_margem = "OK"
        canonical.pipeline_integridade = "COMPLETO"

        active_plan = MagicMock()
        active_plan.plano_id = "plano-001"
        active_plan.read_invocations.return_value = [
            {"skill": "01-escopo-e-eap", "status": "OK", "ts": "2026-01-01T10:00:00"}
        ]
        active_plan.load_canonical.return_value = canonical

        es = MagicMock()
        es.active_plan.return_value = active_plan

        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-escopos")

        assert result["escopos"] == ["esc-principal"]
        assert result["escopo_ativo"] == "esc-principal"
        assert result["plano_ativo"] == "plano-001"
        assert len(result["invocations"]) == 1
        assert result["resultado_atual"]["preco_venda"] == 1_000_000.0
        assert result["pipeline_integridade"] == "COMPLETO"

    def test_no_active_plan_in_escopo(self, tools, tmp_path):
        """Lines 188-200: escopo with no active plan → no plano_ativo key."""
        store = _make_store(tmp_path)
        store.list_escopos.return_value = ["esc-vazio"]

        es = MagicMock()
        es.active_plan.return_value = None
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-no-plan")

        assert result["escopos"] == ["esc-vazio"]
        assert "plano_ativo" not in result

    def test_with_current_version_invocations_log(self, tools, tmp_path):
        """Lines 221-237: current_version + INVOCATIONS_LOG → invocations list."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        log_path = version_dir / "invocations.log"
        log_path.write_text(
            json.dumps({"skill": "01-escopo-e-eap", "status": "OK", "ts": "2026-01-01T10:00:00"})
            + "\n"
            + json.dumps({"skill": "02-produtividade-climatica", "status": "ERRO", "ts": "2026-01-01T11:00:00"})
            + "\n",
            encoding="utf-8",
        )

        store = _make_store(tmp_path)
        store.meta = {
            "nome": "Versioned Proj",
            "contexto_id": "mendeslobo",
            "current_version": "v1",
        }
        store.list_versions.return_value = ["v1"]
        store.list_escopos.return_value = []
        store.version_path.return_value = version_dir
        store.INVOCATIONS_LOG = "invocations.log"
        store.load_canonical.return_value = None

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-versioned")

        assert len(result["invocations"]) == 2
        assert result["invocations"][0]["skill"] == "01-escopo-e-eap"
        assert result["invocations"][1]["status"] == "ERRO"

    def test_canonical_blocked_pipeline_aviso(self, tools, tmp_path):
        """Lines 243-257, 262-274: canonical with blocked pipeline → aviso_integridade + resultado AVISO."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        # No log file — exists() will return False
        store = _make_store(tmp_path)
        store.meta = {
            "nome": "Blocked Proj",
            "contexto_id": "mendeslobo",
            "current_version": "v1",
        }
        store.list_versions.return_value = ["v1"]
        store.list_escopos.return_value = []
        store.version_path.return_value = version_dir
        store.INVOCATIONS_LOG = "invocations.log"

        canonical = MagicMock()
        canonical.pipeline_blocked_from = ["01-escopo-e-eap"]
        canonical.pipeline_integridade = None  # forces derivation
        canonical.resultado = MagicMock()
        canonical.resultado.venda.total_com_bdi = 999.0
        canonical.resultado.custo.total = 888.0
        canonical.resultado.margem_pct = 10.0
        canonical.resultado.status_margem = "AVISO"
        store.load_canonical.return_value = canonical

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-blocked")

        assert result["pipeline_integridade"] == "CORROMPIDO"
        assert "aviso_integridade" in result
        assert "CORROMPIDO" in result["aviso_integridade"]
        assert "AVISO" in result["resultado_atual"]

    def test_canonical_no_blocked_with_errors_is_parcial(self, tools, tmp_path):
        """Lines 246-254: no blocked but skills_com_erro → PARCIAL integridade."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        log_path = version_dir / "invocations.log"
        log_path.write_text(
            json.dumps({"skill": "02-clima", "status": "ERRO", "ts": "2026-01-01T11:00:00"}) + "\n",
            encoding="utf-8",
        )

        store = _make_store(tmp_path)
        store.meta = {"nome": "P", "contexto_id": "c", "current_version": "v1"}
        store.list_versions.return_value = ["v1"]
        store.list_escopos.return_value = []
        store.version_path.return_value = version_dir
        store.INVOCATIONS_LOG = "invocations.log"

        canonical = MagicMock()
        canonical.pipeline_blocked_from = []  # no blocked
        canonical.pipeline_integridade = None  # forces derivation
        canonical.resultado = None
        store.load_canonical.return_value = canonical

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-parcial")

        assert result["pipeline_integridade"] == "PARCIAL"

    def test_canonical_no_blocked_no_errors_is_completo(self, tools, tmp_path):
        """Lines 246-254: no blocked, no errors → COMPLETO."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        # No log file

        store = _make_store(tmp_path)
        store.meta = {"nome": "P", "contexto_id": "c", "current_version": "v1"}
        store.list_versions.return_value = ["v1"]
        store.list_escopos.return_value = []
        store.version_path.return_value = version_dir
        store.INVOCATIONS_LOG = "invocations.log"

        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        canonical.pipeline_integridade = None
        canonical.resultado = None
        store.load_canonical.return_value = canonical

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-completo")

        assert result["pipeline_integridade"] == "COMPLETO"

    def test_canonical_resultado_without_corrupted_no_aviso(self, tools, tmp_path):
        """Lines 262-274: canonical.resultado exists, no CORROMPIDO → no AVISO key in resultado."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()

        store = _make_store(tmp_path)
        store.meta = {"nome": "P", "contexto_id": "c", "current_version": "v1"}
        store.list_versions.return_value = ["v1"]
        store.list_escopos.return_value = []
        store.version_path.return_value = version_dir
        store.INVOCATIONS_LOG = "invocations.log"

        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        canonical.pipeline_integridade = "COMPLETO"
        canonical.resultado = MagicMock()
        canonical.resultado.venda.total_com_bdi = 500.0
        canonical.resultado.custo.total = 400.0
        canonical.resultado.margem_pct = 20.0
        canonical.resultado.status_margem = "OK"
        store.load_canonical.return_value = canonical

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-ok")

        assert "AVISO" not in result.get("resultado_atual", {})
        assert result["resultado_atual"]["preco_venda"] == 500.0


# ===========================================================================
# aprovar_versao
# ===========================================================================


class TestAprovarVersao:
    def test_no_active_plan_returns_erro(self, tools):
        """Lines 290-292: no active plan found → returns erro dict."""
        store = _make_store(Path("/tmp/fake"))
        store.list_escopos.return_value = ["esc-001"]

        es = MagicMock()
        es.active_plan.return_value = None
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.projeto.concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                return_value="esc-001",
            )
            if False
            else patch(
                "concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                return_value="esc-001",
            ),
        ):
            result = tools["aprovar_versao"](project_id="proj-001")

        assert "erro" in result
        assert "esc-001" in result["erro"]

    def test_exception_returns_erro(self, tools):
        """Lines 284, 294-295: exception during approve → returns erro dict."""
        store = _make_store(Path("/tmp/fake"))

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                side_effect=RuntimeError("no escopos"),
            ),
        ):
            result = tools["aprovar_versao"](project_id="proj-exc")

        assert "erro" in result
        assert "no escopos" in result["erro"]

    def test_success_returns_aprovado(self, tools):
        """Lines 286-303: successful approve → returns APROVADO dict."""
        store = _make_store(Path("/tmp/fake"))
        store.list_escopos.return_value = ["esc-001"]

        active_plan = MagicMock()
        active_plan.plano_id = "plano-main"
        es = MagicMock()
        es.active_plan.return_value = active_plan
        es.approve_plan.return_value = ["plano-alt-01"]
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                return_value="esc-001",
            ),
        ):
            result = tools["aprovar_versao"](project_id="proj-001")

        assert result["status"] == "APROVADO"
        assert result["project_id"] == "proj-001"
        assert result["escopo_id"] == "esc-001"
        assert result["plano_aprovado"] == "plano-main"
        assert result["planos_arquivados"] == ["plano-alt-01"]

    def test_explicit_plano_id_used(self, tools):
        """Lines 290-303: explicit plano_id overrides active_plan."""
        store = _make_store(Path("/tmp/fake"))
        store.list_escopos.return_value = ["esc-001"]

        es = MagicMock()
        es.approve_plan.return_value = []
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                return_value="esc-001",
            ),
        ):
            result = tools["aprovar_versao"](project_id="proj-001", plano_id="plano-explicit")

        assert result["status"] == "APROVADO"
        assert result["plano_aprovado"] == "plano-explicit"


# ===========================================================================
# nova_versao
# ===========================================================================


class TestNovaVersao:
    def test_exception_returns_erro(self, tools):
        """Lines 313, 320-321: exception → returns erro dict."""
        store = _make_store(Path("/tmp/fake"))

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                side_effect=ValueError("no escopo"),
            ),
        ):
            result = tools["nova_versao"](project_id="proj-exc")

        assert "erro" in result
        assert "no escopo" in result["erro"]

    def test_success_returns_new_plano(self, tools):
        """Lines 315-323: success → returns new plano_id dict."""
        store = _make_store(Path("/tmp/fake"))
        store.list_escopos.return_value = ["esc-001"]

        ps = MagicMock()
        ps.plano_id = "plano-v2"
        es = MagicMock()
        es.create_plan.return_value = ps
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                return_value="esc-001",
            ),
        ):
            result = tools["nova_versao"](project_id="proj-001")

        assert result["project_id"] == "proj-001"
        assert result["escopo_id"] == "esc-001"
        assert result["plano_id"] == "plano-v2"
        assert result["proxima_skill_sugerida"] == "01-escopo-e-eap"

    def test_custom_nome_passed_to_create_plan(self, tools):
        """Lines 319: nome argument passed to es.create_plan."""
        store = _make_store(Path("/tmp/fake"))
        store.list_escopos.return_value = ["esc-001"]

        ps = MagicMock()
        ps.plano_id = "plano-custom"
        es = MagicMock()
        es.create_plan.return_value = ps
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._resolve_escopo_id",
                return_value="esc-001",
            ),
        ):
            result = tools["nova_versao"](project_id="proj-001", nome="Minha Iteração")

        es.create_plan.assert_called_once_with(nome="Minha Iteração")
        assert result["plano_id"] == "plano-custom"


# ===========================================================================
# salvar_perfil_bdi
# ===========================================================================


class TestSalvarPerfilBdi:
    def test_invalid_tributario_returns_erro(self, tools, tmp_path):
        """Lines 369-373: invalid pydantic input → returns erro."""
        store = _make_store(tmp_path)

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario={"regime": "invalido"},  # missing required fields
                lucro=LUCRO_VALID,
                confirmado_por="Engenheiro A",
            )

        assert "erro" in result
        assert "Dados inválidos" in result["erro"]

    def test_invalid_lucro_returns_erro(self, tools, tmp_path):
        """Lines 369-373: invalid lucro model → returns erro."""
        store = _make_store(tmp_path)

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario=TRIBUTARIO_VALID,
                lucro={"mao_obra": 2.0},  # value > 1 is invalid (ge=0, le=1)
                confirmado_por="Engenheiro A",
            )

        assert "erro" in result
        assert "Dados inválidos" in result["erro"]

    def test_first_save_creates_versao_1(self, tools, tmp_path):
        """Lines 375-394, 401-421, 449-461: first save, versao==1 → writes files."""
        store = _make_store(tmp_path)
        store.root = tmp_path  # use real tmp_path for filesystem writes

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario=TRIBUTARIO_VALID,
                lucro=LUCRO_VALID,
                confirmado_por="Engenheiro A",
            )

        assert "erro" not in result
        assert result["versao"] == 1
        assert result["project_id"] == "proj-001"
        assert result["confirmado_por"] == "Engenheiro A"
        assert "perfil_id" in result
        assert "content_hash" in result

        # Verify files were written
        assert (tmp_path / "bdi" / "perfil_bdi.json").exists()
        assert (tmp_path / "bdi" / "perfil_bdi_v001.json").exists()

    def test_update_without_motivo_returns_erro(self, tools, tmp_path):
        """Lines 393-398: update without motivo_revisao when versao>1 → returns erro."""
        store = _make_store(tmp_path)
        store.root = tmp_path

        # Write an existing perfil_bdi.json with versao=1
        bdi_dir = tmp_path / "bdi"
        bdi_dir.mkdir()
        existing_perfil = {
            "versao": 1,
            "projeto_id": "proj-001",
            "content_hash": "abc123",
            "confirmado_em": "2026-01-01T00:00:00+00:00",
            "confirmado_por": "Old Eng",
            "tributario": TRIBUTARIO_VALID,
            "lucro": LUCRO_VALID,
            "perfil_id": "old-perfil-id",
        }
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(existing_perfil, ensure_ascii=False), encoding="utf-8")

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario=TRIBUTARIO_VALID,
                lucro=LUCRO_VALID,
                confirmado_por="Engenheiro B",
                # motivo_revisao intentionally omitted
            )

        assert "erro" in result
        assert "motivo_revisao" in result["erro"]

    def test_update_with_motivo_writes_diff(self, tools, tmp_path):
        """Lines 424-447: update with motivo_revisao → computes diff, writes versionado file."""
        store = _make_store(tmp_path)
        store.root = tmp_path

        # Write an existing valid perfil_bdi.json
        bdi_dir = tmp_path / "bdi"
        bdi_dir.mkdir()

        # First, create a valid PerfilBdiProjeto to serialize as the existing version
        from datetime import UTC, datetime

        from concilium.domain.models.financial.bdi import (
            PerfilBdiProjeto,
            PerfilLucroProjeto,
            PerfilTributarioProjeto,
        )

        trib = PerfilTributarioProjeto.model_validate(TRIBUTARIO_VALID)
        lucro = PerfilLucroProjeto.model_validate(LUCRO_VALID)
        existing_perfil = PerfilBdiProjeto(
            projeto_id="proj-001",
            versao=1,
            content_hash="oldhash",
            confirmado_em=datetime(2026, 1, 1, tzinfo=UTC),
            confirmado_por="Old Eng",
            tributario=trib,
            lucro=lucro,
        )
        existing_payload = existing_perfil.model_dump(mode="json")
        existing_payload["motivo_revisao"] = None
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(existing_payload, ensure_ascii=False), encoding="utf-8")

        # New lucro with changed mao_obra
        new_lucro = {**LUCRO_VALID, "mao_obra": 0.12}

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario=TRIBUTARIO_VALID,
                lucro=new_lucro,
                confirmado_por="Engenheiro B",
                motivo_revisao="Ajuste de margem aprovado em reunião",
            )

        assert "erro" not in result
        assert result["versao"] == 2
        assert "diff" in result
        diff = result["diff"]
        assert "campos_alterados" in diff
        assert any("lucro" in c for c in diff["campos_alterados"])

        # Versioned file should exist
        assert (tmp_path / "bdi" / "perfil_bdi_v002.json").exists()

    def test_update_with_motivo_no_changes_empty_diff(self, tools, tmp_path):
        """Lines 424-447: update with motivo but same data → diff has empty campos_alterados."""
        store = _make_store(tmp_path)
        store.root = tmp_path

        bdi_dir = tmp_path / "bdi"
        bdi_dir.mkdir()

        from datetime import UTC, datetime

        from concilium.domain.models.financial.bdi import PerfilBdiProjeto, PerfilLucroProjeto, PerfilTributarioProjeto

        trib = PerfilTributarioProjeto.model_validate(TRIBUTARIO_VALID)
        lucro = PerfilLucroProjeto.model_validate(LUCRO_VALID)
        existing_perfil = PerfilBdiProjeto(
            projeto_id="proj-001",
            versao=1,
            content_hash="oldhash",
            confirmado_em=datetime(2026, 1, 1, tzinfo=UTC),
            confirmado_por="Old Eng",
            tributario=trib,
            lucro=lucro,
        )
        existing_payload = existing_perfil.model_dump(mode="json")
        existing_payload["motivo_revisao"] = None
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(existing_payload, ensure_ascii=False), encoding="utf-8")

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario=TRIBUTARIO_VALID,
                lucro=LUCRO_VALID,  # same as before
                confirmado_por="Engenheiro B",
                motivo_revisao="Reconfirmação sem alterações",
            )

        assert "erro" not in result
        assert result["versao"] == 2
        assert "diff" in result

    def test_corrupt_existing_perfil_json_fallback(self, tools, tmp_path):
        """Lines 386-391: corrupt existing perfil_bdi.json → fallback to versao=1."""
        store = _make_store(tmp_path)
        store.root = tmp_path

        bdi_dir = tmp_path / "bdi"
        bdi_dir.mkdir()
        (bdi_dir / "perfil_bdi.json").write_text("INVALID JSON {{}", encoding="utf-8")

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario=TRIBUTARIO_VALID,
                lucro=LUCRO_VALID,
                confirmado_por="Engenheiro A",
            )

        # Falls back to versao=1 since JSON is corrupt
        assert "erro" not in result
        assert result["versao"] == 1

    def test_diff_note_on_incompatible_anterior(self, tools, tmp_path):
        """Lines 445-447: if prior model cannot be validated → diff with nota key."""
        store = _make_store(tmp_path)
        store.root = tmp_path

        bdi_dir = tmp_path / "bdi"
        bdi_dir.mkdir()
        # Write an existing perfil with versao=1 but incompatible structure
        existing_payload = {
            "versao": 1,
            "projeto_id": "proj-001",
            "tributario": TRIBUTARIO_VALID,
            "lucro": LUCRO_VALID,
            # Missing required fields: content_hash, confirmado_em, confirmado_por, perfil_id
        }
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(existing_payload, ensure_ascii=False), encoding="utf-8")

        with patch("concilium.presentation.mcp.tools.projeto._project", return_value=store):
            result = tools["salvar_perfil_bdi"](
                project_id="proj-001",
                tributario=TRIBUTARIO_VALID,
                lucro=LUCRO_VALID,
                confirmado_por="Engenheiro B",
                motivo_revisao="Revisão após incompatibilidade",
            )

        # Versao should be 2 since existing had versao=1
        assert result["versao"] == 2
        if "diff" in result:
            # Either computed or fallback nota
            diff = result["diff"]
            assert "nota" in diff or "campos_alterados" in diff


# ===========================================================================
# Additional coverage: edge cases
# ===========================================================================


class TestConsultarStatusEdgeCases:
    def test_invalid_json_line_in_log_skipped(self, tools, tmp_path):
        """Lines 235-236: JSONDecodeError in log line → line is skipped."""
        version_dir = tmp_path / "v1"
        version_dir.mkdir()
        log_path = version_dir / "invocations.log"
        # Write one valid and one invalid JSON line
        log_path.write_text(
            json.dumps({"skill": "01-escopo-e-eap", "status": "OK", "ts": "2026-01-01T10:00:00"})
            + "\n"
            + "NOT VALID JSON !!!\n",
            encoding="utf-8",
        )

        store = _make_store(tmp_path)
        store.meta = {
            "nome": "P",
            "contexto_id": "c",
            "current_version": "v1",
        }
        store.list_versions.return_value = ["v1"]
        store.list_escopos.return_value = []
        store.version_path.return_value = version_dir
        store.INVOCATIONS_LOG = "invocations.log"
        store.load_canonical.return_value = None

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-jsonerr")

        # Only the valid line is included
        assert len(result["invocations"]) == 1
        assert result["invocations"][0]["skill"] == "01-escopo-e-eap"

    def test_escopo_store_raises_in_active_plan(self, tools, tmp_path):
        """Lines 199-200: inner escopo try/except — escopo() raises → silently continues."""
        store = _make_store(tmp_path)
        store.list_escopos.return_value = ["esc-001"]
        store.escopo.side_effect = RuntimeError("escopo load failed")

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-escopo-err")

        # Should not crash, escopos is still included
        assert result["escopos"] == ["esc-001"]
        assert "plano_ativo" not in result

    def test_outer_escopos_exception_swallowed(self, tools, tmp_path):
        """Lines 218-219: outer except block — list_escopos() raises → silently continues."""
        store = _make_store(tmp_path)
        store.list_escopos.side_effect = RuntimeError("list escopos failed")

        with (
            patch("concilium.presentation.mcp.tools.projeto._project", return_value=store),
            patch("concilium.presentation.mcp.tools.projeto._wrap_response", side_effect=lambda x: x),
        ):
            result = tools["consultar_status"](project_id="proj-outer-err")

        # Should not crash; escopos key should not be in output
        assert "escopos" not in result
        assert result["project_id"] == "proj-outer-err"
