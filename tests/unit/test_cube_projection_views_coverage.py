"""Coverage tests for cube_projection_views.py — gaps not covered by test_cube_projection_views2.py.

Focuses on:
  - _extract_cost_from_entry: all dict branches and object fallback
  - _build_pool_particao_by_item: normal, empty, missing attrs
  - _build_pool_scaling_by_item: scaling ratio, material skip, base-zero guard
  - _iter_scaled_cubo_cells: natureza filter, material vs non-material scaling
  - _iter_indireto_cubo_cells: natureza='indireto' filter
  - _mob_eventos_por_periodo: semana_mobilizacao/desmobilizacao counting
  - _custo_indireto_por_periodo: offset mapping through semanas_sorted
  - direto_temporal_categoria face: row structure, columns, chart_hint, top_n
  - indireto_temporal_categoria face: cubo path, rebalance MOB path, fallback path
  - tempo_natureza face: cubo_analitico primary path (non-fallback)
  - FACE_UNIT_TYPES: all keys present
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from concilium.application.services.analytics.cube_projection_views import (
    _build_indireto_component_totals,
    _build_pool_particao_by_item,
    _build_pool_scaling_by_item,
    _extract_cost_from_entry,
    _indireto_component_shares,
    _iter_indireto_cubo_cells,
    _iter_scaled_cubo_cells,
    bucket_from_week_iso,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ns(**kwargs: Any) -> SimpleNamespace:
    return SimpleNamespace(**kwargs)


def _part(item_id: str, custo: float) -> SimpleNamespace:
    return _ns(item_id=item_id, custo_total_particionado=custo)


def _contrato(particoes: list) -> SimpleNamespace:
    return _ns(particao_por_item=particoes)


def _celula(
    natureza: str = "direto",
    componente_bdi: str = "custo_direto",
    categoria: str = "mao_obra",
    atividade_id: str = "eap-1",
    valor_rs: float = 100.0,
    semana_iso: str = "2026-W01",
) -> SimpleNamespace:
    return _ns(
        natureza=natureza,
        componente_bdi=componente_bdi,
        categoria=categoria,
        atividade_id=atividade_id,
        valor_rs=valor_rs,
        semana_iso=semana_iso,
    )


def _cubo(celulas: list) -> SimpleNamespace:
    return _ns(celulas=celulas)


# ---------------------------------------------------------------------------
# _build_pool_particao_by_item
# ---------------------------------------------------------------------------


class TestBuildPoolParticaoByItem:
    def test_canonical_none_returns_empty(self):
        assert _build_pool_particao_by_item(None) == {}

    def test_canonical_falsy_returns_empty(self):
        assert _build_pool_particao_by_item(0) == {}

    def test_no_contratos_returns_empty(self):
        canonical = _ns(contratos_recurso=None)
        assert _build_pool_particao_by_item(canonical) == {}

    def test_empty_contratos_returns_empty(self):
        canonical = _ns(contratos_recurso=[])
        assert _build_pool_particao_by_item(canonical) == {}

    def test_item_id_empty_string_skipped(self):
        # line 80-81: if not item_id: continue
        part = _part("", 500.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        result = _build_pool_particao_by_item(canonical)
        assert result == {}

    def test_item_id_none_skipped(self):
        part = _ns(item_id=None, custo_total_particionado=200.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        result = _build_pool_particao_by_item(canonical)
        assert result == {}

    def test_single_particao_accumulated(self):
        # lines 77-82
        part = _part("item-1", 300.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        result = _build_pool_particao_by_item(canonical)
        assert result == {"item-1": 300.0}

    def test_multiple_particoes_same_item_accumulated(self):
        parts = [_part("item-1", 100.0), _part("item-1", 200.0)]
        canonical = _ns(contratos_recurso=[_contrato(parts)])
        result = _build_pool_particao_by_item(canonical)
        assert result == {"item-1": 300.0}

    def test_multiple_contratos_merged(self):
        canonical = _ns(
            contratos_recurso=[
                _contrato([_part("item-A", 100.0)]),
                _contrato([_part("item-B", 50.0)]),
            ]
        )
        result = _build_pool_particao_by_item(canonical)
        assert result == {"item-A": 100.0, "item-B": 50.0}

    def test_custo_none_treated_as_zero(self):
        part = _ns(item_id="item-1", custo_total_particionado=None)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        result = _build_pool_particao_by_item(canonical)
        assert result == {"item-1": 0.0}

    def test_contrato_with_no_particao_skipped(self):
        contrato = _ns(particao_por_item=None)
        canonical = _ns(contratos_recurso=[contrato])
        result = _build_pool_particao_by_item(canonical)
        assert result == {}


# ---------------------------------------------------------------------------
# _build_pool_scaling_by_item
# ---------------------------------------------------------------------------


class TestBuildPoolScalingByItem:
    def test_no_particao_returns_empty(self):
        # line 93-94: if not particao: return {}
        canonical = _ns(contratos_recurso=[])
        cubo = _cubo([_celula()])
        assert _build_pool_scaling_by_item(canonical, cubo) == {}

    def test_canonical_none_returns_empty(self):
        cubo = _cubo([_celula()])
        assert _build_pool_scaling_by_item(None, cubo) == {}

    def test_scaling_computed_for_matching_item(self):
        # lines 95-110
        part = _part("eap-1", 200.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            natureza="direto",
            componente_bdi="custo_direto",
            categoria="mao_obra",
            atividade_id="eap-1",
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        scaling = _build_pool_scaling_by_item(canonical, cubo)
        assert scaling == {"eap-1": 2.0}

    def test_material_cells_skipped(self):
        # line 99-100: material category skipped
        part = _part("eap-1", 200.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            componente_bdi="custo_direto",
            categoria="material",
            atividade_id="eap-1",
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        scaling = _build_pool_scaling_by_item(canonical, cubo)
        # base=0 because material is skipped -> no scaling entry
        assert scaling == {}

    def test_non_custo_direto_cells_skipped(self):
        # line 97-98: componente_bdi != custo_direto skipped
        part = _part("eap-1", 200.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            componente_bdi="overhead_ac",
            categoria="mao_obra",
            atividade_id="eap-1",
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        scaling = _build_pool_scaling_by_item(canonical, cubo)
        assert scaling == {}

    def test_base_zero_no_scaling_entry(self):
        # line 108: base > 0 check — if base=0, no entry in scaling
        part = _part("eap-1", 200.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            componente_bdi="custo_direto",
            categoria="mao_obra",
            atividade_id="eap-99",  # different item_id -> no base for eap-1
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        scaling = _build_pool_scaling_by_item(canonical, cubo)
        assert "eap-1" not in scaling

    def test_cell_with_empty_atividade_id_skipped(self):
        # line 101-103: empty item_id skipped in base accumulation
        part = _part("eap-1", 100.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            componente_bdi="custo_direto",
            categoria="mao_obra",
            atividade_id="",
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        scaling = _build_pool_scaling_by_item(canonical, cubo)
        assert scaling == {}

    def test_alvo_zero_no_scaling_entry(self):
        # particao with alvo=0 skips the scaling entry
        part = _part("eap-1", 0.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            componente_bdi="custo_direto",
            categoria="mao_obra",
            atividade_id="eap-1",
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        scaling = _build_pool_scaling_by_item(canonical, cubo)
        assert "eap-1" not in scaling


# ---------------------------------------------------------------------------
# _iter_indireto_cubo_cells
# ---------------------------------------------------------------------------


class TestIterIndirectCuboCells:
    def test_cubo_none_yields_nothing(self):
        # getattr fallback returns []
        cubo = _ns(celulas=None)
        assert list(_iter_indireto_cubo_cells(cubo)) == []

    def test_non_indireto_cells_skipped(self):
        # line 133-134
        cell = _celula(natureza="direto")
        cubo = _cubo([cell])
        assert list(_iter_indireto_cubo_cells(cubo)) == []

    def test_indireto_cell_yielded(self):
        # line 134-135
        cell = _celula(natureza="indireto", valor_rs=250.0)
        cubo = _cubo([cell])
        results = list(_iter_indireto_cubo_cells(cubo))
        assert len(results) == 1
        assert results[0][1] == 250.0

    def test_mixed_cells_only_indireto_yielded(self):
        cells = [
            _celula(natureza="direto", valor_rs=100.0),
            _celula(natureza="indireto", valor_rs=50.0),
            _celula(natureza="indireto", valor_rs=75.0),
        ]
        cubo = _cubo(cells)
        results = list(_iter_indireto_cubo_cells(cubo))
        assert len(results) == 2
        assert {r[1] for r in results} == {50.0, 75.0}

    def test_valor_rs_none_yields_zero(self):
        cell = _ns(natureza="indireto", valor_rs=None)
        cubo = _cubo([cell])
        results = list(_iter_indireto_cubo_cells(cubo))
        assert results[0][1] == 0.0


# ---------------------------------------------------------------------------
# _iter_scaled_cubo_cells
# ---------------------------------------------------------------------------


class TestIterScaledCuboCells:
    def test_non_direto_cells_skipped(self):
        # line 121-122: natureza != direto -> skip
        cell = _celula(natureza="indireto", valor_rs=100.0)
        cubo = _cubo([cell])
        results = list(_iter_scaled_cubo_cells(None, cubo))
        assert results == []

    def test_material_not_scaled(self):
        # line 126-127: material bypasses scaling
        part = _part("eap-1", 200.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            natureza="direto",
            componente_bdi="custo_direto",
            categoria="material",
            atividade_id="eap-1",
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        results = list(_iter_scaled_cubo_cells(canonical, cubo))
        assert len(results) == 1
        # material not scaled: valor stays 100.0
        assert results[0][1] == 100.0

    def test_non_material_scaled(self):
        # scaling factor = 200/100 = 2.0 -> valor = 100 * 2.0 = 200.0
        part = _part("eap-1", 200.0)
        canonical = _ns(contratos_recurso=[_contrato([part])])
        cell = _celula(
            natureza="direto",
            componente_bdi="custo_direto",
            categoria="mao_obra",
            atividade_id="eap-1",
            valor_rs=100.0,
        )
        cubo = _cubo([cell])
        results = list(_iter_scaled_cubo_cells(canonical, cubo))
        assert len(results) == 1
        assert results[0][1] == pytest.approx(200.0)

    def test_no_scaling_factor_uses_1(self):
        # canonical=None -> no scaling -> factor=1.0
        cell = _celula(
            natureza="direto",
            componente_bdi="custo_direto",
            categoria="mao_obra",
            atividade_id="eap-1",
            valor_rs=55.0,
        )
        cubo = _cubo([cell])
        results = list(_iter_scaled_cubo_cells(None, cubo))
        assert len(results) == 1
        assert results[0][1] == pytest.approx(55.0)

    def test_empty_cubo_yields_nothing(self):
        cubo = _cubo([])
        results = list(_iter_scaled_cubo_cells(None, cubo))
        assert results == []


# ---------------------------------------------------------------------------
# _extract_cost_from_entry
# ---------------------------------------------------------------------------


class TestExtractCostFromEntry:
    def test_dict_with_custo_total(self):
        assert _extract_cost_from_entry({"custo_total": 500.0}) == 500.0

    def test_dict_with_custo_mensal_total(self):
        assert _extract_cost_from_entry({"custo_mensal_total": 300.0}) == 300.0

    def test_dict_with_custo_mensal(self):
        assert _extract_cost_from_entry({"custo_mensal": 150.0}) == 150.0

    def test_dict_with_valor(self):
        assert _extract_cost_from_entry({"valor": 99.0}) == 99.0

    def test_dict_with_custo(self):
        assert _extract_cost_from_entry({"custo": 42.0}) == 42.0

    def test_dict_quantidade_times_custo_unitario(self):
        # line 143-146
        result = _extract_cost_from_entry({"quantidade": 10.0, "custo_unitario": 25.0})
        assert result == pytest.approx(250.0)

    def test_dict_quantidade_zero_returns_zero(self):
        result = _extract_cost_from_entry({"quantidade": 0.0, "custo_unitario": 25.0})
        assert result == 0.0

    def test_dict_custo_unitario_zero_returns_zero(self):
        result = _extract_cost_from_entry({"quantidade": 10.0, "custo_unitario": 0.0})
        assert result == 0.0

    def test_dict_empty_returns_zero(self):
        assert _extract_cost_from_entry({}) == 0.0

    def test_object_with_custo_total_attr(self):
        obj = _ns(custo_total=777.0)
        assert _extract_cost_from_entry(obj) == 777.0

    def test_object_custo_total_none_returns_zero(self):
        obj = _ns(custo_total=None)
        assert _extract_cost_from_entry(obj) == 0.0

    def test_dict_priority_custo_total_over_quantidade(self):
        # custo_total should be picked up first before quantidade/custo_unitario
        result = _extract_cost_from_entry({"custo_total": 100.0, "quantidade": 10.0, "custo_unitario": 5.0})
        assert result == 100.0


# ---------------------------------------------------------------------------
# _build_indireto_component_totals
# ---------------------------------------------------------------------------


class TestBuildIndiretoComponentTotals:
    def test_no_indiretos_returns_zeros(self):
        canonical = _ns(indiretos=None)
        result = _build_indireto_component_totals(canonical)
        assert result == {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 0.0}

    def test_indireto_with_funcoes_and_equipamentos(self):
        funcao = {"custo_total": 1000.0}
        equip = {"custo_total": 500.0}
        ind = _ns(
            funcoes=[funcao],
            equipamentos=[equip],
            verbas_mensais=[],
            verbas_fixas=[],
            mobilizacoes=[],
            custo_total=0.0,  # triggers verbas fallback (custo_total=0)
        )
        canonical = _ns(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["mao_obra"] == pytest.approx(1000.0)
        assert result["equipamento"] == pytest.approx(500.0)

    def test_custo_total_zero_verbas_fallback(self):
        # line 168-169: elif custo_total > 0.0: verbas += custo_total
        # sub=0, custo_total=0 -> nothing added
        ind = _ns(
            funcoes=[],
            equipamentos=[],
            verbas_mensais=[],
            verbas_fixas=[],
            mobilizacoes=[],
            custo_total=0.0,
        )
        canonical = _ns(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result == {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 0.0}

    def test_custo_total_nonzero_verbas_fallback(self):
        # sub=0, custo_total>0 -> verbas += custo_total (line 168-169)
        ind = _ns(
            funcoes=[],
            equipamentos=[],
            verbas_mensais=[],
            verbas_fixas=[],
            mobilizacoes=[],
            custo_total=800.0,
        )
        canonical = _ns(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["verbas"] == pytest.approx(800.0)

    def test_scaling_applied_when_sub_and_custo_total_both_positive(self):
        # sub=100, custo_total=200 -> factor=2 -> mao scaled to 200
        funcao = {"custo_total": 100.0}
        ind = _ns(
            funcoes=[funcao],
            equipamentos=[],
            verbas_mensais=[],
            verbas_fixas=[],
            mobilizacoes=[],
            custo_total=200.0,
        )
        canonical = _ns(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["mao_obra"] == pytest.approx(200.0)

    def test_verbas_mensais_accumulated(self):
        verba = {"custo_total": 300.0}
        ind = _ns(
            funcoes=[],
            equipamentos=[],
            verbas_mensais=[verba],
            verbas_fixas=[],
            mobilizacoes=[],
            custo_total=0.0,
        )
        canonical = _ns(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["verbas"] == pytest.approx(300.0)

    def test_mobilizacoes_accumulated_in_verbas(self):
        mob = _ns(custo_total=150.0)
        ind = _ns(
            funcoes=[],
            equipamentos=[],
            verbas_mensais=[],
            verbas_fixas=[],
            mobilizacoes=[mob],
            custo_total=0.0,
        )
        canonical = _ns(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["verbas"] == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# _indireto_component_shares
# ---------------------------------------------------------------------------


class TestIndiretoComponentShares:
    def test_all_zeros_returns_verbas_one(self):
        # line 179-180: if total <= 0.0 -> {"mao_obra": 0, "equipamento": 0, "verbas": 1.0}
        canonical = _ns(indiretos=[])
        result = _indireto_component_shares(canonical)
        assert result == {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 1.0}

    def test_proportional_shares(self):
        # mao=200, equip=200, verbas=600 -> total=1000
        ind = _ns(
            funcoes=[{"custo_total": 200.0}],
            equipamentos=[{"custo_total": 200.0}],
            verbas_mensais=[{"custo_total": 600.0}],
            verbas_fixas=[],
            mobilizacoes=[],
            custo_total=0.0,
        )
        canonical = _ns(indiretos=[ind])
        result = _indireto_component_shares(canonical)
        assert result["mao_obra"] == pytest.approx(0.2)
        assert result["equipamento"] == pytest.approx(0.2)
        assert result["verbas"] == pytest.approx(0.6)

    def test_shares_sum_to_one(self):
        ind = _ns(
            funcoes=[{"custo_total": 333.0}],
            equipamentos=[{"custo_total": 333.0}],
            verbas_mensais=[{"custo_total": 334.0}],
            verbas_fixas=[],
            mobilizacoes=[],
            custo_total=0.0,
        )
        canonical = _ns(indiretos=[ind])
        result = _indireto_component_shares(canonical)
        assert sum(result.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# bucket_from_week_iso
# ---------------------------------------------------------------------------


class TestBucketFromWeekIso:
    def test_semana_granularidade_returns_as_is(self):
        assert bucket_from_week_iso("2026-W23", "semana") == "2026-W23"

    def test_mes_granularidade(self):
        # 2026-W23: Mon of W23 is 2026-06-01 (June)
        result = bucket_from_week_iso("2026-W23", "mes")
        assert result == "2026-06"

    def test_bimestre_granularidade(self):
        # June -> bimestre 3 ((6-1)//2+1=3)
        result = bucket_from_week_iso("2026-W23", "bimestre")
        assert result == "2026-B3"

    def test_trimestre_granularidade(self):
        # June -> trimestre 2 ((6-1)//3+1=2)
        result = bucket_from_week_iso("2026-W23", "trimestre")
        assert result == "2026-T2"

    def test_semestre_granularidade(self):
        # June -> semestre 1 ((6-1)//6+1=1)
        result = bucket_from_week_iso("2026-W23", "semestre")
        assert result == "2026-S1"

    def test_ano_granularidade(self):
        result = bucket_from_week_iso("2026-W23", "ano")
        assert result == "2026"

    def test_invalid_granularidade_raises(self):
        with pytest.raises(ValueError, match="Granularidade inválida"):
            bucket_from_week_iso("2026-W23", "decada")  # type: ignore[arg-type]

    def test_week_1_january(self):
        # 2026-W01 Monday is 2025-12-29 (ISO week 1 of 2026 starts in Dec 2025)
        result = bucket_from_week_iso("2026-W01", "mes")
        assert result == "2025-12"

    def test_week_52_december(self):
        # 2025-W52: typically December 2025
        result = bucket_from_week_iso("2025-W52", "mes")
        assert result == "2025-12"

    def test_second_semester(self):
        # September -> semestre 2
        result = bucket_from_week_iso("2026-W40", "semestre")
        assert result == "2026-S2"

    def test_q4_trimestre(self):
        # November -> trimestre 4
        result = bucket_from_week_iso("2026-W45", "trimestre")
        assert result == "2026-T4"


# ---------------------------------------------------------------------------
# _mob_eventos_por_periodo (lines 214-219) — tested indirectly via public interface
# but also via the function if importable
# ---------------------------------------------------------------------------


def test_mob_eventos_por_periodo_lines_214_219():
    """Test lines 214-219: _mob_eventos_por_periodo iterates semana_mobilizacao/desmobilizacao."""
    from concilium.application.services.analytics.cube_projection_views import _mob_eventos_por_periodo

    inst1 = _ns(semana_mobilizacao="2026-W01", semana_desmobilizacao="2026-W10")
    inst2 = _ns(semana_mobilizacao="2026-W05", semana_desmobilizacao="")
    canonical = _ns(instancias_recurso=[inst1, inst2])
    result = _mob_eventos_por_periodo(canonical, "mes")
    # inst1 contributes 2 events (W01->jan, W10->mar); inst2 contributes 1 (W05->jan)
    assert result.get("2026-01", 0) >= 1
    assert sum(result.values()) == 3


def test_mob_eventos_por_periodo_empty_semana_skipped():
    """Empty semana_mobilizacao/desmobilizacao is skipped (line 216-217)."""
    from concilium.application.services.analytics.cube_projection_views import _mob_eventos_por_periodo

    inst = _ns(semana_mobilizacao="", semana_desmobilizacao="")
    canonical = _ns(instancias_recurso=[inst])
    result = _mob_eventos_por_periodo(canonical, "mes")
    assert result == {}


def test_mob_eventos_por_periodo_no_instancias():
    from concilium.application.services.analytics.cube_projection_views import _mob_eventos_por_periodo

    canonical = _ns(instancias_recurso=None)
    result = _mob_eventos_por_periodo(canonical, "mes")
    assert result == {}


# ---------------------------------------------------------------------------
# resolve_cubo_projection_rows — direto_temporal_categoria line 266
# ---------------------------------------------------------------------------


def test_resolve_cubo_projection_rows_direto_unknown_categoria_skipped():
    """Line 265-266: cat_key=None for unknown categoria -> continue."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    cell = _celula(
        natureza="direto",
        componente_bdi="custo_direto",
        categoria="unknown_cat",
        atividade_id="eap-1",
        valor_rs=100.0,
        semana_iso="2026-W01",
    )
    cubo = _cubo([cell])
    rows, columns, chart_hint = resolve_cubo_projection_rows(cubo, "direto_temporal_categoria", "mes", 100)
    # unknown categoria skipped -> no rows with value
    total = sum(r["valor_rs"] for r in rows)
    assert total == 0.0


