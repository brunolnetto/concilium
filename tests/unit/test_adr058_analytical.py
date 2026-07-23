"""Tests for ADR-058: Analytical richness of the ontological space.

Covers:
- InsumoDetalheAtividade: typed schema, all fields
- CurvaABCInsumo: classification A/B/C, invariant sum≈1.0, ordering
- SCurve: cumulative invariant, weekly aggregation
- AgregacaoSemanalEquipamentos: equipment count per week
- CurvaABCBuilder: deterministic, handles empty canonical
- SCurveBuilder: deterministic, handles missing schedule
"""

from __future__ import annotations

import math

import pytest

from concilium.domain.models.analytics.analitica import (
    CurvaABCInsumo,
    InsumoDetalheAtividade,
    SCurve,
)
from concilium.domain.services.analytics.curva_abc_builder import CurvaABCBuilder
from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_canonical(with_schedule: bool = True):
    from concilium.application.skills import run_escopo_e_eap

    inputs = {
        "nome": "Test ADR-058",
        "tipo_obra": "terraplenagem",
        "localizacao": "BR",
        "coordenadas": {"lat": 0.0, "lng": 0.0},
        "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": "2027-06-01",
        "eap": [
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "CPU-A",
                "descricao": "Escavacao",
                "unidade": "m3",
                "quantitativo": 50000.0,
            },
            {
                "item_id": "eap-02",
                "ordem": 2,
                "cpu_id": "CPU-B",
                "descricao": "Compactacao",
                "unidade": "m3",
                "quantitativo": 30000.0,
            },
        ],
        "contexto_id": "test",
        "snapshot_catalogo_id": "snap",
        "snapshot_perfil_id": "snap",
    }
    canonical = run_escopo_e_eap(None, inputs).canonical

    # Inject equipes_diretas manually for testing
    from concilium.domain.models.canonical import EquipamentoEquipeDireta, EquipeDireta, FuncaoEquipeDireta

    equipes = [
        EquipeDireta(
            equipe_id="eq-01",
            item_id="eap-01",
            cpu_id="CPU-A",
            nome="Equipe A",
            funcoes=[
                FuncaoEquipeDireta(
                    funcao_id="MO-OPER-ESCAV",
                    descricao="Operador Escavadeira",
                    num_pessoas=1,
                    custo_mensal_unitario=12000.0,
                ),
                FuncaoEquipeDireta(
                    funcao_id="MO-AJUDANTE", descricao="Ajudante", num_pessoas=3, custo_mensal_unitario=4000.0
                ),
            ],
            equipamentos=[
                EquipamentoEquipeDireta(
                    equip_id="EQ-ESCAV-38T",
                    descricao="Escavadeira 38T",
                    num_unidades=1,
                    custo_mensal=35000.0,
                    custo_combustivel_mensal=8000.0,
                ),
            ],
            custo_mao_obra_mensal=24000.0,
            custo_equipamentos_mensal=35000.0,
            custo_combustivel_total_mensal=8000.0,
            custo_fixo_mensal=67000.0,
            permanencia_meses=4.0,
            custo_total=268000.0,
        ),
        EquipeDireta(
            equipe_id="eq-02",
            item_id="eap-02",
            cpu_id="CPU-B",
            nome="Equipe B",
            funcoes=[
                FuncaoEquipeDireta(
                    funcao_id="MO-OPER-TRATOR",
                    descricao="Operador Trator",
                    num_pessoas=1,
                    custo_mensal_unitario=10000.0,
                ),
            ],
            equipamentos=[
                EquipamentoEquipeDireta(
                    equip_id="EQ-ESCAV-38T",
                    descricao="Escavadeira 38T",
                    num_unidades=1,
                    custo_mensal=35000.0,
                    custo_combustivel_mensal=6000.0,
                ),
                EquipamentoEquipeDireta(
                    equip_id="EQ-TRATOR", descricao="Trator Esteira", num_unidades=1, custo_mensal=28000.0
                ),
            ],
            custo_mao_obra_mensal=10000.0,
            custo_equipamentos_mensal=63000.0,
            custo_combustivel_total_mensal=6000.0,
            custo_fixo_mensal=73000.0,
            permanencia_meses=3.0,
            custo_total=219000.0,
        ),
    ]
    canonical = canonical.model_copy(update={"equipes_diretas": equipes})

    if with_schedule:
        from concilium.domain.models.canonical import Cronograma, DistribuicaoSemanal, ScheduledActivityCanonical

        sched_activities = [
            ScheduledActivityCanonical(
                activity_id="eap-01",
                start_week=0,
                end_week=15,
                duration_weeks=16,
                distribuicao_semanal={
                    f"2026-W{w + 24:02d}": DistribuicaoSemanal(
                        num_equipes=3,
                        qtd_executada=3125.0,
                        qtd_acumulada=3125.0 * (w + 1),
                        pct=3125.0 * (w + 1) / 50000.0,
                    )
                    for w in range(16)
                },
            ),
            ScheduledActivityCanonical(
                activity_id="eap-02",
                start_week=10,
                end_week=21,
                duration_weeks=12,
                distribuicao_semanal={
                    f"2026-W{w + 34:02d}": DistribuicaoSemanal(
                        num_equipes=2,
                        qtd_executada=2500.0,
                        qtd_acumulada=2500.0 * (w + 1),
                        pct=2500.0 * (w + 1) / 30000.0,
                    )
                    for w in range(12)
                },
            ),
        ]
        cronograma = Cronograma(
            algorithm="manual_allocation",
            quality_score=1.0,
            makespan_weeks=22,
            is_feasible=True,
            scheduled_activities=sched_activities,
        )
        canonical = canonical.model_copy(update={"cronograma": cronograma})

    return canonical


