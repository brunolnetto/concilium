"""Tests for concilium.presentation.mcp.tools.escopo — unit coverage.

Coverage targets:
  _resolve_escopo_id: all branches (no escopos, explicit valid, explicit invalid,
                      auto-infer single, multi-escopo error)
  consultar_estrutura_projeto: empty escopos, multiple escopos with plans,
                               canonical resultado None vs set
  gerir_escopo (entidade="escopo"): success path, create_escopo raises
  gerir_escopo (entidade="plano"): criar, aprovar with/without plano_id, arquivar with/without
                                   plano_id, invalid acao
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id, register

# ---------------------------------------------------------------------------
# Fixture: build server and extract tool callables
# ---------------------------------------------------------------------------


@pytest.fixture()
def tools():
    """Register escopo tools on a fresh FastMCP instance and return {name: fn}."""
    server = FastMCP("test-escopo")
    register(server)
    tool_map = server._tool_manager._tools
    return {name: tool.fn for name, tool in tool_map.items()}


# ---------------------------------------------------------------------------
# Helper: build a minimal mock store
# ---------------------------------------------------------------------------


def _make_store(escopos: list[str] | None = None) -> MagicMock:
    store = MagicMock()
    store.meta = {"id": "proj-test", "nome": "Test Project"}
    store.list_escopos.return_value = escopos if escopos is not None else []
    return store


# ===========================================================================
# _resolve_escopo_id — pure function tests (no MCP involved)
# ===========================================================================


class TestResolveEscopoId:
    def test_no_escopos_raises(self):
        """Empty escopos list → ValueError mentioning 'não possui escopos'."""
        store = _make_store(escopos=[])
        with pytest.raises(ValueError, match="não possui escopos"):
            _resolve_escopo_id(store)

    def test_explicit_valid_id_returned(self):
        """Explicit escopo_id that exists → returned as-is."""
        store = _make_store(escopos=["esc-a", "esc-b"])
        result = _resolve_escopo_id(store, escopo_id="esc-a")
        assert result == "esc-a"

    def test_explicit_invalid_id_raises(self):
        """Explicit escopo_id not in list → ValueError mentioning available escopos."""
        store = _make_store(escopos=["esc-a", "esc-b"])
        with pytest.raises(ValueError, match="não encontrado"):
            _resolve_escopo_id(store, escopo_id="esc-missing")

    def test_auto_infer_single_escopo(self):
        """Single escopo and no explicit id → returns the only escopo."""
        store = _make_store(escopos=["esc-only"])
        result = _resolve_escopo_id(store)
        assert result == "esc-only"

    def test_multi_escopo_no_id_raises(self):
        """Multiple escopos and no explicit id → ValueError asking user to specify."""
        store = _make_store(escopos=["esc-a", "esc-b", "esc-c"])
        with pytest.raises(ValueError, match="múltiplos escopos"):
            _resolve_escopo_id(store)


# ===========================================================================
# consultar_estrutura_projeto
# ===========================================================================


class TestConsultarEstruturaProjeto:
    def test_empty_escopos_returns_empty_list(self, tools):
        """No escopos → escopos list is empty in response."""
        store = _make_store(escopos=[])

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["consultar_estrutura_projeto"](project_id="proj-001")

        assert result["project_id"] == "proj-001"
        assert result["escopos"] == []

    def test_escopo_with_plans_canonical_resultado_none(self, tools):
        """Escopo with one plan where canonical.resultado is None → margem_pct is None."""
        # Build plan store mock
        ps = MagicMock()
        ps.meta = {"nome": "Plano A", "status": "rascunho"}
        can = MagicMock()
        can.resultado = None
        ps.load_canonical.return_value = can

        # Build escopo mock
        es = MagicMock()
        es.meta = {"nome": "Escopo Teste", "tipo_obra": "terraplenagem", "status": "ativo"}
        es.list_plans.return_value = ["plano-001"]
        es.plan.return_value = ps

        store = _make_store(escopos=["esc-001"])
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["consultar_estrutura_projeto"](project_id="proj-001")

        assert len(result["escopos"]) == 1
        esc_out = result["escopos"][0]
        assert esc_out["escopo_id"] == "esc-001"
        assert esc_out["nome"] == "Escopo Teste"
        assert esc_out["tipo_obra"] == "terraplenagem"
        assert len(esc_out["planos"]) == 1
        plano_out = esc_out["planos"][0]
        assert plano_out["plano_id"] == "plano-001"
        assert plano_out["nome"] == "Plano A"
        assert plano_out["status"] == "rascunho"
        assert plano_out["margem_pct"] is None

    def test_escopo_with_plans_canonical_resultado_set(self, tools):
        """Escopo with plan where canonical.resultado has margem_pct set."""
        ps = MagicMock()
        ps.meta = {"nome": "Plano B", "status": "aprovado"}
        can = MagicMock()
        can.resultado = MagicMock()
        can.resultado.margem_pct = 15.5
        ps.load_canonical.return_value = can

        es = MagicMock()
        es.meta = {"nome": "Escopo B", "tipo_obra": "pavimentacao", "status": "aprovado"}
        es.list_plans.return_value = ["plano-002"]
        es.plan.return_value = ps

        store = _make_store(escopos=["esc-002"])
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["consultar_estrutura_projeto"](project_id="proj-002")

        plano_out = result["escopos"][0]["planos"][0]
        assert plano_out["margem_pct"] == 15.5

    def test_canonical_load_returns_none_margem_pct_none(self, tools):
        """When load_canonical returns None (not just resultado=None) → margem_pct is None."""
        ps = MagicMock()
        ps.meta = {"nome": "Plano C", "status": "rascunho"}
        ps.load_canonical.return_value = None  # entire canonical is None

        es = MagicMock()
        es.meta = {"nome": "Escopo C", "tipo_obra": "drenagem", "status": "rascunho"}
        es.list_plans.return_value = ["plano-003"]
        es.plan.return_value = ps

        store = _make_store(escopos=["esc-003"])
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["consultar_estrutura_projeto"](project_id="proj-003")

        plano_out = result["escopos"][0]["planos"][0]
        assert plano_out["margem_pct"] is None

    def test_multiple_escopos(self, tools):
        """Multiple escopos are all returned in output list."""

        def _make_es(nome: str, typ: str, plan_ids: list[str]) -> MagicMock:
            es = MagicMock()
            es.meta = {"nome": nome, "tipo_obra": typ, "status": "ativo"}
            es.list_plans.return_value = plan_ids
            ps = MagicMock()
            ps.meta = {"nome": "P", "status": "rascunho"}
            ps.load_canonical.return_value = None
            es.plan.return_value = ps
            return es

        store = _make_store(escopos=["esc-x", "esc-y"])
        escopos_map = {
            "esc-x": _make_es("Escopo X", "terra", ["p-x1"]),
            "esc-y": _make_es("Escopo Y", "pav", []),
        }
        store.escopo.side_effect = lambda eid: escopos_map[eid]

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["consultar_estrutura_projeto"](project_id="proj-multi")

        assert len(result["escopos"]) == 2
        ids = [e["escopo_id"] for e in result["escopos"]]
        assert "esc-x" in ids
        assert "esc-y" in ids

    def test_escopo_with_no_plans(self, tools):
        """Escopo that has no plans → planos list is empty."""
        es = MagicMock()
        es.meta = {"nome": "Escopo Vazio", "tipo_obra": None, "status": None}
        es.list_plans.return_value = []

        store = _make_store(escopos=["esc-empty"])
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["consultar_estrutura_projeto"](project_id="proj-empty")

        esc_out = result["escopos"][0]
        assert esc_out["planos"] == []


# ===========================================================================
# gerir_escopo (entidade="escopo")
# ===========================================================================


class TestConfigurarEscopo:
    _base_kwargs = dict(
        project_id="proj-001",
        entidade="escopo",
        escopo_id="esc-001",
        nome="Escopo de Teste",
        tipo_obra="terraplenagem",
        localizacao="Fortaleza, CE",
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
        coordenadas_lat=-3.71,
        coordenadas_lng=-38.54,
        dias_semana=6,
        horas_dia=8,
    )

    def test_success_path(self, tools):
        """Happy path: create_escopo succeeds → returns status OK and escopo_id."""
        store = _make_store()
        es = MagicMock()
        es.escopo_id = "esc-001"
        store.create_escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](**self._base_kwargs)

        assert result["status"] == "OK"
        assert result["escopo_id"] == "esc-001"
        store.create_escopo.assert_called_once()

    def test_create_escopo_raises_returns_erro(self, tools):
        """create_escopo raises → returns {'erro': str(e)} without crashing."""
        store = _make_store()
        store.create_escopo.side_effect = ValueError("Dados inválidos para escopo")

        with patch("concilium.presentation.mcp.tools.escopo._project", return_value=store):
            result = tools["gerir_escopo"](**self._base_kwargs)

        assert "erro" in result
        assert "Dados inválidos para escopo" in result["erro"]

    def test_default_coordinates_and_regime(self, tools):
        """Default coordenadas_lat/lng=0.0 and dias_semana=6, horas_dia=8 are passed to create_escopo."""
        store = _make_store()
        es = MagicMock()
        es.escopo_id = "esc-defaults"
        store.create_escopo.return_value = es

        minimal_kwargs = dict(
            project_id="proj-001",
            entidade="escopo",
            escopo_id="esc-defaults",
            nome="Mínimo",
            tipo_obra="terra",
            localizacao="BR",
            data_inicio="2026-01-01",
            data_termino="2026-06-30",
        )

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](**minimal_kwargs)

        assert result["status"] == "OK"
        call_kwargs = store.create_escopo.call_args.kwargs
        assert call_kwargs["coordenadas_lat"] == 0.0
        assert call_kwargs["coordenadas_lng"] == 0.0
        assert call_kwargs["dias_semana"] == 6
        assert call_kwargs["horas_dia"] == 8


# ===========================================================================
# gerir_escopo (entidade="escopo", acao="editar_roster_mo") — ADR-173 F3
# ===========================================================================


class TestEditarRosterMo:
    def test_adiciona_membro(self, tools):
        es = MagicMock()
        store = _make_store()
        store.escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="escopo",
                escopo_id="esc-001",
                acao="editar_roster_mo",
                roster_mo_membro={
                    "individuo_id": "mo-001",
                    "funcao_id": "MO-ARMADOR",
                    "salario_base_mensal": 3200.0,
                    "data_admissao": "2026-01-05",
                },
            )

        assert result["status"] == "OK"
        es.upsert_roster_mo_membro.assert_called_once_with(
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3200.0,
                "data_admissao": "2026-01-05",
            }
        )
        store.create_escopo.assert_not_called()

    def test_sem_roster_mo_membro_retorna_erro(self, tools):
        es = MagicMock()
        store = _make_store()
        store.escopo.return_value = es

        with patch("concilium.presentation.mcp.tools.escopo._project", return_value=store):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="escopo",
                escopo_id="esc-001",
                acao="editar_roster_mo",
            )

        assert "erro" in result
        es.upsert_roster_mo_membro.assert_not_called()

    def test_upsert_lanca_excecao_retorna_erro(self, tools):
        es = MagicMock()
        es.upsert_roster_mo_membro.side_effect = ValueError("membro.individuo_id é obrigatório")
        store = _make_store()
        store.escopo.return_value = es

        with patch("concilium.presentation.mcp.tools.escopo._project", return_value=store):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="escopo",
                escopo_id="esc-001",
                acao="editar_roster_mo",
                roster_mo_membro={"funcao_id": "MO-ARMADOR"},
            )

        assert "erro" in result
        assert "individuo_id" in result["erro"]

    def test_acao_criar_ainda_funciona_sem_regressao(self, tools):
        """acao default ('criar') continua chamando create_escopo — editar_roster_mo
        não deve interferir no caminho existente."""
        store = _make_store()
        es = MagicMock()
        es.escopo_id = "esc-001"
        store.create_escopo.return_value = es

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="escopo",
                escopo_id="esc-001",
                nome="Escopo",
                tipo_obra="terraplenagem",
                localizacao="BR",
                data_inicio="2026-01-01",
                data_termino="2026-12-31",
            )

        assert result["status"] == "OK"
        store.create_escopo.assert_called_once()


# ===========================================================================
# gerir_escopo (entidade="plano")
# ===========================================================================


class TestGerenciarPlano:
    def _make_store_with_escopo(self, escopo: MagicMock | None = None) -> MagicMock:
        store = _make_store()
        if escopo is None:
            escopo = MagicMock()
        store.escopo.return_value = escopo
        return store

    def test_criar_plano(self, tools):
        """acao='criar' → calls es.create_plan, returns plano_id."""
        ps = MagicMock()
        ps.plano_id = "plano-novo"
        es = MagicMock()
        es.create_plan.return_value = ps

        store = self._make_store_with_escopo(es)

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="criar",
                nome="Plano Novo",
            )

        assert result["plano_id"] == "plano-novo"
        es.create_plan.assert_called_once_with(nome="Plano Novo", hipotese=None)

    def test_criar_plano_default_nome(self, tools):
        """acao='criar' with no nome → uses 'Novo Plano' as default."""
        ps = MagicMock()
        ps.plano_id = "plano-default"
        es = MagicMock()
        es.create_plan.return_value = ps

        store = self._make_store_with_escopo(es)

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="criar",
            )

        assert result["plano_id"] == "plano-default"
        es.create_plan.assert_called_once_with(nome="Novo Plano", hipotese=None)

    def test_aprovar_with_plano_id(self, tools):
        """acao='aprovar' with plano_id → calls es.approve_plan, returns plano_aprovado."""
        es = MagicMock()
        es.approve_plan.return_value = ["plano-old-1", "plano-old-2"]

        store = self._make_store_with_escopo(es)

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="aprovar",
                plano_id="plano-aprovado",
            )

        assert result["plano_aprovado"] == "plano-aprovado"
        assert result["arquivados"] == ["plano-old-1", "plano-old-2"]
        es.approve_plan.assert_called_once_with("plano-aprovado")

    def test_aprovar_without_plano_id_returns_erro(self, tools):
        """acao='aprovar' without plano_id → returns erro dict."""
        es = MagicMock()
        store = self._make_store_with_escopo(es)

        with patch("concilium.presentation.mcp.tools.escopo._project", return_value=store):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="aprovar",
            )

        assert "erro" in result
        assert "plano_id" in result["erro"]
        es.approve_plan.assert_not_called()

    def test_arquivar_with_plano_id(self, tools):
        """acao='arquivar' with plano_id → calls ps.archive(), returns ARQUIVADO."""
        ps = MagicMock()
        es = MagicMock()
        es.plan.return_value = ps

        store = self._make_store_with_escopo(es)

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="arquivar",
                plano_id="plano-para-arquivar",
            )

        assert result["status"] == "ARQUIVADO"
        assert result["plano_id"] == "plano-para-arquivar"
        es.plan.assert_called_once_with("plano-para-arquivar")
        ps.archive.assert_called_once()

    def test_arquivar_without_plano_id_returns_erro(self, tools):
        """acao='arquivar' without plano_id → returns erro dict."""
        es = MagicMock()
        store = self._make_store_with_escopo(es)

        with patch("concilium.presentation.mcp.tools.escopo._project", return_value=store):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="arquivar",
            )

        assert "erro" in result
        assert "plano_id" in result["erro"]
        es.plan.assert_not_called()

    def test_invalid_acao_returns_erro(self, tools):
        """Unknown acao → returns erro dict with the invalid acao name."""
        es = MagicMock()
        store = self._make_store_with_escopo(es)

        with patch("concilium.presentation.mcp.tools.escopo._project", return_value=store):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="deletar",
            )

        assert "erro" in result
        assert "deletar" in result["erro"]

    def test_entidade_invalida_returns_erro(self, tools):
        """Branch 121->138: entidade fora de {escopo, plano} → erro dict."""
        es = MagicMock()
        store = self._make_store_with_escopo(es)

        with patch("concilium.presentation.mcp.tools.escopo._project", return_value=store):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="insumo",
                escopo_id="esc-001",
                acao="criar",
            )

        assert "erro" in result
        assert "insumo" in result["erro"]

    def test_criar_com_hipotese(self, tools):
        """acao='criar' with hipotese kwarg → hipotese is forwarded to create_plan."""
        ps = MagicMock()
        ps.plano_id = "plano-hip"
        es = MagicMock()
        es.create_plan.return_value = ps

        store = self._make_store_with_escopo(es)

        with (
            patch("concilium.presentation.mcp.tools.escopo._project", return_value=store),
            patch(
                "concilium.presentation.mcp.tools.escopo._wrap_response",
                side_effect=lambda x: x,
            ),
        ):
            result = tools["gerir_escopo"](
                project_id="proj-001",
                entidade="plano",
                escopo_id="esc-001",
                acao="criar",
                hipotese="Hipótese otimista",
            )

        assert result["plano_id"] == "plano-hip"
        es.create_plan.assert_called_once_with(nome="Novo Plano", hipotese="Hipótese otimista")