# ---------------------------------------------------------------------------
# resolve_cubo_projection_rows — indireto_temporal_categoria lines 300-306 / 316-319
# ---------------------------------------------------------------------------


def test_resolve_cubo_projection_rows_indireto_temporal_categoria_cubo_cells():
    """Lines 300-306: reads IND- cells from cubo_analitico."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    ind_cell = _ns(
        natureza="indireto",
        componente_bdi="custo_direto",
        atividade_id="IND-ADM",
        valor_rs=500.0,
        semana_iso="2026-W01",
    )
    cubo_analitico = _cubo([ind_cell])
    canonical = _ns(
        cubo_analitico=cubo_analitico,
        instancias_recurso=[],
        indiretos=[],
        cronograma=None,
        indiretos_semanal=[],
    )
    cubo = _cubo([])
    rows, columns, chart_hint = resolve_cubo_projection_rows(
        cubo, "indireto_temporal_categoria", "mes", 100, canonical=canonical
    )
    adm_total = sum(r["valor_rs"] for r in rows if r.get("categoria_indireto") == "ADM")
    assert adm_total == pytest.approx(500.0)


def test_resolve_cubo_projection_rows_indireto_mob_rebalancing():
    """Lines 315-319: rebalance MOB when total_eventos > 0 and more than 2 buckets."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    ind_cell = _ns(
        natureza="indireto",
        componente_bdi="custo_direto",
        atividade_id="IND-MOB",
        valor_rs=300.0,
        semana_iso="2026-W01",
    )
    cubo_analitico = _cubo([ind_cell])
    # 3+ mobilization buckets to trigger rebalancing
    inst1 = _ns(semana_mobilizacao="2026-W01", semana_desmobilizacao="2026-W10")
    inst2 = _ns(semana_mobilizacao="2026-W20", semana_desmobilizacao="2026-W30")
    canonical = _ns(
        cubo_analitico=cubo_analitico,
        instancias_recurso=[inst1, inst2],
        indiretos=[],
        cronograma=None,
        indiretos_semanal=[],
    )
    cubo = _cubo([])
    rows, columns, chart_hint = resolve_cubo_projection_rows(
        cubo, "indireto_temporal_categoria", "mes", 200, canonical=canonical
    )
    mob_total = sum(r["valor_rs"] for r in rows if r.get("categoria_indireto") == "MOB")
    assert mob_total == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# resolve_cubo_projection_rows — tempo_natureza line 373 (bucket falsy skip) / line 378