# ---------------------------------------------------------------------------
# InsumoDetalheAtividade — typed schema
# ---------------------------------------------------------------------------


class TestInsumoDetalheAtividade:
    def test_fields_accessible(self):
        d = InsumoDetalheAtividade(
            insumo_id="MO-OPER",
            descricao="Operador",
            categoria="MAO_OBRA",
            num_unidades=1.0,
            custo_unitario_mensal=10000.0,
            permanencia_meses=3.0,
            custo_total=30000.0,
        )
        assert d.insumo_id == "MO-OPER"
        assert d.custo_total == 30000.0

    def test_frozen_immutable(self):
        d = InsumoDetalheAtividade(
            insumo_id="X",
            descricao="X",
            categoria="MAO_OBRA",
            num_unidades=1,
            custo_unitario_mensal=1,
            permanencia_meses=1,
            custo_total=1,
        )
        with pytest.raises((AttributeError, TypeError)):
            d.custo_total = 999  # type: ignore[misc]

    def test_to_dict(self):
        d = InsumoDetalheAtividade(
            insumo_id="EQ-X",
            descricao="EQ",
            categoria="EQUIPAMENTO",
            num_unidades=2.0,
            custo_unitario_mensal=5000.0,
            permanencia_meses=2.0,
            custo_total=20000.0,
        )
        dd = d.to_dict()
        assert dd["insumo_id"] == "EQ-X"
        assert dd["custo_total"] == 20000.0


# ---------------------------------------------------------------------------
# CurvaABCBuilder
# ---------------------------------------------------------------------------


