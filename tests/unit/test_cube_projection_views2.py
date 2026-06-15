"""Comprehensive tests for cube_projection_views.py — boost coverage from 60% to 80%+.

Covers:
  - bucket_from_week_iso: all six FaceGranularity values + invalid raises ValueError
  - _normalize_bdi_component: overhead, tributo, margem_l, custo_direto/indireto, unknown
  - _build_bdi_multipliers_from_cubo: normal case + zero-base guard
  - _split_operational_cost_with_bdi: normal decomposition
  - _build_indireto_component_totals: factor scaling + custo_total fallback
  - _indireto_component_shares: normal + zero total guard
  - resolve_cubo_projection_rows: tempo_componente, categoria_componente,
      atividade_componente, diesel_temporal, tempo_natureza, invalid face
  - resolve_abc_curva_rows: class A/B/C classification, operator_meta keys
  - resolve_s_curve_rows: row structure, pct_acumulado, zero total_projeto guard
  - resolve_recursos_ativos_rows: row structure, operator_meta keys
  - build_cube_projection_payload: routing to each branch, returned dict keys
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from concilium.application.services.analytics.cube_projection_views import (
    FACE_UNIT_TYPES,
    _build_bdi_multipliers_from_cubo,
    _build_indireto_component_totals,
    _indireto_component_shares,
    _normalize_bdi_component,
    _split_operational_cost_with_bdi,
    bucket_from_week_iso,
    build_cube_projection_payload,
    resolve_abc_curva_rows,
    resolve_cubo_projection_rows,
    resolve_recursos_ativos_rows,
    resolve_s_curve_rows,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_celula(
    atividade_id: str = "ATV-001",
    categoria: str = "mao_obra",
    semana_iso: str = "2026-W10",
    componente_bdi: str = "custo_direto",
    valor_rs: float = 100.0,
    consumo_diesel_L: float = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        atividade_id=atividade_id,
        categoria=categoria,
        semana_iso=semana_iso,
        componente_bdi=componente_bdi,
        valor_rs=valor_rs,
        consumo_diesel_L=consumo_diesel_L,
    )


def _make_cubo(*celulas: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(celulas=list(celulas))


def _make_canonical(indiretos=None, indiretos_semanal=None, cronograma=None) -> SimpleNamespace:
    return SimpleNamespace(
        indiretos=indiretos or [],
        indiretos_semanal=indiretos_semanal or [],
        cronograma=cronograma,
        contratos_recurso=[],
    )


# ===========================================================================
# bucket_from_week_iso
# ===========================================================================


class TestBucketFromWeekIso:
    """All six FaceGranularity variants and an invalid value."""

    WEEK = "2026-W10"  # anchor = 2026-03-02 (Monday)

    def test_semana(self):
        assert bucket_from_week_iso(self.WEEK, "semana") == self.WEEK

    def test_mes(self):
        assert bucket_from_week_iso(self.WEEK, "mes") == "2026-03"

    def test_bimestre(self):
        # March = month 3 -> bimestre = ((3-1)//2)+1 = 2
        assert bucket_from_week_iso(self.WEEK, "bimestre") == "2026-B2"

    def test_trimestre(self):
        # March = month 3 -> trimestre = ((3-1)//3)+1 = 1
        assert bucket_from_week_iso(self.WEEK, "trimestre") == "2026-T1"

    def test_semestre(self):
        # March = month 3 -> semestre = ((3-1)//6)+1 = 1
        assert bucket_from_week_iso(self.WEEK, "semestre") == "2026-S1"

    def test_ano(self):
        assert bucket_from_week_iso(self.WEEK, "ano") == "2026"

    def test_invalid_granularidade_raises(self):
        with pytest.raises((ValueError, TypeError)):
            bucket_from_week_iso(self.WEEK, "decada")  # type: ignore[arg-type]

    def test_july_week_bimestre(self):
        # 2026-W29 → 2026-07-13 → bimestre ((7-1)//2)+1 = 4
        assert bucket_from_week_iso("2026-W29", "bimestre") == "2026-B4"

    def test_july_week_semestre(self):
        # July = month 7 → semestre ((7-1)//6)+1 = 2
        assert bucket_from_week_iso("2026-W29", "semestre") == "2026-S2"

    def test_q4_trimestre(self):
        # 2026-W44 → 2026-10-26 → trimestre ((10-1)//3)+1 = 4
        assert bucket_from_week_iso("2026-W44", "trimestre") == "2026-T4"


# ===========================================================================
# _normalize_bdi_component
# ===========================================================================


class TestNormalizeBdiComponent:
    def test_overhead_ac(self):
        assert _normalize_bdi_component("overhead_ac") == "Overhead BDI"

    def test_overhead_df(self):
        assert _normalize_bdi_component("overhead_df") == "Overhead BDI"

    def test_overhead_r(self):
        assert _normalize_bdi_component("overhead_r") == "Overhead BDI"

    def test_overhead_cr(self):
        assert _normalize_bdi_component("overhead_cr") == "Overhead BDI"

    def test_tributo_cofins(self):
        assert _normalize_bdi_component("tributo_cofins") == "Tributos"

    def test_tributo_iss(self):
        assert _normalize_bdi_component("tributo_iss") == "Tributos"

    def test_tributo_pis(self):
        assert _normalize_bdi_component("tributo_pis") == "Tributos"

    def test_tributo_cssl(self):
        assert _normalize_bdi_component("tributo_cssl") == "Tributos"

    def test_tributo_ir(self):
        assert _normalize_bdi_component("tributo_ir") == "Tributos"

    def test_margem_l(self):
        assert _normalize_bdi_component("margem_l") == "Lucro (L)"

    def test_custo_direto(self):
        assert _normalize_bdi_component("custo_direto") == "Custo operacional"

    def test_custo_indireto(self):
        assert _normalize_bdi_component("custo_indireto") == "Custo operacional"

    def test_unknown_passthrough(self):
        assert _normalize_bdi_component("alguma_coisa_estranha") == "alguma_coisa_estranha"


# ===========================================================================
# _build_bdi_multipliers_from_cubo
# ===========================================================================


class TestBuildBdiMultipliersFromCubo:
    def _make_cubo_with_bdi(self) -> SimpleNamespace:
        """custo_operacional=100, overhead=10, lucro=20, tributos=15."""
        return _make_cubo(
            _make_celula(componente_bdi="custo_direto", valor_rs=100.0),
            _make_celula(componente_bdi="overhead_ac", valor_rs=10.0),
            _make_celula(componente_bdi="margem_l", valor_rs=20.0),
            _make_celula(componente_bdi="tributo_iss", valor_rs=15.0),
        )

    def test_multipliers_are_ratios(self):
        result = _build_bdi_multipliers_from_cubo(self._make_cubo_with_bdi())
        assert result["Overhead BDI"] == pytest.approx(0.10)
        assert result["Lucro (L)"] == pytest.approx(0.20)
        assert result["Tributos"] == pytest.approx(0.15)

    def test_zero_base_returns_zeros(self):
        cubo = _make_cubo()  # no celulas
        result = _build_bdi_multipliers_from_cubo(cubo)
        assert result == {"Overhead BDI": 0.0, "Lucro (L)": 0.0, "Tributos": 0.0}

    def test_none_celulas_returns_zeros(self):
        cubo = SimpleNamespace(celulas=None)
        result = _build_bdi_multipliers_from_cubo(cubo)
        assert result == {"Overhead BDI": 0.0, "Lucro (L)": 0.0, "Tributos": 0.0}

    def test_valor_rs_none_treated_as_zero(self):
        cubo = _make_cubo(
            SimpleNamespace(
                atividade_id="A",
                categoria="mao_obra",
                semana_iso="2026-W01",
                componente_bdi="custo_direto",
                valor_rs=None,
                consumo_diesel_L=0.0,
            )
        )
        result = _build_bdi_multipliers_from_cubo(cubo)
        assert result == {"Overhead BDI": 0.0, "Lucro (L)": 0.0, "Tributos": 0.0}

    def test_overhead_aggregates_multiple_components(self):
        cubo = _make_cubo(
            _make_celula(componente_bdi="custo_direto", valor_rs=100.0),
            _make_celula(componente_bdi="overhead_ac", valor_rs=5.0),
            _make_celula(componente_bdi="overhead_df", valor_rs=5.0),
        )
        result = _build_bdi_multipliers_from_cubo(cubo)
        assert result["Overhead BDI"] == pytest.approx(0.10)


# ===========================================================================
# _split_operational_cost_with_bdi
# ===========================================================================


class TestSplitOperationalCostWithBdi:
    def test_proportional_split(self):
        multipliers = {"Overhead BDI": 0.10, "Lucro (L)": 0.20, "Tributos": 0.15}
        result = _split_operational_cost_with_bdi(100.0, multipliers)
        assert result["Custo operacional"] == pytest.approx(100.0)
        assert result["Overhead BDI"] == pytest.approx(10.0)
        assert result["Lucro (L)"] == pytest.approx(20.0)
        assert result["Tributos"] == pytest.approx(15.0)

    def test_zero_base_cost(self):
        multipliers = {"Overhead BDI": 0.10, "Lucro (L)": 0.20, "Tributos": 0.15}
        result = _split_operational_cost_with_bdi(0.0, multipliers)
        for v in result.values():
            assert v == 0.0

    def test_none_base_cost_treated_as_zero(self):
        multipliers = {"Overhead BDI": 0.10, "Lucro (L)": 0.20, "Tributos": 0.15}
        result = _split_operational_cost_with_bdi(None, multipliers)  # type: ignore[arg-type]
        assert result["Custo operacional"] == 0.0

    def test_missing_multiplier_keys_default_to_zero(self):
        result = _split_operational_cost_with_bdi(100.0, {})
        assert result["Overhead BDI"] == 0.0
        assert result["Lucro (L)"] == 0.0
        assert result["Tributos"] == 0.0


# ===========================================================================
# _build_indireto_component_totals
# ===========================================================================


class TestBuildIndiretoComponentTotals:
    def _make_ind(self, custo_total=100.0, funcoes=None, equipamentos=None, verbas_mensais=None,
                  verbas_fixas=None, mobilizacoes=None):
        return SimpleNamespace(
            custo_total=custo_total,
            funcoes=funcoes or [],
            equipamentos=equipamentos or [],
            verbas_mensais=verbas_mensais or [],
            verbas_fixas=verbas_fixas or [],
            mobilizacoes=mobilizacoes or [],
        )

    def test_empty_indiretos(self):
        canonical = _make_canonical(indiretos=[])
        result = _build_indireto_component_totals(canonical)
        assert result == {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 0.0}

    def test_none_indiretos(self):
        canonical = SimpleNamespace(indiretos=None)
        result = _build_indireto_component_totals(canonical)
        assert result == {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 0.0}

    def test_proportional_scaling(self):
        """When sub=50 but custo_total=100, factor=2 is applied."""
        ind = self._make_ind(
            custo_total=100.0,
            funcoes=[{"custo_total": 20.0}],
            equipamentos=[{"custo_total": 10.0}],
            verbas_mensais=[{"custo_total": 20.0}],
        )
        canonical = _make_canonical(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        # sub=50, factor=2: mao=40, eq=20, verbas=40
        assert result["mao_obra"] == pytest.approx(40.0)
        assert result["equipamento"] == pytest.approx(20.0)
        assert result["verbas"] == pytest.approx(40.0)

    def test_custo_total_fallback_to_verbas_when_sub_zero(self):
        """When no sub-items, custo_total is added to verbas."""
        ind = self._make_ind(custo_total=75.0)
        canonical = _make_canonical(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["verbas"] == pytest.approx(75.0)
        assert result["mao_obra"] == pytest.approx(0.0)
        assert result["equipamento"] == pytest.approx(0.0)

    def test_verbas_fixas_included(self):
        ind = self._make_ind(
            custo_total=30.0,
            verbas_fixas=[{"custo_total": 30.0}],
        )
        canonical = _make_canonical(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["verbas"] == pytest.approx(30.0)

    def test_mobilizacoes_added_to_verbas(self):
        mob = SimpleNamespace(custo_total=50.0)
        ind = self._make_ind(
            custo_total=50.0,
            mobilizacoes=[mob],
        )
        canonical = _make_canonical(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        # sub=50, custo_total=50, factor=1, so verbas=50
        assert result["verbas"] == pytest.approx(50.0)

    def test_dict_entry_with_quantidade_custo_unitario(self):
        """_extract_cost_from_entry handles qtd*unit when no cost keys."""
        ind = self._make_ind(
            custo_total=20.0,
            funcoes=[{"quantidade": 2.0, "custo_unitario": 10.0}],
        )
        canonical = _make_canonical(indiretos=[ind])
        result = _build_indireto_component_totals(canonical)
        assert result["mao_obra"] == pytest.approx(20.0)

    def test_multiple_indiretos_accumulated(self):
        ind1 = self._make_ind(custo_total=50.0)  # all to verbas
        ind2 = self._make_ind(custo_total=50.0)  # all to verbas
        canonical = _make_canonical(indiretos=[ind1, ind2])
        result = _build_indireto_component_totals(canonical)
        assert result["verbas"] == pytest.approx(100.0)


# ===========================================================================
# _indireto_component_shares
# ===========================================================================


class TestIndiretoComponentShares:
    def test_equal_split(self):
        ind = SimpleNamespace(
            custo_total=30.0,
            funcoes=[{"custo_total": 10.0}],
            equipamentos=[{"custo_total": 10.0}],
            verbas_mensais=[{"custo_total": 10.0}],
            verbas_fixas=[],
            mobilizacoes=[],
        )
        canonical = _make_canonical(indiretos=[ind])
        shares = _indireto_component_shares(canonical)
        assert shares["mao_obra"] == pytest.approx(1 / 3)
        assert shares["equipamento"] == pytest.approx(1 / 3)
        assert shares["verbas"] == pytest.approx(1 / 3)

    def test_zero_total_returns_verbas_one(self):
        canonical = _make_canonical(indiretos=[])
        shares = _indireto_component_shares(canonical)
        assert shares == {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 1.0}


# ===========================================================================
# resolve_cubo_projection_rows
# ===========================================================================


class TestResolveCuboProjectionRows:
    """Tests that do NOT need to import real domain services."""

    def _cubo_stub(self):
        return _make_cubo(
            _make_celula(componente_bdi="custo_direto", valor_rs=100.0),
            _make_celula(componente_bdi="overhead_ac", valor_rs=10.0),
            _make_celula(componente_bdi="margem_l", valor_rs=20.0),
            _make_celula(componente_bdi="tributo_iss", valor_rs=15.0),
        )

    # -- tempo_componente ------------------------------------------------

    def test_tempo_componente_returns_rows_with_expected_keys(self):
        rows, columns, chart_hint = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="tempo_componente",
            granularidade="mes",
            top_n=200,
            canonical=None,
        )
        assert chart_hint == "line"
        col_ids = {c["id"] for c in columns}
        assert col_ids == {"periodo", "componente_bdi", "valor_rs"}
        assert all("periodo" in r and "componente_bdi" in r and "valor_rs" in r for r in rows)

    def test_tempo_componente_aggregates_normalized_components(self):
        rows, _, _ = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="tempo_componente",
            granularidade="mes",
            top_n=200,
            canonical=None,
        )
        by_comp = {r["componente_bdi"]: r["valor_rs"] for r in rows}
        assert "Custo operacional" in by_comp
        assert "Overhead BDI" in by_comp
        assert "Lucro (L)" in by_comp
        assert "Tributos" in by_comp

    def test_tempo_componente_with_canonical_adds_indireto(self):
        canonical = _make_canonical(
            indiretos=[
                SimpleNamespace(
                    categoria="ADM",
                    custo_total=50.0,
                    funcoes=[],
                    equipamentos=[],
                    verbas_mensais=[],
                    verbas_fixas=[],
                    mobilizacoes=[],
                )
            ]
        )
        rows, _, _ = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="tempo_componente",
            granularidade="mes",
            top_n=200,
            canonical=canonical,
        )
        # At minimum direto rows exist
        assert len(rows) >= 4

    # -- categoria_componente --------------------------------------------

    def test_categoria_componente_chart_hint_is_heatmap(self):
        _, _, chart_hint = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="categoria_componente",
            granularidade="mes",
            top_n=200,
            canonical=None,
        )
        assert chart_hint == "heatmap"

    def test_categoria_componente_columns(self):
        _, columns, _ = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="categoria_componente",
            granularidade="mes",
            top_n=200,
            canonical=None,
        )
        col_ids = {c["id"] for c in columns}
        assert col_ids == {"categoria", "componente_bdi", "valor_rs"}

    def test_categoria_componente_top_n_limits_rows(self):
        rows, _, _ = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="categoria_componente",
            granularidade="mes",
            top_n=2,
            canonical=None,
        )
        assert len(rows) <= 2

    # -- atividade_componente --------------------------------------------

    def test_atividade_componente_chart_hint_is_heatmap(self):
        _, _, chart_hint = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="atividade_componente",
            granularidade="mes",
            top_n=200,
            canonical=None,
        )
        assert chart_hint == "heatmap"

    def test_atividade_componente_row_keys(self):
        rows, _, _ = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="atividade_componente",
            granularidade="mes",
            top_n=200,
            canonical=None,
        )
        assert all("atividade_id" in r and "componente_bdi" in r and "valor_rs" in r for r in rows)

    def test_atividade_componente_with_canonical_indiretos(self):
        canonical = _make_canonical(
            indiretos=[
                SimpleNamespace(
                    categoria="ADM",
                    custo_total=100.0,
                    funcoes=[],
                    equipamentos=[],
                    verbas_mensais=[],
                    verbas_fixas=[],
                    mobilizacoes=[],
                )
            ]
        )
        rows, _, _ = resolve_cubo_projection_rows(
            self._cubo_stub(),
            face="atividade_componente",
            granularidade="mes",
            top_n=200,
            canonical=canonical,
        )
        ids = [r["atividade_id"] for r in rows]
        assert any("indireto.ADM" in aid for aid in ids)

    # -- diesel_temporal --------------------------------------------------

    def test_diesel_temporal_chart_hint_is_bar_stacked(self):
        cubo = _make_cubo(
            _make_celula(
                atividade_id="ATV-D",
                categoria="equipamento",
                semana_iso="2026-W10",
                componente_bdi="custo_direto",
                valor_rs=0.0,
                consumo_diesel_L=500.0,
            )
        )
        _, _, chart_hint = resolve_cubo_projection_rows(
            cubo,
            face="diesel_temporal",
            granularidade="mes",
            top_n=200,
        )
        assert chart_hint == "bar_stacked"

    def test_diesel_temporal_columns(self):
        cubo = _make_cubo(
            _make_celula(consumo_diesel_L=500.0, semana_iso="2026-W10"),
        )
        _, columns, _ = resolve_cubo_projection_rows(
            cubo, face="diesel_temporal", granularidade="mes", top_n=200
        )
        col_ids = {c["id"] for c in columns}
        assert col_ids == {"periodo", "atividade_id", "consumo_diesel_l"}

    def test_diesel_temporal_zero_diesel_excluded(self):
        cubo = _make_cubo(
            _make_celula(consumo_diesel_L=0.0, semana_iso="2026-W10"),
        )
        rows, _, _ = resolve_cubo_projection_rows(
            cubo, face="diesel_temporal", granularidade="mes", top_n=200
        )
        assert rows == []

    def test_diesel_temporal_top_4_atividades(self):
        """Only the top 4 activities by total diesel appear in rows."""
        celulas = [
            _make_celula(atividade_id=f"ATV-{i}", consumo_diesel_L=float(100 - i), semana_iso="2026-W10")
            for i in range(6)
        ]
        cubo = SimpleNamespace(celulas=celulas)
        rows, _, _ = resolve_cubo_projection_rows(
            cubo, face="diesel_temporal", granularidade="mes", top_n=200
        )
        atividades_in_rows = {r["atividade_id"] for r in rows}
        assert len(atividades_in_rows) <= 4

    def test_diesel_temporal_empty_cubo(self):
        rows, _, chart_hint = resolve_cubo_projection_rows(
            _make_cubo(), face="diesel_temporal", granularidade="mes", top_n=200
        )
        assert rows == []
        assert chart_hint == "bar_stacked"

    # -- invalid face -----------------------------------------------------

    def test_invalid_face_raises_value_error(self):
        with pytest.raises(ValueError, match="Face de projeção não suportada"):
            resolve_cubo_projection_rows(
                self._cubo_stub(), face="nao_existe", granularidade="mes", top_n=200
            )

    # -- tempo_natureza (patched SCurveBuilder) ---------------------------

    def test_tempo_natureza_bar_stacked_via_mock(self):
        agg = SimpleNamespace(
            semana_iso="2026-W10",
            custo_direto_semana=80.0,
            custo_indireto_semana=20.0,
        )
        s_curve_mock = SimpleNamespace(agregacao_semanal=[agg])
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSCurveBuilder:
            MockSCurveBuilder.return_value.build.return_value = s_curve_mock
            rows, columns, chart_hint = resolve_cubo_projection_rows(
                _make_cubo(),
                face="tempo_natureza",
                granularidade="mes",
                top_n=200,
                canonical=SimpleNamespace(),
            )
        assert chart_hint == "bar_stacked"
        col_ids = {c["id"] for c in columns}
        assert col_ids == {"periodo", "natureza", "valor_rs"}
        naturezas = {r["natureza"] for r in rows}
        assert "direto" in naturezas
        assert "indireto" in naturezas

    def test_tempo_natureza_values_aggregated_correctly(self):
        agg1 = SimpleNamespace(semana_iso="2026-W10", custo_direto_semana=50.0, custo_indireto_semana=10.0)
        agg2 = SimpleNamespace(semana_iso="2026-W11", custo_direto_semana=30.0, custo_indireto_semana=5.0)
        s_curve_mock = SimpleNamespace(agregacao_semanal=[agg1, agg2])
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSCurveBuilder:
            MockSCurveBuilder.return_value.build.return_value = s_curve_mock
            rows, _, _ = resolve_cubo_projection_rows(
                _make_cubo(),
                face="tempo_natureza",
                granularidade="mes",
                top_n=200,
                canonical=SimpleNamespace(),
            )
        # Both weeks fold into same month bucket
        by_nat = {r["natureza"]: r["valor_rs"] for r in rows}
        assert by_nat["direto"] == pytest.approx(80.0)
        assert by_nat["indireto"] == pytest.approx(15.0)


# ===========================================================================
# resolve_abc_curva_rows
# ===========================================================================


class TestResolveAbcCurvaRows:
    def _make_curva(self, n_items: int = 5):
        """Return a stub CurvaABC with n_items, pct_acumulado 0..100."""
        items = []
        for i in range(n_items):
            pct_acc = (i + 1) * (100.0 / n_items)
            items.append(
                SimpleNamespace(
                    insumo_id=f"INS-{i:03d}",
                    descricao=f"Insumo {i}",
                    categoria="MAO_OBRA",
                    custo_total=1000.0 - i * 100,
                    pct_custo=100.0 / n_items,
                    pct_custo_acumulado=pct_acc,
                )
            )
        return SimpleNamespace(itens=items)

    def test_rows_contain_expected_keys(self):
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = self._make_curva(5)
            rows, columns, chart_hint, unit_type, operator_meta = resolve_abc_curva_rows(
                SimpleNamespace(), top_n=200, threshold_a=0.80, threshold_b=0.95
            )
        required_keys = {"insumo_id", "descricao", "categoria", "custo_total_rs", "pct_custo",
                         "pct_custo_acumulado", "classe_abc"}
        assert all(required_keys.issubset(r.keys()) for r in rows)

    def test_chart_hint_is_bar(self):
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = self._make_curva(3)
            _, _, chart_hint, _, _ = resolve_abc_curva_rows(
                SimpleNamespace(), top_n=200, threshold_a=0.80, threshold_b=0.95
            )
        assert chart_hint == "bar"

    def test_unit_type_is_currency_brl(self):
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = self._make_curva(3)
            _, _, _, unit_type, _ = resolve_abc_curva_rows(
                SimpleNamespace(), top_n=200, threshold_a=0.80, threshold_b=0.95
            )
        assert unit_type == "currency_brl"

    def test_operator_meta_keys(self):
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = self._make_curva(5)
            _, _, _, _, operator_meta = resolve_abc_curva_rows(
                SimpleNamespace(), top_n=200, threshold_a=0.80, threshold_b=0.95
            )
        assert "thresholds" in operator_meta
        assert "class_counts" in operator_meta
        assert "coverage_a" in operator_meta

    def test_class_abc_classification(self):
        """Items below threshold_a are A, between A and B are B, else C."""
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = self._make_curva(10)
            rows, _, _, _, _ = resolve_abc_curva_rows(
                SimpleNamespace(), top_n=200, threshold_a=50.0, threshold_b=90.0
            )
        classes = {r["classe_abc"] for r in rows}
        assert "A" in classes
        assert "C" in classes

    def test_top_n_limits_rows(self):
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = self._make_curva(10)
            rows, _, _, _, _ = resolve_abc_curva_rows(
                SimpleNamespace(), top_n=3, threshold_a=0.80, threshold_b=0.95
            )
        assert len(rows) <= 3

    def test_class_counts_in_operator_meta(self):
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = self._make_curva(10)
            _, _, _, _, operator_meta = resolve_abc_curva_rows(
                SimpleNamespace(), top_n=200, threshold_a=50.0, threshold_b=80.0
            )
        counts = operator_meta["class_counts"]
        assert set(counts.keys()) == {"A", "B", "C"}
        assert sum(counts.values()) == 10


# ===========================================================================
# resolve_s_curve_rows
# ===========================================================================


class TestResolveSCurveRows:
    def _make_s_curve(self, n_weeks: int = 4, total: float = 400.0):
        semanas = [f"2026-W{w:02d}" for w in range(10, 10 + n_weeks)]
        custo_semanal = [100.0] * n_weeks
        return SimpleNamespace(
            semanas_iso=semanas,
            custo_semanal=custo_semanal,
            total_projeto=total,
            agregacao_semanal=[],
        )

    def test_row_keys(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve()
            rows, _, _, _, _ = resolve_s_curve_rows(SimpleNamespace(), "mes", top_n=200)
        required = {"periodo", "custo_semanal_rs", "custo_acumulado_rs", "pct_acumulado"}
        assert all(required.issubset(r.keys()) for r in rows)

    def test_chart_hint_line(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve()
            _, _, chart_hint, _, _ = resolve_s_curve_rows(SimpleNamespace(), "mes", top_n=200)
        assert chart_hint == "line"

    def test_unit_type_currency_brl(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve()
            _, _, _, unit_type, _ = resolve_s_curve_rows(SimpleNamespace(), "mes", top_n=200)
        assert unit_type == "currency_brl"

    def test_operator_meta_has_total(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve(total=999.0)
            _, _, _, _, operator_meta = resolve_s_curve_rows(SimpleNamespace(), "mes", top_n=200)
        assert operator_meta["total_projeto_rs"] == 999.0

    def test_pct_acumulado_zero_when_total_zero(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve(total=0.0)
            rows, _, _, _, _ = resolve_s_curve_rows(SimpleNamespace(), "mes", top_n=200)
        assert all(r["pct_acumulado"] == 0.0 for r in rows)

    def test_custo_acumulado_monotonically_increasing(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            # Weeks across two different months so we get multiple rows
            sc = SimpleNamespace(
                semanas_iso=["2026-W05", "2026-W06", "2026-W09", "2026-W10"],
                custo_semanal=[100.0, 100.0, 150.0, 150.0],
                total_projeto=500.0,
                agregacao_semanal=[],
            )
            MockSC.return_value.build.return_value = sc
            rows, _, _, _, _ = resolve_s_curve_rows(SimpleNamespace(), "mes", top_n=200)
        acumulados = [r["custo_acumulado_rs"] for r in rows]
        assert acumulados == sorted(acumulados)

    def test_top_n_limits_rows(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            # 6 weeks across 3 months
            sc = SimpleNamespace(
                semanas_iso=[f"2026-W{w:02d}" for w in range(5, 11)],
                custo_semanal=[100.0] * 6,
                total_projeto=600.0,
                agregacao_semanal=[],
            )
            MockSC.return_value.build.return_value = sc
            rows, _, _, _, _ = resolve_s_curve_rows(SimpleNamespace(), "mes", top_n=2)
        assert len(rows) <= 2


# ===========================================================================
# resolve_recursos_ativos_rows
# ===========================================================================


class TestResolveRecursosAtivosRows:
    def _make_agg(self, semana_iso: str, n_equipes: float = 5.0, n_equip_unicos: float = 3.0,
                  equip_ativos: dict | None = None):
        return SimpleNamespace(
            semana_iso=semana_iso,
            n_equipes_totais=n_equipes,
            n_equipamentos_unicos=n_equip_unicos,
            equipamentos_ativos=equip_ativos or {"CAM-01": 2, "PLA-01": 1},
        )

    def _make_s_curve(self, n_weeks: int = 3):
        aggs = [self._make_agg(f"2026-W{10 + i:02d}") for i in range(n_weeks)]
        return SimpleNamespace(
            semanas_iso=[a.semana_iso for a in aggs],
            custo_semanal=[0.0] * n_weeks,
            total_projeto=0.0,
            agregacao_semanal=aggs,
        )

    def test_row_keys(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve()
            rows, _, _, _, _ = resolve_recursos_ativos_rows(SimpleNamespace(), "mes", top_n=200)
        required = {"periodo", "n_equipes_totais", "n_equipamentos_unicos", "equipamentos_unidades_ativas"}
        assert all(required.issubset(r.keys()) for r in rows)

    def test_chart_hint_line(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve()
            _, _, chart_hint, _, _ = resolve_recursos_ativos_rows(SimpleNamespace(), "mes", top_n=200)
        assert chart_hint == "line"

    def test_unit_type_is_count(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve()
            _, _, _, unit_type, _ = resolve_recursos_ativos_rows(SimpleNamespace(), "mes", top_n=200)
        assert unit_type == "count"

    def test_operator_meta_keys(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve()
            _, _, _, _, operator_meta = resolve_recursos_ativos_rows(SimpleNamespace(), "mes", top_n=200)
        assert "aggregation_rule" in operator_meta
        assert "n_periodos" in operator_meta

    def test_n_equipamentos_unicos_is_max_per_bucket(self):
        """When multiple weeks fold to same bucket, n_equipamentos_unicos = max."""
        agg1 = self._make_agg("2026-W10", n_equip_unicos=3.0)
        agg2 = self._make_agg("2026-W11", n_equip_unicos=7.0)
        sc = SimpleNamespace(
            semanas_iso=["2026-W10", "2026-W11"],
            custo_semanal=[0.0, 0.0],
            total_projeto=0.0,
            agregacao_semanal=[agg1, agg2],
        )
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = sc
            rows, _, _, _, _ = resolve_recursos_ativos_rows(SimpleNamespace(), "mes", top_n=200)
        assert rows[0]["n_equipamentos_unicos"] == 7

    def test_top_n_limits_rows(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._make_s_curve(n_weeks=6)
            rows, _, _, _, _ = resolve_recursos_ativos_rows(SimpleNamespace(), "semana", top_n=2)
        assert len(rows) <= 2


# ===========================================================================
# build_cube_projection_payload
# ===========================================================================


EXPECTED_PAYLOAD_KEYS = {"face", "granularidade", "rows", "columns", "chart_hint", "unit_type", "operator_meta"}


class TestBuildCubeProjectionPayload:
    def _simple_s_curve(self):
        return SimpleNamespace(
            semanas_iso=["2026-W10"],
            custo_semanal=[100.0],
            total_projeto=100.0,
            agregacao_semanal=[
                SimpleNamespace(
                    semana_iso="2026-W10",
                    custo_direto_semana=80.0,
                    custo_indireto_semana=20.0,
                    n_equipes_totais=5.0,
                    n_equipamentos_unicos=2.0,
                    equipamentos_ativos={"CAM-01": 2},
                )
            ],
        )

    # -- abc_curva branch --------------------------------------------------

    def test_abc_curva_payload_keys(self):
        curva = SimpleNamespace(
            itens=[
                SimpleNamespace(
                    insumo_id="INS-001",
                    descricao="Test",
                    categoria="MAO_OBRA",
                    custo_total=1000.0,
                    pct_custo=100.0,
                    pct_custo_acumulado=100.0,
                )
            ]
        )
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = curva
            payload = build_cube_projection_payload(
                canonical=SimpleNamespace(),
                cubo=_make_cubo(),
                face="abc_curva",
                granularidade="mes",
                top_n=200,
            )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())
        assert payload["face"] == "abc_curva"
        assert payload["granularidade"] == "mes"

    # -- s_curve_custo branch ----------------------------------------------

    def test_s_curve_custo_payload_keys(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._simple_s_curve()
            payload = build_cube_projection_payload(
                canonical=SimpleNamespace(),
                cubo=_make_cubo(),
                face="s_curve_custo",
                granularidade="mes",
                top_n=200,
            )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())
        assert payload["face"] == "s_curve_custo"

    # -- recursos_ativos_tempo branch -------------------------------------

    def test_recursos_ativos_tempo_payload_keys(self):
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = self._simple_s_curve()
            payload = build_cube_projection_payload(
                canonical=SimpleNamespace(),
                cubo=_make_cubo(),
                face="recursos_ativos_tempo",
                granularidade="mes",
                top_n=200,
            )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())
        assert payload["unit_type"] == "count"
        assert payload["operator_meta"] != {}

    # -- cubo-based branches ----------------------------------------------

    def test_tempo_componente_payload_keys(self):
        cubo = _make_cubo(_make_celula(componente_bdi="custo_direto", valor_rs=100.0))
        payload = build_cube_projection_payload(
            canonical=_make_canonical(),
            cubo=cubo,
            face="tempo_componente",
            granularidade="mes",
            top_n=200,
        )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())
        assert payload["operator_meta"] == {}
        assert payload["unit_type"] == FACE_UNIT_TYPES["tempo_componente"]

    def test_categoria_componente_payload_keys(self):
        cubo = _make_cubo(_make_celula(componente_bdi="custo_direto", valor_rs=100.0))
        payload = build_cube_projection_payload(
            canonical=_make_canonical(),
            cubo=cubo,
            face="categoria_componente",
            granularidade="mes",
            top_n=200,
        )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())
        assert payload["face"] == "categoria_componente"

    def test_atividade_componente_payload_keys(self):
        cubo = _make_cubo(_make_celula(componente_bdi="custo_direto", valor_rs=100.0))
        payload = build_cube_projection_payload(
            canonical=_make_canonical(),
            cubo=cubo,
            face="atividade_componente",
            granularidade="mes",
            top_n=200,
        )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())

    def test_diesel_temporal_payload_keys(self):
        cubo = _make_cubo(_make_celula(consumo_diesel_L=100.0, semana_iso="2026-W10"))
        payload = build_cube_projection_payload(
            canonical=_make_canonical(),
            cubo=cubo,
            face="diesel_temporal",
            granularidade="mes",
            top_n=200,
        )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())
        assert payload["unit_type"] == "volume_liters"

    def test_tempo_natureza_payload_keys(self):
        agg = SimpleNamespace(
            semana_iso="2026-W10",
            custo_direto_semana=100.0,
            custo_indireto_semana=20.0,
        )
        sc = SimpleNamespace(agregacao_semanal=[agg])
        with patch(
            "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder"
        ) as MockSC:
            MockSC.return_value.build.return_value = sc
            payload = build_cube_projection_payload(
                canonical=SimpleNamespace(),
                cubo=_make_cubo(),
                face="tempo_natureza",
                granularidade="mes",
                top_n=200,
            )
        assert EXPECTED_PAYLOAD_KEYS.issubset(payload.keys())
        assert payload["unit_type"] == "currency_brl"

    # -- abc_threshold custom values --------------------------------------

    def test_abc_curva_custom_thresholds(self):
        curva = SimpleNamespace(itens=[])
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder"
        ) as MockABC:
            MockABC.return_value.build.return_value = curva
            payload = build_cube_projection_payload(
                canonical=SimpleNamespace(),
                cubo=_make_cubo(),
                face="abc_curva",
                granularidade="mes",
                top_n=200,
                abc_threshold_a=0.70,
                abc_threshold_b=0.90,
            )
        assert payload["operator_meta"]["thresholds"]["a"] == 0.70
        assert payload["operator_meta"]["thresholds"]["b"] == 0.90