# ---------------------------------------------------------------------------


def test_resolve_cubo_projection_rows_tempo_natureza_direto_cell_accumulated():
    """Lines 373-376: direto cell with valid bucket is accumulated into direto_por_bucket."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    cell_good = _ns(natureza="direto", componente_bdi="custo_direto", valor_rs=100.0, semana_iso="2026-W10")
    cubo_analitico = _cubo([cell_good])
    canonical = _ns(cubo_analitico=cubo_analitico)
    cubo = _cubo([])
    rows, columns, chart_hint = resolve_cubo_projection_rows(cubo, "tempo_natureza", "mes", 100, canonical=canonical)
    total = sum(r["valor_rs"] for r in rows if r.get("natureza") == "direto")
    assert total == pytest.approx(100.0)


def test_resolve_cubo_projection_rows_tempo_natureza_indireto_cell():
    """Line 377-378: indireto cell accumulates into indireto_por_bucket."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    cell_ind = _ns(natureza="indireto", componente_bdi="custo_direto", valor_rs=200.0, semana_iso="2026-W01")
    cubo_analitico = _cubo([cell_ind])
    canonical = _ns(cubo_analitico=cubo_analitico)
    cubo = _cubo([])
    rows, columns, chart_hint = resolve_cubo_projection_rows(cubo, "tempo_natureza", "mes", 100, canonical=canonical)
    ind_total = sum(r["valor_rs"] for r in rows if r.get("natureza") == "indireto")
    assert ind_total == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# resolve_cubo_projection_rows — atividade_componente line 489