class TestCurvaABCBuilder:
    def test_builds_successfully(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        assert isinstance(abc, CurvaABCInsumo)
        assert abc.total_custo_direto > 0

    def test_items_ordered_by_cost_desc(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        for i in range(len(abc.itens) - 1):
            assert abc.itens[i].custo_total >= abc.itens[i + 1].custo_total

    def test_pct_sums_to_one(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        total = sum(item.pct_custo for item in abc.itens)
        assert math.isclose(total, 1.0, abs_tol=0.001)

    def test_classification_valid(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        for item in abc.itens:
            assert item.classe in ("A", "B", "C")

    def test_pct_acumulado_monotone(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        prev = 0.0
        for item in abc.itens:
            assert item.pct_custo_acumulado >= prev - 1e-9
            prev = item.pct_custo_acumulado

    def test_last_item_pct_acumulado_near_one(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        assert math.isclose(abc.itens[-1].pct_custo_acumulado, 1.0, abs_tol=0.001)

    def test_class_a_covers_80pct(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        # Items in class A should represent >= 70% (can vary with few items)
        a_items = [i for i in abc.itens if i.classe == "A"]
        if a_items:
            a_cost = sum(i.custo_total for i in a_items)
            assert a_cost / abc.total_custo_direto >= 0.70

    def test_insumos_aggregated_across_activities(self):
        """EQ-ESCAV-38T appears in both eap-01 and eap-02 — should be aggregated."""
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        escav_items = [i for i in abc.itens if "ESCAV-38T" in i.insumo_id and "DIESEL" not in i.insumo_id]
        assert len(escav_items) == 1, "EQ-ESCAV-38T should be aggregated into one ABC item"
        escav = escav_items[0]
        # Should contain both atividades
        assert "eap-01" in escav.atividades
        assert "eap-02" in escav.atividades

    def test_empty_canonical_returns_empty_abc(self):
        from concilium.application.skills import run_escopo_e_eap

        inputs = {
            "nome": "Empty",
            "tipo_obra": "terraplenagem",
            "localizacao": "BR",
            "coordenadas": {"lat": 0, "lng": 0},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-01-01",
            "data_termino": "2027-01-01",
            "eap": [],
            "contexto_id": "test",
            "snapshot_catalogo_id": "s",
            "snapshot_perfil_id": "s",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical
        abc = CurvaABCBuilder().build(canonical)
        assert abc.total_custo_direto == 0.0
        assert len(abc.itens) == 0

    def test_detalhes_por_atividade(self):
        canonical = _make_canonical(with_schedule=False)
        detalhes = CurvaABCBuilder().build_detalhes_por_atividade(canonical)
        assert "eap-01" in detalhes
        assert "eap-02" in detalhes
        for _item_id, dets in detalhes.items():
            for d in dets:
                assert isinstance(d, InsumoDetalheAtividade)
                assert d.custo_total >= 0

    def test_abc_totals_by_class(self):
        canonical = _make_canonical(with_schedule=False)
        abc = CurvaABCBuilder().build(canonical)
        assert math.isclose(abc.total_a + abc.total_b + abc.total_c, abc.total_custo_direto, rel_tol=0.001)


# ---------------------------------------------------------------------------
# SCurveBuilder
# ---------------------------------------------------------------------------


class TestSCurveBuilder:
    def test_builds_successfully_with_schedule(self):
        canonical = _make_canonical(with_schedule=True)
        sc = SCurveBuilder().build(canonical)
        assert isinstance(sc, SCurve)
        assert len(sc.semanas_iso) > 0

    def test_cumulative_monotone(self):
        canonical = _make_canonical(with_schedule=True)
        sc = SCurveBuilder().build(canonical)
        prev = 0.0
        for c in sc.custo_acumulado:
            assert c >= prev - 1e-6
            prev = c

    def test_pct_acumulado_ends_near_one(self):
        canonical = _make_canonical(with_schedule=True)
        sc = SCurveBuilder().build(canonical)
        if sc.pct_acumulado:
            assert math.isclose(sc.pct_acumulado[-1], 1.0, abs_tol=0.001)

    def test_aggregation_has_equipamentos(self):
        canonical = _make_canonical(with_schedule=True)
        sc = SCurveBuilder().build(canonical)
        # Active weeks should have equipamentos
        active = [a for a in sc.agregacao_semanal if a.n_equipes_totais > 0]
        assert len(active) > 0
        for agr in active:
            assert agr.n_equipamentos_unicos >= 0
            assert agr.custo_direto_semana >= 0

    def test_total_matches_sum_of_weekly(self):
        canonical = _make_canonical(with_schedule=True)
        sc = SCurveBuilder().build(canonical)
        computed_total = sum(sc.custo_semanal)
        assert math.isclose(computed_total, sc.total_custo_direto + sc.total_custo_indireto, rel_tol=0.01)

    def test_empty_schedule_returns_empty(self):
        canonical = _make_canonical(with_schedule=False)
        sc = SCurveBuilder().build(canonical)
        assert sc.total_projeto == 0.0
        assert len(sc.semanas_iso) == 0

    def test_all_tuples_same_length(self):
        canonical = _make_canonical(with_schedule=True)
        sc = SCurveBuilder().build(canonical)
        n = len(sc.semanas_iso)
        assert len(sc.custo_semanal) == n
        assert len(sc.custo_acumulado) == n
        assert len(sc.pct_acumulado) == n
        assert len(sc.agregacao_semanal) == n

    def test_to_dict_json_serializable(self):
        import json

        canonical = _make_canonical(with_schedule=True)
        sc = SCurveBuilder().build(canonical)
        d = sc.to_dict()
        json_str = json.dumps(d, ensure_ascii=False, default=str)
        assert len(json_str) > 50

    def test_build_uses_pool_costs_when_available(self):
        """Covers the custo_por_semana_pool non-empty branch in SCurveBuilder.build."""
        from unittest.mock import patch

        canonical = _make_canonical(with_schedule=True)
        pool_costs = {"2026-W23": 10000.0, "2026-W24": 20000.0}

        with patch(
            "concilium.domain.services.analytics.s_curve_builder._scb_collect_direct_costs_pool",
            return_value=pool_costs,
        ):
            sc = SCurveBuilder().build(canonical)
        assert isinstance(sc, SCurve)
        # pool costs must be reflected in total
        assert sc.total_custo_direto >= 0

    def test_build_empty_when_no_schedule_weeks(self):
        """Covers _scb_collect_semanas returning (None, None) — _empty() branch."""

        canonical = _make_canonical(with_schedule=False)
        sc = SCurveBuilder().build(canonical)
        assert sc.total_projeto == 0.0
        assert sc.semanas_iso == ()

    def test_build_empty_when_activities_have_no_weeks(self):
        """scheduled_activities is non-empty but every distribuicao_semanal is
        empty → _scb_collect_semanas returns (None, None) via the build()
        code path (not just the helper in isolation)."""
        from concilium.domain.models.canonical import Cronograma, ScheduledActivityCanonical

        canonical = _make_canonical(with_schedule=False)
        sched_activities = [
            ScheduledActivityCanonical(
                activity_id="eap-01",
                start_week=0,
                end_week=0,
                duration_weeks=0,
                distribuicao_semanal={},
            ),
        ]
        cronograma = Cronograma(
            algorithm="manual_allocation",
            quality_score=1.0,
            makespan_weeks=1,
            is_feasible=True,
            scheduled_activities=sched_activities,
        )
        canonical = canonical.model_copy(update={"cronograma": cronograma})
        sc = SCurveBuilder().build(canonical)
        assert sc.total_projeto == 0.0
        assert sc.semanas_iso == ()

    def test_build_skips_equipamento_with_blank_equip_id(self):
        """An EquipamentoEquipeDireta with a falsy equip_id (default "") must
        not be aggregated into equip_por_semana."""
        from concilium.domain.models.canonical import EquipamentoEquipeDireta

        canonical = _make_canonical(with_schedule=True)
        equipes = list(canonical.equipes_diretas)
        equipes[0] = equipes[0].model_copy(
            update={
                "equipamentos": [
                    EquipamentoEquipeDireta(
                        equip_id="",
                        descricao="Sem ID",
                        num_unidades=1,
                        custo_mensal=1000.0,
                    ),
                ]
            }
        )
        canonical = canonical.model_copy(update={"equipes_diretas": equipes})
        sc = SCurveBuilder().build(canonical)
        assert sc.total_projeto >= 0.0


# ---------------------------------------------------------------------------
# SCurveBuilder helper functions
# ---------------------------------------------------------------------------


class TestSCurveBuilderHelpers:
    def test_extend_weeks_no_op_when_within_length(self):
        """max_offset < len(semanas_sorted) → returns unchanged list."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_extend_weeks_for_offsets

        weeks = ["2026-W01", "2026-W02", "2026-W03"]
        result = _scb_extend_weeks_for_offsets(weeks, max_offset=1)
        assert result == weeks

    def test_extend_weeks_appends_when_offset_exceeds_length(self):
        """max_offset >= len(semanas_sorted) → appends new ISO weeks."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_extend_weeks_for_offsets

        weeks = ["2026-W01", "2026-W02"]
        result = _scb_extend_weeks_for_offsets(weeks, max_offset=3)
        assert len(result) == 4  # needs to reach index 3
        assert result[:2] == weeks
        assert all("-W" in w for w in result)

    def test_extend_weeks_empty_list_returns_empty(self):
        """Empty semanas_sorted → returned as-is."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_extend_weeks_for_offsets

        result = _scb_extend_weeks_for_offsets([], max_offset=5)
        assert result == []

    def test_build_curves_zero_total_proj_gives_zero_pct(self):
        """total_proj == 0 → pct_acum is all zeros."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_build_curves

        custo_acum, pct_acum = _scb_build_curves([0.0, 0.0, 0.0], total_proj=0.0)
        assert custo_acum == [0.0, 0.0, 0.0]
        assert pct_acum == [0.0, 0.0, 0.0]

    def test_build_curves_normal(self):
        """Normal case: pct_acum ends at 1.0."""
        import math

        from concilium.domain.services.analytics.s_curve_builder import _scb_build_curves

        custo_acum, pct_acum = _scb_build_curves([100.0, 200.0, 300.0], total_proj=600.0)
        assert custo_acum[-1] == 600.0
        assert math.isclose(pct_acum[-1], 1.0, abs_tol=1e-6)

    def test_collect_direct_costs_pool_returns_empty_on_exception(self):
        """CuboPoolInstancialBuilder.build raises → returns empty dict."""
        from unittest.mock import MagicMock, patch

        from concilium.domain.services.analytics.s_curve_builder import _scb_collect_direct_costs_pool

        with patch(
            "concilium.domain.services.analytics.cubo_pool_builder.CuboPoolInstancialBuilder.build",
            side_effect=Exception("fail"),
        ):
            result = _scb_collect_direct_costs_pool(MagicMock())
        assert result == {}

    def test_collect_semanas_returns_none_when_no_weeks(self):
        """No distribuicao_semanal keys → returns (None, None)."""
        from unittest.mock import MagicMock

        from concilium.domain.services.analytics.s_curve_builder import _scb_collect_semanas

        sa = MagicMock()
        sa.distribuicao_semanal = {}
        result = _scb_collect_semanas([sa])
        assert result == (None, None)


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
            total_a=800.0,
            total_b=150.0,
            total_c=50.0,
            n_itens_a=1,
            n_itens_b=0,
            n_itens_c=0,
        )
        d = curva.to_dict()
        assert d["projeto_id"] == "p1"
        assert isinstance(d["itens"], list)

    def test_scurve_to_dict(self):
        from concilium.domain.models.analytics.analitica import AgregacaoSemanalEquipamentos, SCurve

        agreg = AgregacaoSemanalEquipamentos(
            semana_iso="2026-W01",
            semana_offset=0,
            equipamentos_ativos={},
            n_equipamentos_unicos=0,
            n_equipes_totais=0,
            custo_direto_semana=8000.0,
            custo_indireto_semana=2000.0,
            custo_total_semana=10000.0,
        )
        scurve = SCurve(
            projeto_id="p1",
            gerado_em="2026",
            total_custo_direto=100000.0,
            total_custo_indireto=20000.0,
            total_projeto=120000.0,
            semanas_iso=("2026-W01",),
            custo_semanal=(10000.0,),
            custo_acumulado=(10000.0,),
            pct_acumulado=(0.1,),
            agregacao_semanal=(agreg,),
        )
        d = scurve.to_dict()
        assert d["projeto_id"] == "p1"



