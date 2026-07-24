"""Tests for MCP analise tools: auditar_plano, comparar_planos, explorar_pool_recursos.

Coverage targets:
  analise.py — register, auditar_plano, comparar_planos, explorar_pool_recursos
  (happy-path, error-path, no-canonical, missing-pool guard)
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp.tools.analise import register

# ---------------------------------------------------------------------------
# Module-level patch paths
# ---------------------------------------------------------------------------

_ESCOPO_MODULE = "concilium.presentation.mcp.tools.escopo"
_ANALISE_MODULE = "concilium.presentation.mcp.tools.analise"
_CUBO_MODULE = "concilium.application.services.analytics.cubo_pool_projection"
_CUBO_ESTOQUE_MODULE = "concilium.application.services.analytics.cubo_estoque_consumivel_projection"

# The tool closures reference _project via the name bound in analise.py at
# import time ("from _context import _project"), so we must patch at the
# analise module, not at _context.
_PROJECT_PATCH = f"{_ANALISE_MODULE}._project"


# ---------------------------------------------------------------------------
# Helper: build server, register tools, extract callables by name
# ---------------------------------------------------------------------------


def _make_tools(monkeypatch, tmp_path: Path) -> dict:
    """Register analise tools and return {name: callable}."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))

    server = FastMCP("test-analise")
    register(server)

    tools: dict = {}
    for tool_obj in server._tool_manager.list_tools():
        fn = getattr(tool_obj, "fn", None) or getattr(tool_obj, "func", None)
        tools[tool_obj.name] = fn
    return tools


# ---------------------------------------------------------------------------
# Canonical mock builder
# ---------------------------------------------------------------------------


def _make_canonical(
    data_termino: datetime.date | None = None,
    custo_total: float = 1_000_000.0,
    margem_pct: float = 25.0,
    status_margem: str = "VERDE",
    conflitos_pico: list | None = None,
    pipeline_integridade: bool = True,
    contratos_recurso: list | None = None,
    instancias_recurso: list | None = None,
    recursos_consumiveis: list | None = None,
    resumo_estoque_consumiveis: list | None = None,
) -> MagicMock:
    """Return a minimal canonical MagicMock with fields accessed by the tools."""
    if data_termino is None:
        data_termino = datetime.date.today() + datetime.timedelta(days=90)
    if conflitos_pico is None:
        conflitos_pico = []

    canonical = MagicMock()
    canonical.projeto.data_termino = data_termino
    canonical.conflitos_pico = conflitos_pico
    canonical.pipeline_integridade = pipeline_integridade

    resultado = MagicMock()
    resultado.custo.total = custo_total
    resultado.margem_pct = margem_pct
    resultado.status_margem = status_margem
    canonical.resultado = resultado

    canonical.contratos_recurso = contratos_recurso
    canonical.instancias_recurso = instancias_recurso
    canonical.recursos_consumiveis = recursos_consumiveis
    canonical.resumo_estoque_consumiveis = resumo_estoque_consumiveis

    return canonical


def _make_store_with_canonical(
    canonical: MagicMock | None, escopo_id: str = "ESC-01", plano_id: str = "PL-01"
) -> MagicMock:
    """Build store/escopo/plan chain returning the given canonical."""
    store = MagicMock()
    store.list_escopos.return_value = [escopo_id]
    store.meta = {"id": "proj-test"}

    escopo = MagicMock()
    active_plan = MagicMock()
    active_plan.plano_id = plano_id
    escopo.active_plan.return_value = active_plan

    plan_store = MagicMock()
    plan_store.load_canonical.return_value = canonical
    escopo.plan.return_value = plan_store

    store.escopo.return_value = escopo
    return store


# ---------------------------------------------------------------------------
# Tests: register() wires three tools
# ---------------------------------------------------------------------------


def test_register_creates_three_tools(monkeypatch, tmp_path):
    """register() must expose auditar_plano, comparar_planos, explorar_pool_recursos."""
    tools = _make_tools(monkeypatch, tmp_path)
    assert "auditar_plano" in tools
    assert "comparar_planos" in tools
    assert "explorar_pool_recursos" in tools
    assert "explorar_estoque_consumiveis" in tools