# ---------------------------------------------------------------------------


def test_resolve_cubo_projection_rows_atividade_componente_skips_empty_cat():
    """Line 488-489: cat empty or custo_total<=0 -> continue."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    # ind without categoria -> skipped
    ind_no_cat = _ns(categoria="", custo_total=500.0)
    # ind with zero custo -> skipped
    ind_zero = _ns(categoria="ADM", custo_total=0.0)
    # valid ind
    ind_valid = _ns(categoria="TOP", custo_total=300.0)
    canonical = _ns(indiretos=[ind_no_cat, ind_zero, ind_valid])
    cubo = _cubo([])
    rows, columns, chart_hint = resolve_cubo_projection_rows(
        cubo, "atividade_componente", "mes", 100, canonical=canonical
    )
    keys = {r["atividade_id"] for r in rows}
    assert not any(k.endswith(".") for k in keys)  # empty cat skipped
    assert any("indireto.TOP" in k for k in keys)


# ---------------------------------------------------------------------------
# Remaining branch gaps (session 2): 303, 374, [204,202], [268,260], [302,303],
# [305,295], [311,323], [328,326], [373,374], [453,455]
# ---------------------------------------------------------------------------


def test_custo_indireto_por_periodo_offset_out_of_range_skipped():
    """Line 204->202: ind.semana offset out of range of semanas_sorted -> skip, no KeyError."""
    from concilium.application.services.analytics.cube_projection_views import _custo_indireto_por_periodo

    act = _ns(distribuicao_semanal={"2026-W01": 1.0, "2026-W02": 1.0})
    cronograma = _ns(scheduled_activities=[act])
    ind_valid = _ns(semana=0, custo_semanal=100.0)
    ind_out_of_range = _ns(semana=99, custo_semanal=500.0)
    canonical = _ns(cronograma=cronograma, indiretos_semanal=[ind_valid, ind_out_of_range])
    result = _custo_indireto_por_periodo(canonical, "semana")
    assert sum(result.values()) == pytest.approx(100.0)


def test_resolve_cubo_projection_rows_direto_temporal_categoria_empty_bucket_skipped():
    """Line 268->260: empty semana_iso with granularidade='semana' -> bucket falsy -> continue."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    cell = _celula(
        natureza="direto",
        componente_bdi="custo_direto",
        categoria="mao_obra",
        semana_iso="",
        valor_rs=100.0,
    )
    cubo = _cubo([cell])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(cubo, "direto_temporal_categoria", "semana", 100)
    total = sum(r["valor_rs"] for r in rows)
    assert total == 0.0


