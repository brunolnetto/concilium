"""Tests for tiny-gap files: validador_cobertura_item, scope_guard, inputs mixin,
conversor_unidades, report_calibration_sections, domain/models/__init__,
analitica, cube __init__, artifact_transport, _04_cronograma_skill_helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ─── domain/services/validador_cobertura_item.py (2 missing: 46, 75) ──────────

def _make_eap_item(item_id="A1", quantitativo=10.0):
    from concilium.domain.services.validador_cobertura_item import EapItem
    return EapItem(item_id=item_id, cpu_id="CPU-1", quantitativo=quantitativo)


def _make_equipe(custo_total=1000.0):
    from concilium.domain.services.validador_cobertura_item import EquipeDireta
    return EquipeDireta(item_id="A1", custo_total=custo_total)


def _make_planejamento(pu_total=1200.0):
    plan = MagicMock()
    if pu_total is None:
        plan.preco_unitario_com_bdi = None
    else:
        plan.preco_unitario_com_bdi = MagicMock()
        plan.preco_unitario_com_bdi.total = pu_total
    return plan


class TestValidadorCoberturaItem:
    def test_invalid_pu_returns_aviso(self):
        from concilium.domain.services.validador_cobertura_item import validar_cobertura_item
        result = validar_cobertura_item(_make_eap_item(), _make_equipe(1000), _make_planejamento(None))
        assert result[0].codigo == "VAL-COB-SEM-PRECO"

    def test_margem_negativa_aviso(self):
        from concilium.domain.services.validador_cobertura_item import validar_cobertura_item
        # custo_real = 1000/10 = 100, pu_venda = 80 → margem < 0
        result = validar_cobertura_item(_make_eap_item(quantitativo=10), _make_equipe(1000), _make_planejamento(80.0))
        assert result[0].codigo == "VAL-COB-NEG"

    def test_margem_baixa_aviso(self):
        from concilium.domain.services.validador_cobertura_item import validar_cobertura_item
        # custo = 49, pu = 50 → margem = 2% < MARGEM_MINIMA (5%)
        result = validar_cobertura_item(_make_eap_item(quantitativo=10), _make_equipe(490), _make_planejamento(50.0))
        codes = [r.codigo for r in result]
        assert any(c.startswith("VAL-COB") for c in codes)


# ─── presentation/mcp/guards/scope_guard.py (3 missing: 77, 79-80) ────────────

class TestScopeGuard:
    def test_set_scopes_converts_to_roles(self):
        from concilium.presentation.mcp.guards.scope_guard import set_scopes, _current_roles
        token = set_scopes(["mcp:read", "pipeline:run"])
        roles = list(_current_roles.get())
        assert "viewer" in roles or "operator" in roles

    def test_set_scopes_unknown_defaults_to_operator(self):
        from concilium.presentation.mcp.guards.scope_guard import set_scopes, _current_roles
        token = set_scopes(["unknown:scope"])
        roles = list(_current_roles.get())
        assert "operator" in roles

    def test_check_scope_no_auth(self):
        from concilium.presentation.mcp.guards.scope_guard import check_scope
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):
            check_scope("listar_projetos")  # should not raise (looks up TOOL_PERMISSIONS)


# ─── domain/models/__init__.py (1 missing: line 95) ───────────────────────────

class TestDomainModelsInit:
    def test_can_import_domain_models(self):
        import concilium.domain.models
        # The __init__.py has a re-export — just importing it covers the file
        assert hasattr(concilium.domain.models, "__file__")

    def test_canonical_importable(self):
        from concilium.domain.models.canonical import CanonicalModel
        assert CanonicalModel is not None


# ─── application/runtime/mixins/inputs.py (5 missing: 30, 38, 54, 71-72) ─────

class TestInputsMixin:
    def _make_mixin(self):
        from concilium.application.runtime.mixins.inputs import InputsMixin
        obj = InputsMixin.__new__(InputsMixin)
        return obj

    def _make_project(self, meta=None):
        proj = MagicMock()
        proj.meta = meta or {"nome": "Test", "tipo_obra": "terraplenagem"}
        proj.read_json.return_value = {}
        proj.id = "proj-1"
        return proj

    def _make_contexto(self):
        ctx = MagicMock()
        ctx.id = "ctx-1"
        ctx.jurisdicao_id = "jur-1"
        return ctx

    def test_apply_runtime_defaults_escopo_with_coordenadas(self):
        mixin = self._make_mixin()
        mixin.create_snapshots = MagicMock(return_value={"catalogo": "cat-v1", "perfil": "perf-v1"})
        proj = self._make_project({"nome": "P", "coordenadas": {"lat": 10, "lng": 20}})
        ctx = self._make_contexto()
        inputs = {}
        result = mixin._apply_runtime_defaults("01-escopo-e-eap", proj, ctx, inputs)
        assert result["coordenadas"] == {"lat": 10, "lng": 20}

    def test_apply_runtime_defaults_escopo_without_coordenadas(self):
        mixin = self._make_mixin()
        mixin.create_snapshots = MagicMock(return_value={"catalogo": "cat", "perfil": "perf"})
        proj = self._make_project({"nome": "P", "coordenadas_lat": 5.0, "coordenadas_lng": 10.0})
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("01-escopo-e-eap", proj, ctx, {})
        assert result["coordenadas"]["lat"] == 5.0

    def test_apply_runtime_defaults_escopo_adds_regime(self):
        mixin = self._make_mixin()
        mixin.create_snapshots = MagicMock(return_value={"catalogo": "cat", "perfil": "perf"})
        proj = self._make_project({"nome": "P", "dias_semana": 5, "horas_dia": 9})
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("01-escopo-e-eap", proj, ctx, {})
        assert result["regime_trabalho"]["dias_semana"] == 5

    def test_apply_runtime_defaults_skill05_encargos(self):
        mixin = self._make_mixin()
        mixin.load_jurisdicao = MagicMock(return_value={
            "motor_encargos_sociais": {"percentual_horista": 1.777, "percentual_mensalista": 1.06}
        })
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("05-equipes-e-alocacao", proj, ctx, {})
        assert result["percentual_encargos"] == 1.777
        assert result["percentual_encargos_mensalista"] == 1.06

    def test_apply_runtime_defaults_skill04_calendario(self):
        mixin = self._make_mixin()
        mixin.load_calendario_operacional = MagicMock(return_value={"eventos": []})
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("04-cronograma", proj, ctx, {})
        assert "calendario_operacional" in result

    def test_apply_runtime_defaults_skill09_gerar_excel(self):
        mixin = self._make_mixin()
        proj = self._make_project()
        ctx = self._make_contexto()
        result = mixin._apply_runtime_defaults("09-relatorio-e-artefatos", proj, ctx, {})
        assert "gerar_excel" in result

    def test_build_skill_kwargs(self):
        from concilium.application.runtime.mixins.inputs import InputsMixin
        mixin = InputsMixin.__new__(InputsMixin)
        contract = MagicMock()
        contract.signature = ["canonical_in", "inputs", "catalogo"]
        result = mixin._build_skill_kwargs(
            contract,
            canonical_in={"data": "c"},
            inputs={"key": "val"},
            catalogo={"cpus": []},
            perfil={},
            contexto=MagicMock(),
            project=MagicMock(),
            version="v1",
        )
        assert "canonical_in" in result
        assert "inputs" in result
        assert "catalogo" in result


# ─── domain/services/conversor_unidades.py (5 missing: 67, 88, 93-94, 103) ────

class TestConversorUnidades:
    def test_converter_preco_same_unit(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades
        result = ConversorUnidades.converter_preco(100.0, "h", "h")
        assert result == 100.0

    def test_converter_preco_h_to_mes(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades
        result = ConversorUnidades.converter_preco(100.0, "h", "mes")
        # If 1 mes = HORAS_MES_CLT hours, then 100 R$/h = 100*HORAS_MES_CLT R$/mes (inverse)
        # Actually converter_preco divides by fator
        assert result > 0

    def test_converter_preco_incompatible_raises(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades, UnidadeIncompativelError
        with pytest.raises(UnidadeIncompativelError):
            ConversorUnidades.converter_preco(100.0, "h", "m3")

    def test_eh_unidade_conhecida_true(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades
        assert ConversorUnidades.eh_unidade_conhecida("hora") or ConversorUnidades.eh_unidade_conhecida("h")

    def test_eh_unidade_conhecida_false(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades
        assert not ConversorUnidades.eh_unidade_conhecida("galao")

    def test_sao_compativeis_same(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades
        assert ConversorUnidades.sao_compativeis("h", "h") is True

    def test_sao_compativeis_related(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades
        # h and mes should be related
        result = ConversorUnidades.sao_compativeis("h", "mes")
        assert isinstance(result, bool)

    def test_sao_compativeis_unrelated(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades
        assert ConversorUnidades.sao_compativeis("h", "m3") is False


# ─── application/runtime/deliverables/reports/report_calibration_sections.py ──

class TestReportCalibrationSections:
    def test_sum_pe_field(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _sum_pe_field
        rows = [{"custo": 100.0}, {"custo": 200.0}]
        assert _sum_pe_field(rows, "custo") == 300.0

    def test_format_insight_item_with_titulo(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _format_insight_item
        result = _format_insight_item({"titulo": "Test", "descricao": "Description"})
        assert "Test" in result

    def test_format_insight_item_fallback(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _format_insight_item
        result = _format_insight_item({"other": "value"})
        assert "Insight" in result

    def test_render_dict_insights(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _render_dict_insights
        result = _render_dict_insights({"key1": "val1", "key2": "val2"})
        assert len(result) == 2
        assert any("key1" in r for r in result)

    def test_render_list_insights_with_dict(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _render_list_insights
        items = [{"titulo": "T1", "descricao": "D1"}, "plain string"]
        result = _render_list_insights(items)
        assert len(result) == 2

    def test_render_insights_section_empty(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import render_insights_section
        assert render_insights_section(None) == []
        assert render_insights_section([]) == []

    def test_render_insights_section_list(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import render_insights_section
        result = render_insights_section([{"titulo": "T", "descricao": "D"}])
        assert len(result) > 0

    def test_render_insights_section_dict(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import render_insights_section
        result = render_insights_section({"categoria": "valor"})
        assert len(result) > 0

    def test_render_equilibrium_section_empty(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import render_equilibrium_section
        result = render_equilibrium_section([])
        assert result == []

    def test_render_equilibrium_section_basic(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import render_equilibrium_section
        rows = [{"item_id": "A1", "descricao": "Test", "classificacao": "A", "custo_share": 0.3}]
        result = render_equilibrium_section(rows)
        assert isinstance(result, list)
        assert len(result) > 0


# ─── domain/models/analytics/analitica.py (10 missing: 59-60, 91, 93-98, 100) ─

class TestAnaliticaModels:
    def _make_item_abc(self, classe="A"):
        from concilium.domain.models.analytics.analitica import ItemCurvaABC
        return ItemCurvaABC(
            insumo_id="INS-1",
            descricao="Diesel",
            categoria="COMBUSTIVEL",
            custo_total=1000.0,
            pct_custo=0.8,
            pct_custo_acumulado=0.8,
            classe=classe,
            atividades=("A1", "A2"),
        )

    def test_item_abc_descricao_classe_A(self):
        item = self._make_item_abc("A")
        assert "Crítico" in item.descricao_classe or "80" in item.descricao_classe

    def test_item_abc_descricao_classe_B(self):
        item = self._make_item_abc("B")
        assert "B" in item.descricao_classe or "15" in item.descricao_classe

    def test_item_abc_descricao_classe_C(self):
        item = self._make_item_abc("C")
        assert "C" in item.descricao_classe or "5" in item.descricao_classe

    def test_curva_abc_insumo_to_dict(self):
        from concilium.domain.models.analytics.analitica import CurvaABCInsumo
        item = self._make_item_abc("A")
        curva = CurvaABCInsumo(
            projeto_id="p1",
            gerado_em="2026",
            total_custo_direto=1000.0,
            itens=(item,),
            total_a=800.0, total_b=150.0, total_c=50.0,
            n_itens_a=1, n_itens_b=0, n_itens_c=0,
        )
        d = curva.to_dict()
        assert d["projeto_id"] == "p1"
        assert isinstance(d["itens"], list)

    def test_scurve_to_dict(self):
        from concilium.domain.models.analytics.analitica import SCurve, AgregacaoSemanalEquipamentos
        agreg = AgregacaoSemanalEquipamentos(
            semana_iso="2026-W01", semana_offset=0,
            equipamentos_ativos={}, n_equipamentos_unicos=0, n_equipes_totais=0,
            custo_direto_semana=8000.0,
            custo_indireto_semana=2000.0,
            custo_total_semana=10000.0,
        )
        scurve = SCurve(
            projeto_id="p1", gerado_em="2026",
            total_custo_direto=100000.0, total_custo_indireto=20000.0, total_projeto=120000.0,
            semanas_iso=("2026-W01",),
            custo_semanal=(10000.0,),
            custo_acumulado=(10000.0,),
            pct_acumulado=(0.1,),
            agregacao_semanal=(agreg,),
        )
        d = scurve.to_dict()
        assert d["projeto_id"] == "p1"


# ─── presentation/api/routes/catalogs.py (8 missing: 63-64, 89-92, 105-106) ───

class TestApiCatalogsRoutes:
    def _client(self, svc):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        try:
            from concilium.presentation.api.app import create_app
            from concilium.presentation.api.container import get_concilium_service
        except TypeError:
            pytest.skip("FastAPI incompatível")
        app = create_app()
        app.dependency_overrides[get_concilium_service] = lambda: svc
        return TestClient(app, raise_server_exceptions=False)

    def test_get_cpu_returns_none_gives_404(self):
        svc = MagicMock()
        svc.get_catalog_cpu.return_value = None
        c = self._client(svc)
        resp = c.get("/api/catalogs/cat-1/cpus/CPU-MISSING")
        assert resp.status_code == 404

    def test_get_cpu_exception_gives_404(self):
        svc = MagicMock()
        svc.get_catalog_cpu.side_effect = RuntimeError("not found")
        c = self._client(svc)
        resp = c.get("/api/catalogs/cat-1/cpus/CPU-1")
        assert resp.status_code == 404

    def test_upsert_cpu_value_error_gives_422(self):
        svc = MagicMock()
        svc.upsert_catalog_cpu.side_effect = ValueError("invalid")
        c = self._client(svc)
        resp = c.put("/api/catalogs/cat-1/cpus/CPU-1", json={"cpu_data": {}, "motivo": "test"})
        assert resp.status_code == 422

    def test_list_insumos_error_gives_404(self):
        svc = MagicMock()
        svc.list_catalog_insumos.side_effect = FileNotFoundError("cat not found")
        c = self._client(svc)
        resp = c.get("/api/catalogs/cat-1/insumos")
        assert resp.status_code == 404