# ---------------------------------------------------------------------------
# Tests: auditar_plano
# ---------------------------------------------------------------------------


class TestAuditarPlano:
    def test_happy_path(self, monkeypatch, tmp_path):
        """Happy path: returns wrapped dict with viabilidade and financeiro."""
        canonical = _make_canonical(custo_total=500_000, margem_pct=20.0, status_margem="VERDE")
        store = _make_store_with_canonical(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test")

        assert "schema_version" in result
        assert result["escopo_id"] == "ESC-01"
        assert result["plano_id"] == "PL-01"
        assert result["financeiro"]["custo_total"] == 500_000
        assert result["financeiro"]["margem_pct"] == 20.0
        assert result["financeiro"]["status_margem"] == "VERDE"
        assert "viabilidade" in result
        assert "gargalos" in result

    def test_happy_path_with_conflitos(self, monkeypatch, tmp_path):
        """Conflitos in conflitos_pico appear in gargalos (capped at 5)."""
        conflito = MagicMock()
        conflito.recurso_id = "REC-01"
        conflito.semana = "2026-W10"
        conflito.quantidade_excedente = 2.5

        canonical = _make_canonical(conflitos_pico=[conflito] * 7)
        store = _make_store_with_canonical(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test")

        # gargalos is capped at 5
        assert len(result["gargalos"]) == 5
        assert result["viabilidade"]["conflitos_recurso"] == 7

    def test_prazo_ok_false_when_termino_is_past(self, monkeypatch, tmp_path):
        """prazo_ok is False when data_termino is in the past."""
        past = datetime.date.today() - datetime.timedelta(days=1)
        canonical = _make_canonical(data_termino=past)
        store = _make_store_with_canonical(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test")

        assert result["viabilidade"]["prazo_ok"] is False

    def test_no_canonical_returns_erro(self, monkeypatch, tmp_path):
        """When load_canonical() returns None, return {'erro': ...}."""
        store = _make_store_with_canonical(None)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test")

        assert "erro" in result
        assert "canônicos" in result["erro"] or "pipeline" in result["erro"]

    def test_resolve_escopo_id_raises_returns_erro(self, monkeypatch, tmp_path):
        """_resolve_escopo_id raising an exception bubbles up as {'erro': ...}."""
        store = MagicMock()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", side_effect=ValueError("Escopo não encontrado")),
        ):
            result = tools["auditar_plano"]("proj-test")

        assert "erro" in result
        assert "Escopo" in result["erro"]

    def test_active_plan_raises_returns_erro(self, monkeypatch, tmp_path):
        """active_plan() raising an exception returns {'erro': ...}."""
        store = MagicMock()
        store.list_escopos.return_value = ["ESC-01"]

        escopo = MagicMock()
        escopo.active_plan.side_effect = RuntimeError("Sem plano ativo")
        store.escopo.return_value = escopo

        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test")

        assert "erro" in result
        assert "plano ativo" in result["erro"]

    def test_explicit_plano_id(self, monkeypatch, tmp_path):
        """When plano_id is explicitly provided, it is used as-is."""
        canonical = _make_canonical()
        store = _make_store_with_canonical(canonical, plano_id="PL-explicit")

        plan_store = MagicMock()
        plan_store.load_canonical.return_value = canonical
        store.escopo.return_value.plan.return_value = plan_store

        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test", escopo_id="ESC-01", plano_id="PL-explicit")

        assert result["plano_id"] == "PL-explicit"

    def test_no_active_plan_and_no_plano_id_returns_erro(self, monkeypatch, tmp_path):
        """Line 36: plano_id=None and active_plan() returns None -> erro guard."""
        store = MagicMock()
        store.list_escopos.return_value = ["ESC-01"]
        escopo = MagicMock()
        escopo.active_plan.return_value = None
        store.escopo.return_value = escopo

        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test")

        assert "erro" in result
        assert "plano ativo" in result["erro"]

    def test_resultado_none_uses_defaults(self, monkeypatch, tmp_path):
        """When canonical.resultado is None/falsy, financeiro uses default values."""
        canonical = _make_canonical()
        canonical.resultado = None  # force falsy resultado

        store = _make_store_with_canonical(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["auditar_plano"]("proj-test")

        fin = result["financeiro"]
        assert fin["custo_total"] == 0
        assert fin["margem_pct"] == 0
        assert fin["status_margem"] == "VERMELHO"


# ---------------------------------------------------------------------------
# Tests: comparar_planos
# ---------------------------------------------------------------------------


class TestCompararPlanos:
    def _make_comparar_store(self, canonical_a: MagicMock | None, canonical_b: MagicMock | None) -> MagicMock:
        """Build store where plan('PL-A') -> canonical_a and plan('PL-B') -> canonical_b."""
        store = MagicMock()
        escopo = MagicMock()

        def _plan_side_effect(pid):
            ps = MagicMock()
            if pid == "PL-A":
                ps.load_canonical.return_value = canonical_a
            else:
                ps.load_canonical.return_value = canonical_b
            return ps

        escopo.plan.side_effect = _plan_side_effect
        store.escopo.return_value = escopo
        return store

    def test_happy_path_both_have_canonical(self, monkeypatch, tmp_path):
        """Both plans have canonical data — comparacao contains two dicts."""
        term_a = datetime.date(2026, 12, 31)
        term_b = datetime.date(2027, 3, 31)

        can_a = _make_canonical(data_termino=term_a, custo_total=1_000_000, margem_pct=25.0)
        can_b = _make_canonical(data_termino=term_b, custo_total=900_000, margem_pct=30.0)

        store = self._make_comparar_store(can_a, can_b)
        tools = _make_tools(monkeypatch, tmp_path)

        with patch(_PROJECT_PATCH, return_value=store):
            result = tools["comparar_planos"]("proj-test", "ESC-01", "PL-A", "PL-B")

        assert "schema_version" in result
        comp = result["comparacao"]
        assert comp["PL-A"]["custo"] == 1_000_000
        assert comp["PL-A"]["margem"] == 25.0
        assert comp["PL-A"]["termino"] == "2026-12-31"
        assert comp["PL-B"]["custo"] == 900_000
        assert comp["PL-B"]["margem"] == 30.0
        assert comp["PL-B"]["termino"] == "2027-03-31"

    def test_one_plan_no_canonical(self, monkeypatch, tmp_path):
        """Plan without canonical data shows 'Sem dados' string."""
        can_a = _make_canonical(data_termino=datetime.date(2026, 12, 31))
        store = self._make_comparar_store(can_a, None)
        tools = _make_tools(monkeypatch, tmp_path)

        with patch(_PROJECT_PATCH, return_value=store):
            result = tools["comparar_planos"]("proj-test", "ESC-01", "PL-A", "PL-B")

        comp = result["comparacao"]
        assert isinstance(comp["PL-A"], dict)
        assert comp["PL-B"] == "Sem dados"

    def test_both_plans_no_canonical(self, monkeypatch, tmp_path):
        """Both plans without canonical data — both show 'Sem dados'."""
        store = self._make_comparar_store(None, None)
        tools = _make_tools(monkeypatch, tmp_path)

        with patch(_PROJECT_PATCH, return_value=store):
            result = tools["comparar_planos"]("proj-test", "ESC-01", "PL-A", "PL-B")

        comp = result["comparacao"]
        assert comp["PL-A"] == "Sem dados"
        assert comp["PL-B"] == "Sem dados"

    def test_canonical_without_resultado(self, monkeypatch, tmp_path):
        """If can.resultado is falsy, the plan falls into 'Sem dados'."""
        can_a = _make_canonical()
        can_a.resultado = None  # falsy resultado

        store = self._make_comparar_store(can_a, None)
        tools = _make_tools(monkeypatch, tmp_path)

        with patch(_PROJECT_PATCH, return_value=store):
            result = tools["comparar_planos"]("proj-test", "ESC-01", "PL-A", "PL-B")

        # When can is not None but can.resultado is falsy, `if can and can.resultado` is False
        assert result["comparacao"]["PL-A"] == "Sem dados"

    def test_response_contains_schema_version(self, monkeypatch, tmp_path):
        """Response envelope always contains schema_version."""
        store = self._make_comparar_store(None, None)
        tools = _make_tools(monkeypatch, tmp_path)

        with patch(_PROJECT_PATCH, return_value=store):
            result = tools["comparar_planos"]("proj-test", "ESC-01", "PL-A", "PL-B")

        assert "schema_version" in result
        assert "trace_id" in result


# ---------------------------------------------------------------------------
# Tests: explorar_pool_recursos
# ---------------------------------------------------------------------------


class TestExplorarPoolRecursos:
    def _make_pool_store(
        self, canonical: MagicMock | None, escopo_id: str = "ESC-01", plano_id: str = "PL-01"
    ) -> MagicMock:
        """Build store chain for explorar_pool_recursos."""
        store = MagicMock()
        store.list_escopos.return_value = [escopo_id]
        store.meta = {"id": "proj-test"}

        escopo = MagicMock()
        active_plan = MagicMock()
        active_plan.plano_id = plano_id
        escopo.active_plan.return_value = active_plan

        plan_store = MagicMock()
        plan_store.load_canonical.return_value = canonical
        escopo.plan.return_value = plan_store

        store.escopo.return_value = escopo
        return store

    def _make_cubo_result(self) -> dict:
        return {
            "face": "instancia_ciclo_vida",
            "natureza": "fisica",
            "narrativa": "Narrativa de teste",
            "rows": [{"a": 1}],
            "totais": {"total": 100},
            "invariantes_ok": True,
        }

    def test_happy_path(self, monkeypatch, tmp_path):
        """Happy path: returns wrapped projection data."""
        canonical = _make_canonical(contratos_recurso=[{"id": "C1"}])
        store = self._make_pool_store(canonical)
        cubo_result = self._make_cubo_result()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
            patch(f"{_CUBO_MODULE}.resolve_cubo_pool_projection", return_value=cubo_result),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "schema_version" in result
        assert result["face"] == "instancia_ciclo_vida"
        assert result["narrativa"] == "Narrativa de teste"
        assert result["rows"] == [{"a": 1}]
        assert result["invariantes_ok"] is True
        assert result["project_id"] == "proj-test"
        assert result["escopo_id"] == "ESC-01"
        assert result["plano_id"] == "PL-01"

    def test_no_canonical_returns_erro(self, monkeypatch, tmp_path):
        """load_canonical() returning None — error guard triggers."""
        store = self._make_pool_store(None)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" in result
        assert "pipeline" in result["erro"].lower() or "canônicos" in result["erro"]

    def test_resolve_escopo_raises_returns_erro(self, monkeypatch, tmp_path):
        """_resolve_escopo_id raising returns {'erro': ...}."""
        store = MagicMock()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", side_effect=ValueError("sem escopos")),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" in result
        assert "sem escopos" in result["erro"]

    def test_missing_pool_both_none(self, monkeypatch, tmp_path):
        """contratos_recurso=None and instancias_recurso=None triggers pool guard."""
        canonical = _make_canonical(contratos_recurso=None, instancias_recurso=None)
        store = self._make_pool_store(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" in result
        assert "rcpsp_spec" in result["erro"] or "pool" in result["erro"].lower()

    def test_missing_pool_empty_lists(self, monkeypatch, tmp_path):
        """contratos_recurso=[] and instancias_recurso=[] (falsy) triggers pool guard."""
        canonical = _make_canonical(contratos_recurso=[], instancias_recurso=[])
        store = self._make_pool_store(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" in result

    def test_no_plano_id_and_no_active_plan_returns_erro(self, monkeypatch, tmp_path):
        """plano_id=None and escopo.active_plan() returns None — 'sem plano ativo' guard."""
        store = MagicMock()
        store.list_escopos.return_value = ["ESC-01"]
        store.meta = {"id": "proj-test"}
        escopo = MagicMock()
        escopo.active_plan.return_value = None
        store.escopo.return_value = escopo
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" in result
        assert "sem plano ativo" in result["erro"].lower()

    def test_plano_id_explicito_ignora_active_plan(self, monkeypatch, tmp_path):
        """plano_id explícito é usado diretamente, sem consultar active_plan()."""
        canonical = _make_canonical(contratos_recurso=[{"id": "C1"}])
        store = self._make_pool_store(canonical, plano_id="PL-EXPLICITO")
        cubo_result = self._make_cubo_result()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
            patch(f"{_CUBO_MODULE}.resolve_cubo_pool_projection", return_value=cubo_result),
        ):
            result = tools["explorar_pool_recursos"]("proj-test", plano_id="PL-EXPLICITO")

        assert result["plano_id"] == "PL-EXPLICITO"

    def test_instancias_recurso_present_passes_pool_guard(self, monkeypatch, tmp_path):
        """instancias_recurso present (contratos_recurso absent) passes pool guard."""
        canonical = _make_canonical(contratos_recurso=None, instancias_recurso=[{"id": "I1"}])
        store = self._make_pool_store(canonical)
        cubo_result = self._make_cubo_result()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
            patch(f"{_CUBO_MODULE}.resolve_cubo_pool_projection", return_value=cubo_result),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" not in result
        assert "face" in result

    def test_passes_parameters_to_cubo(self, monkeypatch, tmp_path):
        """Optional parameters (face, granularidade, atividade_id, instancia_id) are forwarded."""
        canonical = _make_canonical(contratos_recurso=[{"id": "C1"}])
        store = self._make_pool_store(canonical)
        cubo_result = self._make_cubo_result()
        cubo_result["face"] = "custo_estado_componente"

        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
            patch(f"{_CUBO_MODULE}.resolve_cubo_pool_projection", return_value=cubo_result) as mock_cubo,
        ):
            result = tools["explorar_pool_recursos"](
                "proj-test",
                face="custo_estado_componente",
                granularidade="semana",
                atividade_id="ATI-01",
                instancia_id="INST-01",
            )

        mock_cubo.assert_called_once_with(
            canonical,
            face="custo_estado_componente",
            granularidade="semana",
            atividade_id="ATI-01",
            instancia_id="INST-01",
        )
        assert result["face"] == "custo_estado_componente"

    def test_active_plan_raises_returns_erro(self, monkeypatch, tmp_path):
        """active_plan() raising inside explorar_pool_recursos returns {'erro': ...}."""
        store = MagicMock()
        escopo = MagicMock()
        escopo.active_plan.side_effect = RuntimeError("nenhum plano ativo")
        store.escopo.return_value = escopo

        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" in result
        assert "nenhum plano ativo" in result["erro"]

    def test_no_active_plan_and_no_plano_id_returns_erro(self, monkeypatch, tmp_path):
        """Lines 122/126: plano_id=None and active_plan() returns None -> erro guard."""
        store = MagicMock()
        store.list_escopos.return_value = ["ESC-01"]
        escopo = MagicMock()
        escopo.active_plan.return_value = None
        store.escopo.return_value = escopo

        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_pool_recursos"]("proj-test")

        assert "erro" in result


# ---------------------------------------------------------------------------
# Tests: explorar_estoque_consumiveis (ADR-128 F6)
# ---------------------------------------------------------------------------


class TestExplorarEstoqueConsumiveis:
    def _make_estoque_store(
        self, canonical: MagicMock | None, escopo_id: str = "ESC-01", plano_id: str = "PL-01"
    ) -> MagicMock:
        """Build store chain for explorar_estoque_consumiveis (mirror of pool's helper)."""
        store = MagicMock()
        store.list_escopos.return_value = [escopo_id]
        store.meta = {"id": "proj-test"}

        escopo = MagicMock()
        active_plan = MagicMock()
        active_plan.plano_id = plano_id
        escopo.active_plan.return_value = active_plan

        plan_store = MagicMock()
        plan_store.load_canonical.return_value = canonical
        escopo.plan.return_value = plan_store

        store.escopo.return_value = escopo
        return store

    def _make_cubo_result(self) -> dict:
        return {
            "face": "resumo_por_recurso",
            "natureza": "causal",
            "narrativa": "Narrativa de teste",
            "rows": [{"resource_id": "MA-DIESEL-TESTE"}],
            "totais": {"overflow_total": 0.0},
            "invariantes_ok": True,
        }

    def test_happy_path(self, monkeypatch, tmp_path):
        canonical = _make_canonical(recursos_consumiveis=[{"resource_id": "MA-DIESEL-TESTE"}])
        store = self._make_estoque_store(canonical)
        cubo_result = self._make_cubo_result()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
            patch(f"{_CUBO_ESTOQUE_MODULE}.resolve_cubo_estoque_consumivel_projection", return_value=cubo_result),
        ):
            result = tools["explorar_estoque_consumiveis"]("proj-test")

        assert "schema_version" in result
        assert result["face"] == "resumo_por_recurso"
        assert result["narrativa"] == "Narrativa de teste"
        assert result["rows"] == [{"resource_id": "MA-DIESEL-TESTE"}]
        assert result["invariantes_ok"] is True
        assert result["project_id"] == "proj-test"
        assert result["escopo_id"] == "ESC-01"
        assert result["plano_id"] == "PL-01"

    def test_no_canonical_returns_erro(self, monkeypatch, tmp_path):
        store = self._make_estoque_store(None)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_estoque_consumiveis"]("proj-test")

        assert "erro" in result
        assert "pipeline" in result["erro"].lower() or "canônicos" in result["erro"]

    def test_resolve_escopo_raises_returns_erro(self, monkeypatch, tmp_path):
        store = MagicMock()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", side_effect=ValueError("sem escopos")),
        ):
            result = tools["explorar_estoque_consumiveis"]("proj-test")

        assert "erro" in result
        assert "sem escopos" in result["erro"]

    def test_missing_estoque_both_none_triggers_guard(self, monkeypatch, tmp_path):
        """recursos_consumiveis=None and resumo_estoque_consumiveis=None triggers the guard."""
        canonical = _make_canonical(recursos_consumiveis=None, resumo_estoque_consumiveis=None)
        store = self._make_estoque_store(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_estoque_consumiveis"]("proj-test")

        assert "erro" in result
        assert "estoque" in result["erro"].lower()

    def test_missing_estoque_empty_lists_triggers_guard(self, monkeypatch, tmp_path):
        """recursos_consumiveis=[] and resumo_estoque_consumiveis=[] (falsy) triggers the guard."""
        canonical = _make_canonical(recursos_consumiveis=[], resumo_estoque_consumiveis=[])
        store = self._make_estoque_store(canonical)
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_estoque_consumiveis"]("proj-test")

        assert "erro" in result

    def test_no_plano_id_and_no_active_plan_returns_erro(self, monkeypatch, tmp_path):
        """plano_id=None and escopo.active_plan() returns None — 'sem plano ativo' guard."""
        store = MagicMock()
        store.list_escopos.return_value = ["ESC-01"]
        store.meta = {"id": "proj-test"}
        escopo = MagicMock()
        escopo.active_plan.return_value = None
        store.escopo.return_value = escopo
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
        ):
            result = tools["explorar_estoque_consumiveis"]("proj-test")

        assert "erro" in result
        assert "sem plano ativo" in result["erro"].lower()

    def test_plano_id_explicito_ignora_active_plan(self, monkeypatch, tmp_path):
        """plano_id explícito é usado diretamente, sem consultar active_plan()."""
        canonical = _make_canonical(recursos_consumiveis=[{"resource_id": "MA-DIESEL-TESTE"}])
        store = self._make_estoque_store(canonical, plano_id="PL-EXPLICITO")
        cubo_result = self._make_cubo_result()
        tools = _make_tools(monkeypatch, tmp_path)

        with (
            patch(_PROJECT_PATCH, return_value=store),
            patch(f"{_ESCOPO_MODULE}._resolve_escopo_id", return_value="ESC-01"),
            patch(f"{_CUBO_ESTOQUE_MODULE}.resolve_cubo_estoque_consumivel_projection", return_value=cubo_result),
        ):
            result = tools["explorar_estoque_consumiveis"]("proj-test", plano_id="PL-EXPLICITO")

        assert result["plano_id"] == "PL-EXPLICITO"