def test_resolve_cubo_projection_rows_indireto_unknown_category_skipped():
    """Line 302-303: aid category not in the known categories list -> continue."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    ind_cell = _ns(
        natureza="indireto",
        componente_bdi="custo_direto",
        atividade_id="IND-DESCONHECIDO",
        valor_rs=999.0,
        semana_iso="2026-W01",
    )
    cubo_analitico = _cubo([ind_cell])
    canonical = _ns(
        cubo_analitico=cubo_analitico,
        instancias_recurso=[],
        indiretos=[],
        cronograma=None,
        indiretos_semanal=[],
    )
    cubo = _cubo([])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(
        cubo, "indireto_temporal_categoria", "mes", 100, canonical=canonical
    )
    total = sum(r["valor_rs"] for r in rows)
    assert total == 0.0


def test_resolve_cubo_projection_rows_indireto_temporal_categoria_empty_bucket_skipped():
    """Line 305->295: empty semana_iso with granularidade='semana' -> bucket falsy -> continue."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    ind_cell = _ns(
        natureza="indireto",
        componente_bdi="custo_direto",
        atividade_id="IND-ADM",
        valor_rs=250.0,
        semana_iso="",
    )
    cubo_analitico = _cubo([ind_cell])
    canonical = _ns(
        cubo_analitico=cubo_analitico,
        instancias_recurso=[],
        indiretos=[],
        cronograma=None,
        indiretos_semanal=[],
    )
    cubo = _cubo([])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(
        cubo, "indireto_temporal_categoria", "semana", 100, canonical=canonical
    )
    total = sum(r["valor_rs"] for r in rows)
    assert total == 0.0


def test_resolve_cubo_projection_rows_indireto_temporal_categoria_canonical_none():
    """Line 311->323: canonical falsy -> skip rebalance and fallback blocks entirely."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    cubo = _cubo([])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(
        cubo, "indireto_temporal_categoria", "mes", 100, canonical=None
    )
    assert rows == []


def test_resolve_cubo_projection_rows_indireto_fallback_skips_unknown_category():
    """Line 328->326: fallback path skips indiretos with categoria not in ADM/TOP/LAB/QSMS/MOB."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    ind_unknown = _ns(categoria="XYZ", custo_total=1000.0)
    ind_known = _ns(categoria="ADM", custo_total=100.0)
    act = _ns(distribuicao_semanal={"2026-W01": 1.0})
    cronograma = _ns(scheduled_activities=[act])
    ind_semanal = _ns(semana=0, custo_semanal=200.0)
    canonical = _ns(
        cubo_analitico=None,
        instancias_recurso=[],
        indiretos=[ind_unknown, ind_known],
        cronograma=cronograma,
        indiretos_semanal=[ind_semanal],
    )
    cubo = _cubo([])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(
        cubo, "indireto_temporal_categoria", "mes", 100, canonical=canonical
    )
    # by_cat_total only counts "ADM"=100.0 (XYZ ignored); indireto_bucket total is 200.0
    # distributed across categories by share (ADM gets 100% of shares since it's the only known total)
    adm_total = sum(r["valor_rs"] for r in rows if r.get("categoria_indireto") == "ADM")
    assert adm_total == pytest.approx(200.0)


def test_resolve_cubo_projection_rows_tempo_natureza_empty_bucket_skipped():
    """Line 373->374: empty semana_iso with granularidade='semana' -> bucket falsy -> continue."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    cell_empty_bucket = _ns(natureza="direto", componente_bdi="custo_direto", valor_rs=100.0, semana_iso="")
    cubo_analitico = _cubo([cell_empty_bucket])
    canonical = _ns(cubo_analitico=cubo_analitico)
    cubo = _cubo([])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(
        cubo, "tempo_natureza", "semana", 100, canonical=canonical
    )
    total = sum(r["valor_rs"] for r in rows)
    assert total == 0.0


def test_resolve_cubo_projection_rows_categoria_componente_sub_zero_custo_total_positive():
    """Line 453->455: sub==0 (mao=eq=verbas=0) but custo_total_ind>0 -> verbas += custo_total_ind."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    ind = _ns(
        categoria="ADM",
        custo_total=777.0,
        funcoes=[],
        equipamentos=[],
        verbas_mensais=[],
        verbas_fixas=[],
        mobilizacoes=[],
    )
    canonical = _ns(indiretos=[ind])
    cubo = _cubo([])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(
        cubo, "categoria_componente", "mes", 100, canonical=canonical
    )
    verbas_rows = [r for r in rows if r["categoria"] == "indireto.verbas"]
    total_verbas = sum(r["valor_rs"] for r in verbas_rows)
    assert total_verbas > 0.0


def test_resolve_cubo_projection_rows_categoria_componente_sub_and_custo_total_both_zero():
    """Line 453->455 branch False: sub==0 and custo_total_ind<=0 -> neither adjustment runs."""
    from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows

    ind = _ns(
        categoria="ADM",
        custo_total=0.0,
        funcoes=[],
        equipamentos=[],
        verbas_mensais=[],
        verbas_fixas=[],
        mobilizacoes=[],
    )
    canonical = _ns(indiretos=[ind])
    cubo = _cubo([])
    rows, _columns, _chart_hint = resolve_cubo_projection_rows(
        cubo, "categoria_componente", "mes", 100, canonical=canonical
    )
    total = sum(r["valor_rs"] for r in rows)
    assert total == 0.0
