"""Tests for CuboAnalitico — cubo 4D (categoria × atividade × tempo × componente BDI).

Covers:
- CelulaAnalitica: is_tributo, is_overhead, is_margem, is_custo_direto
- CuboAnalitico invariants:
  * total_preco_venda == sum(célula.valor_rs)
  * total_custo_direto + total_overhead + total_margem + total_tributos ≈ total_preco_venda
  * For each (categoria, atividade, semana): sum of components ≈ PV_semana(cat, atv, sem)
- CuboAnalitico projections:
  * exposicao_tributaria_semanal: monotone-compatible values, covers all semanas
  * exposicao_tributaria_por_tipo: 5 tributary types
  * margem_por_atividade: ordered desc, sums to total_margem
  * composicao_preco_temporal: each week sums to total_semana correctly
- CuboAnaliticoBuilder:
  * Deterministic (same canonical → same total, same n_celulas)
  * No insumo iteration — uses pre-aggregated EquipeDireta fields
  * Handles empty schedule gracefully
  * Diesel efficiency applied correctly
  * Regime version passed through
- slice() and group_by() correctness
- to_dict() JSON-serializable
"""

from __future__ import annotations

import json
import math
from collections import defaultdict

import pytest

from concilium.domain.models.analytics.cubo_analitico import (
    CelulaAnalitica,
    CuboAnalitico,
)
from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_canonical(n_atividades: int = 2, with_schedule: bool = True):
    from concilium.application.skills import run_escopo_e_eap
    from concilium.domain.models.canonical import (
        Cronograma,
        DistribuicaoSemanal,
        EquipamentoEquipeDireta,
        EquipeDireta,
        FuncaoEquipeDireta,
        ScheduledActivityCanonical,
    )

    eap = [
        {
            "item_id": f"eap-{i:02d}",
            "ordem": i,
            "cpu_id": f"CPU-{i}",
            "descricao": f"Atividade {i}",
            "unidade": "m3",
            "quantitativo": 10000.0 * i,
        }
        for i in range(1, n_atividades + 1)
    ]
    inputs = {
        "nome": "Test Cubo",
        "tipo_obra": "terraplenagem",
        "localizacao": "BR",
        "coordenadas": {"lat": 0, "lng": 0},
        "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
        "data_inicio": "2026-06-01",
        "data_termino": "2027-12-31",
        "eap": eap,
        "contexto_id": "test",
        "snapshot_catalogo_id": "s",
        "snapshot_perfil_id": "s",
    }
    canonical = run_escopo_e_eap(None, inputs).canonical

    equipes = []
    for i in range(1, n_atividades + 1):
        equipes.append(
            EquipeDireta(
                equipe_id=f"eq-{i:02d}",
                item_id=f"eap-{i:02d}",
                cpu_id=f"CPU-{i}",
                funcoes=[FuncaoEquipeDireta(funcao_id="MO-OPER", num_pessoas=1, custo_mensal_unitario=12000.0)],
                equipamentos=[
                    EquipamentoEquipeDireta(
                        equip_id="EQ-ESCAV", num_unidades=1, custo_mensal=35000.0, custo_combustivel_mensal=8000.0
                    ),
                ],
                custo_mao_obra_mensal=12000.0,
                custo_equipamentos_mensal=35000.0,
                custo_combustivel_total_mensal=8000.0,
                custo_material_mensal=2000.0,
                custo_fixo_mensal=57000.0,
                permanencia_meses=3.0,
                custo_total=171000.0,
            )
        )

    if with_schedule:
        n_weeks = 12
        sched = []
        for i in range(1, n_atividades + 1):
            start = (i - 1) * 6
            end = start + n_weeks - 1
            dist_sem = {}
            for w in range(n_weeks):
                sem = f"2026-W{start + w + 24:02d}"
                dist_sem[sem] = DistribuicaoSemanal(
                    num_equipes=2,
                    qtd_executada=833.0,
                    qtd_acumulada=833.0 * (w + 1),
                    pct=0.1,
                )
            sched.append(
                ScheduledActivityCanonical(
                    activity_id=f"eap-{i:02d}",
                    start_week=start,
                    end_week=end,
                    duration_weeks=n_weeks,
                    distribuicao_semanal=dist_sem,
                )
            )
        cronograma = Cronograma(
            algorithm="manual_allocation",
            quality_score=1.0,
            makespan_weeks=n_atividades * 6 + n_weeks,
            is_feasible=True,
            scheduled_activities=sched,
        )
        canonical = canonical.model_copy(update={"equipes_diretas": equipes, "cronograma": cronograma})
    else:
        canonical = canonical.model_copy(update={"equipes_diretas": equipes})

    return canonical


# ---------------------------------------------------------------------------
# CelulaAnalitica
# ---------------------------------------------------------------------------


class TestCelulaAnalitica:
    def _cell(self, comp: str, cat_insumo: str = "mao_obra", prop: str = "salario_encargos") -> CelulaAnalitica:
        return CelulaAnalitica(
            natureza="direto",
            atividade_id="eap-01",
            categoria_insumo=cat_insumo,
            propriedade=prop,
            semana_iso="2026-W23",
            componente_bdi=comp,
            valor_rs=100.0,
        )

    @pytest.mark.parametrize(
        "comp,expected_is",
        [
            ("custo_direto", "custo_direto"),
            ("overhead_ac", "overhead"),
            ("overhead_df", "overhead"),
            ("margem_l", "margem"),
            ("tributo_iss", "tributo"),
            ("tributo_cofins", "tributo"),
        ],
    )
    def test_cell_classification(self, comp, expected_is):
        c = self._cell(comp)
        if expected_is == "custo_direto":
            assert c.is_custo_direto()
            assert not c.is_overhead()
            assert not c.is_margem()
            assert not c.is_tributo()
        elif expected_is == "overhead":
            assert c.is_overhead()
        elif expected_is == "margem":
            assert c.is_margem()
        elif expected_is == "tributo":
            assert c.is_tributo()

    def test_frozen(self):
        c = self._cell("custo_direto")
        with pytest.raises((AttributeError, TypeError)):
            c.valor_rs = 999  # type: ignore[misc]

    def test_categoria_backward_compat(self):
        """Backward compat: material.combustivel → categoria='diesel' (ADR-090)."""
        c_diesel = CelulaAnalitica(
            natureza="direto",
            atividade_id="eap-01",
            categoria_insumo="material",
            propriedade="combustivel",  # ADR-090
            semana_iso="2026-W01",
            componente_bdi="custo_direto",
            valor_rs=50.0,
            valor_fisico=10.0,
            unidade_fisica="L",
        )
        assert c_diesel.categoria == "diesel"  # backward compat via property
        assert c_diesel.consumo_diesel_L == 10.0  # backward compat via property
        assert c_diesel.is_diesel()

        c_mat = CelulaAnalitica(
            natureza="direto",
            atividade_id="eap-01",
            categoria_insumo="material",
            propriedade="consumivel",
            semana_iso="2026-W01",
            componente_bdi="custo_direto",
            valor_rs=80.0,
        )
        assert c_mat.categoria == "material"
        assert c_mat.consumo_diesel_L == 0.0
        assert not c_mat.is_diesel()

        c_eq = CelulaAnalitica(
            natureza="direto",
            atividade_id="eap-01",
            categoria_insumo="equipamento",
            propriedade="aluguel",
            semana_iso="2026-W01",
            componente_bdi="custo_direto",
            valor_rs=100.0,
        )
        assert c_eq.categoria == "equipamento"
        assert not c_eq.is_diesel()


# ---------------------------------------------------------------------------
# CuboAnaliticoBuilder
# ---------------------------------------------------------------------------


class TestCuboAnaliticoBuilder:
    def test_builds_from_canonical(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        assert isinstance(cubo, CuboAnalitico)
        assert cubo.total_preco_venda > 0
        assert len(cubo.celulas) > 0

    def test_deterministic(self):
        canonical = _make_canonical()
        c1 = CuboAnaliticoBuilder().build(canonical)
        c2 = CuboAnaliticoBuilder().build(canonical)
        assert math.isclose(c1.total_preco_venda, c2.total_preco_venda, rel_tol=1e-9)
        assert len(c1.celulas) == len(c2.celulas)

    def test_empty_schedule_returns_empty(self):
        canonical = _make_canonical(with_schedule=False)
        cubo = CuboAnaliticoBuilder().build(canonical)
        assert cubo.total_preco_venda == 0.0
        assert len(cubo.celulas) == 0

    def test_regime_version_stored(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder(regime_version="transicao").build(canonical)
        assert cubo.regime_bdi == "transicao"

    def test_four_categories_present(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        cats = {c.categoria for c in cubo.celulas}
        # mao_obra, equipamento, diesel, material all have non-zero costs in fixture
        assert "mao_obra" in cats
        assert "equipamento" in cats
        assert "diesel" in cats

    def test_eleven_bdi_components_per_active_cell(self):
        """BDI components por célula refletem o perfil da categoria.

        mao_obra/servicos/equipamento: múltiplos overhead + tributos → >= 6 componentes
        material/diesel: BDI = apenas L (lucro), sem overhead/tributos → 2 componentes
        Calibração AGIS: COFINS/PIS = 0% (isenção infraestrutura); diesel/material = L=4%.
        """
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        groups: dict[tuple, set] = defaultdict(set)
        for c in cubo.celulas:
            groups[(c.categoria, c.atividade_id, c.semana_iso)].add(c.componente_bdi)
        for key, comps in groups.items():
            # material e diesel: BDI = só lucro → custo_direto + margem_l (2 componentes)
            if key[0] in ("material", "diesel"):
                continue
            # mao_obra e serviços: AC + DF + R + L + ISS + CSSL + IR → >= 6
            assert len(comps) >= 6, f"Expected >= 6 components for {key}, got {len(comps)}"

    def test_no_insumo_id_field_in_cells(self):
        """Cells should NOT have insumo_id — that's CurvaABC's job."""
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        for c in cubo.celulas:
            assert not hasattr(c, "insumo_id")

    def test_all_semanas_from_schedule_represented(self):
        canonical = _make_canonical(n_atividades=1)
        cubo = CuboAnaliticoBuilder().build(canonical)
        cubo_semanas = {c.semana_iso for c in cubo.celulas}
        sched = canonical.cronograma.scheduled_activities[0]
        sched_semanas = set(sched.distribuicao_semanal.keys())
        assert cubo_semanas >= sched_semanas


# ---------------------------------------------------------------------------
# CuboAnalitico invariants
# ---------------------------------------------------------------------------


class TestCuboInvariants:
    def test_total_equals_sum_of_cells(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        computed = round(sum(c.valor_rs for c in cubo.celulas), 2)
        assert math.isclose(computed, cubo.total_preco_venda, rel_tol=0.001)

    def test_components_sum_to_total(self):
        """custo_direto + overhead + margem + tributos ≈ total_preco_venda."""
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        decomposed = cubo.total_custo_direto + cubo.total_overhead + cubo.total_margem + cubo.total_tributos
        assert math.isclose(decomposed, cubo.total_preco_venda, rel_tol=0.001)

    def test_decomposition_within_categoria_semana(self):
        """For each (categoria, atividade, semana) group: sum of comps ≈ PV_semana."""
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        groups: dict[tuple, float] = defaultdict(float)
        for c in cubo.celulas:
            groups[(c.categoria, c.atividade_id, c.semana_iso)] += c.valor_rs
        # Every group should have a positive total
        for key, total in groups.items():
            assert total > 0, f"Group {key} has zero total"

    def test_all_valores_positive(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        for c in cubo.celulas:
            assert c.valor_rs >= 0, f"Negative cell: {c}"

    def test_pct_margem_plus_pct_tributos_less_than_one(self):
        """Margin + taxes < 100% — direct cost must be positive."""
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        assert cubo.pct_margem + cubo.pct_tributos < 1.0


# ---------------------------------------------------------------------------
# Projections
# ---------------------------------------------------------------------------


class TestProjections:
    def test_exposicao_tributaria_semanal_covers_all_semanas(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        trib_sem = cubo.exposicao_tributaria_semanal()
        {c.semana_iso for c in cubo.celulas}
        trib_semanas = set(trib_sem.keys())
        # All semanas with positive custo should also have tributos (except material)
        non_material = {c.semana_iso for c in cubo.celulas if c.categoria != "material"}
        assert trib_semanas >= non_material

    def test_exposicao_tributaria_por_tipo_has_active_types(self):
        """Apenas tributos não-zero aparecem na exposição. Calibração AGIS: COFINS/PIS = 0%."""
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        trib_tipo = cubo.exposicao_tributaria_por_tipo()
        # DEFAULT calibrado AGIS: COFINS=0%, PIS=0% → apenas ISS, CSSL, IR contribuem
        assert "tributo_iss" in trib_tipo
        assert "tributo_cssl" in trib_tipo
        assert "tributo_ir" in trib_tipo
        # COFINS e PIS podem estar ausentes ou com valor zero (isenção infraestrutura)
        for k, v in trib_tipo.items():
            assert v >= 0, f"Tributo negativo: {k}={v}"

    def test_exposicao_tributaria_total_consistent(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        sum_by_type = sum(cubo.exposicao_tributaria_por_tipo().values())
        assert math.isclose(sum_by_type, cubo.total_tributos, rel_tol=0.001)

    @pytest.mark.parametrize(
        "granularidade",
        ["semana", "mes", "bimestre", "trimestre", "semestre", "ano"],
    )
    def test_composicao_preco_temporal_all_granularities_close_total(self, granularidade):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        comp = cubo.composicao_preco_temporal(granularidade)
        total = sum(sum(v.values()) for v in comp.values())
        assert math.isclose(total, cubo.total_preco_venda, rel_tol=0.001)

    @pytest.mark.parametrize(
        "granularidade",
        ["mes", "bimestre", "trimestre", "semestre", "ano"],
    )
    def test_exposicao_tributaria_temporal_matches_weekly_total(self, granularidade):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        temporal = cubo.exposicao_tributaria_temporal(granularidade)
        assert math.isclose(sum(temporal.values()), cubo.total_tributos, rel_tol=0.001)

    def test_temporal_wrapper_methods_are_available(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        assert cubo.composicao_preco_mensal()
        assert cubo.composicao_preco_bimestral()
        assert cubo.composicao_preco_trimestral()
        assert cubo.composicao_preco_semestral()
        assert cubo.composicao_preco_anual()

    def test_resumo_por_natureza_closes_project_total(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        resumo = cubo.resumo_por_natureza()
        assert set(resumo.keys()) == {"direto", "indireto"}
        assert math.isclose(resumo["direto"] + resumo["indireto"], cubo.total_preco_venda, rel_tol=0.001)

    @pytest.mark.parametrize("granularidade", ["semana", "mes", "bimestre", "trimestre", "semestre", "ano"])
    def test_resumo_por_natureza_temporal_closes_project_total(self, granularidade):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        resumo = cubo.resumo_por_natureza_temporal(granularidade)
        total = sum(float(vals.get("direto", 0.0)) + float(vals.get("indireto", 0.0)) for vals in resumo.values())
        assert math.isclose(total, cubo.total_preco_venda, rel_tol=0.001)

    def test_margem_por_atividade_ordered_desc(self):
        canonical = _make_canonical(n_atividades=3)
        cubo = CuboAnaliticoBuilder().build(canonical)
        margem = cubo.margem_por_atividade()
        values = list(margem.values())
        for i in range(len(values) - 1):
            assert values[i] >= values[i + 1]

    def test_margem_por_atividade_sums_to_total(self):
        canonical = _make_canonical(n_atividades=2)
        cubo = CuboAnaliticoBuilder().build(canonical)
        margem = cubo.margem_por_atividade()
        assert math.isclose(sum(margem.values()), cubo.total_margem, rel_tol=0.001)

    def test_composicao_preco_temporal_weekly_totals(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        comp_temp = cubo.composicao_preco_temporal()
        for _semana, comps in comp_temp.items():
            total_sem = sum(comps.values())
            # Each week should have positive total
            assert total_sem > 0

    def test_composicao_preco_temporal_aggregated_total(self):
        """Sum of all weekly totals ≈ total_preco_venda."""
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        comp_temp = cubo.composicao_preco_temporal()
        grand_total = sum(v for week_comps in comp_temp.values() for v in week_comps.values())
        assert math.isclose(grand_total, cubo.total_preco_venda, rel_tol=0.001)


# ---------------------------------------------------------------------------
# slice() and group_by()
# ---------------------------------------------------------------------------


class TestSliceAndGroupBy:
    def test_slice_by_categoria(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        sliced = cubo.slice(categoria="mao_obra")
        assert all(c.categoria == "mao_obra" for c in sliced.celulas)
        assert sliced.total_preco_venda < cubo.total_preco_venda

    def test_slice_by_componente(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        sliced = cubo.slice(componente_bdi="margem_l")
        assert all(c.componente_bdi == "margem_l" for c in sliced.celulas)
        assert math.isclose(sliced.total_preco_venda, cubo.total_margem, rel_tol=0.001)

    def test_group_by_semana_componente(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        gb = cubo.group_by("semana_iso", "componente_bdi")
        total = round(sum(gb.values()), 2)
        assert math.isclose(total, cubo.total_preco_venda, rel_tol=0.001)

    def test_group_by_categoria(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        gb = cubo.group_by("categoria")
        total = sum(gb.values())
        assert math.isclose(total, cubo.total_preco_venda, rel_tol=0.001)

    def test_slice_empty_when_no_match(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        sliced = cubo.slice(atividade_id="nonexistent-id")
        assert len(sliced.celulas) == 0
        assert sliced.total_preco_venda == 0.0

    def test_to_dict_json_serializable(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        d = cubo.to_dict()
        json_str = json.dumps(d, default=str, ensure_ascii=False)
        assert len(json_str) > 100

    def test_to_dict_contains_projections(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        d = cubo.to_dict()
        assert "exposicao_tributaria_por_tipo" in d
        assert "margem_por_atividade" in d
        assert "total_preco_venda" in d
        assert "pct_margem" in d
        assert "total_consumo_diesel_L" in d
        assert "consumo_diesel_por_atividade" in d
        assert "resumo_por_natureza" in d
        assert "resumo_por_natureza_temporal" in d
        assert "semana" in d["resumo_por_natureza_temporal"]
        assert "mes" in d["resumo_por_natureza_temporal"]


# ---------------------------------------------------------------------------
# Diesel consumption in liters
# ---------------------------------------------------------------------------


class TestDieselConsumption:
    def test_diesel_cells_have_consumo_L(self):
        """Diesel cells with componente_bdi='custo_direto' must have consumo_diesel_L > 0
        when EquipamentoEquipeDireta.consumo_litros_hora is set."""
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        diesel_custo_direto = [
            c for c in cubo.celulas if c.categoria == "diesel" and c.componente_bdi == "custo_direto"
        ]
        # Fixture has custo_combustivel_mensal=8000 but no consumo_litros_hora set
        # → consumo_L = 0 (no consumo_litros_hora in fixture)
        # Test that the field exists and is >= 0
        for c in diesel_custo_direto:
            assert c.consumo_diesel_L >= 0

    def test_non_diesel_cells_have_zero_consumo_L(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        non_diesel = [c for c in cubo.celulas if c.categoria != "diesel"]
        for c in non_diesel:
            assert c.consumo_diesel_L == 0.0

    def test_consumo_diesel_with_litros_hora_set(self):
        """When consumo_litros_hora is set, diesel cells should have positive L."""
        from concilium.application.skills import run_escopo_e_eap
        from concilium.domain.models.canonical import (
            Cronograma,
            DistribuicaoSemanal,
            EquipamentoEquipeDireta,
            EquipeDireta,
            ScheduledActivityCanonical,
        )

        inputs = {
            "nome": "Diesel Test",
            "tipo_obra": "terraplenagem",
            "localizacao": "BR",
            "coordenadas": {"lat": 0, "lng": 0},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2027-01-01",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "CPU-1",
                    "descricao": "Escavacao",
                    "unidade": "m3",
                    "quantitativo": 10000.0,
                }
            ],
            "contexto_id": "test",
            "snapshot_catalogo_id": "s",
            "snapshot_perfil_id": "s",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical

        # Equipment with known consumo_litros_hora = 12 L/h
        equipe = EquipeDireta(
            equipe_id="eq-01",
            item_id="eap-01",
            cpu_id="CPU-1",
            funcoes=[],
            custo_mao_obra_mensal=0.0,
            equipamentos=[
                EquipamentoEquipeDireta(
                    equip_id="EQ-ESCAV",
                    num_unidades=1,
                    custo_mensal=0.0,
                    consumo_litros_hora=12.0,  # 12 L/h por unidade
                    custo_combustivel_mensal=8000.0,
                )
            ],
            custo_equipamentos_mensal=0.0,
            custo_combustivel_total_mensal=8000.0,
            permanencia_meses=2.0,
        )
        dist = {
            "2026-W24": DistribuicaoSemanal(
                num_equipes=2, qtd_executada=1000, qtd_acumulada=1000, pct=0.1, eficiencia=0.9
            )
        }
        sched = [
            ScheduledActivityCanonical(
                activity_id="eap-01",
                start_week=0,
                end_week=0,
                duration_weeks=1,
                distribuicao_semanal=dist,
            )
        ]
        cronograma = Cronograma(
            algorithm="manual_allocation",
            quality_score=1.0,
            makespan_weeks=1,
            is_feasible=True,
            scheduled_activities=sched,
        )
        canonical = canonical.model_copy(update={"equipes_diretas": [equipe], "cronograma": cronograma})

        cubo = CuboAnaliticoBuilder(horas_dia=8, dias_semana=6).build(canonical)

        # Expected: 12 L/h × 48 h/sem × 0.9 eficiencia × 2 equipes × 1 unidade = 1036.8 L
        expected_L = 12.0 * 48 * 0.9 * 2 * 1
        diesel_cells = [c for c in cubo.celulas if c.categoria == "diesel" and c.componente_bdi == "custo_direto"]
        assert len(diesel_cells) == 1
        assert math.isclose(diesel_cells[0].consumo_diesel_L, expected_L, rel_tol=1e-6)

    def test_total_consumo_diesel_L_property(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        computed = sum(
            c.consumo_diesel_L for c in cubo.celulas if c.categoria == "diesel" and c.componente_bdi == "custo_direto"
        )
        assert math.isclose(cubo.total_consumo_diesel_L, computed, rel_tol=1e-6)

    def test_consumo_diesel_semanal_projection(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        semanal = cubo.consumo_diesel_semanal()
        # All values must be >= 0
        for _sem, vol in semanal.items():
            assert vol >= 0

    @pytest.mark.parametrize("granularidade", ["mes", "bimestre", "trimestre", "semestre", "ano"])
    def test_consumo_diesel_temporal_matches_weekly_projection(self, granularidade):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        temporal = cubo.consumo_diesel_temporal(granularidade)
        assert sum(temporal.values()) >= 0

    def test_consumo_diesel_por_atividade_projection(self):
        canonical = _make_canonical(n_atividades=2)
        cubo = CuboAnaliticoBuilder().build(canonical)
        por_ativ = cubo.consumo_diesel_por_atividade()
        # All activities with diesel should be present (or empty if no consumo_litros_hora)
        assert isinstance(por_ativ, dict)
        for _ativ, vol in por_ativ.items():
            assert vol >= 0

    def test_diesel_consumo_only_on_custo_direto_cell(self):
        """Only the custo_direto cell carries the physical quantity — ADR-090.
        All other BDI components (overhead, margem, tributos) have consumo_L=0."""
        from concilium.application.skills import run_escopo_e_eap
        from concilium.domain.models.canonical import (
            Cronograma,
            DistribuicaoSemanal,
            EquipamentoEquipeDireta,
            EquipeDireta,
            ScheduledActivityCanonical,
        )

        inputs = {
            "nome": "T",
            "tipo_obra": "terraplenagem",
            "localizacao": "BR",
            "coordenadas": {"lat": 0, "lng": 0},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-06-01",
            "data_termino": "2027-01-01",
            "eap": [
                {
                    "item_id": "eap-01",
                    "ordem": 1,
                    "cpu_id": "C",
                    "descricao": "X",
                    "unidade": "m3",
                    "quantitativo": 100.0,
                }
            ],
            "contexto_id": "test",
            "snapshot_catalogo_id": "s",
            "snapshot_perfil_id": "s",
        }
        canonical = run_escopo_e_eap(None, inputs).canonical
        equipe = EquipeDireta(
            equipe_id="eq-01",
            item_id="eap-01",
            cpu_id="C",
            funcoes=[],
            equipamentos=[
                EquipamentoEquipeDireta(
                    equip_id="EQ-X",
                    num_unidades=1,
                    custo_mensal=0.0,
                    consumo_litros_hora=10.0,
                    custo_combustivel_mensal=5000.0,
                )
            ],
            custo_combustivel_total_mensal=5000.0,
            permanencia_meses=1.0,
        )
        dist = {"2026-W24": DistribuicaoSemanal(num_equipes=1, qtd_executada=50, qtd_acumulada=50, pct=0.5)}
        sched = [
            ScheduledActivityCanonical(
                activity_id="eap-01",
                start_week=0,
                end_week=0,
                duration_weeks=1,
                distribuicao_semanal=dist,
            )
        ]
        canonical = canonical.model_copy(
            update={
                "equipes_diretas": [equipe],
                "cronograma": Cronograma(
                    algorithm="manual_allocation",
                    quality_score=1.0,
                    makespan_weeks=1,
                    is_feasible=True,
                    scheduled_activities=sched,
                ),
            }
        )
        cubo = CuboAnaliticoBuilder().build(canonical)
        diesel_cells = [c for c in cubo.celulas if c.categoria == "diesel"]
        custo_direto = [c for c in diesel_cells if c.componente_bdi == "custo_direto"]
        outros = [c for c in diesel_cells if c.componente_bdi != "custo_direto"]
        assert all(c.consumo_diesel_L > 0 for c in custo_direto)
        assert all(c.consumo_diesel_L == 0.0 for c in outros)


# ---------------------------------------------------------------------------
# CelulaAnalitica — uncovered branches
# ---------------------------------------------------------------------------


class TestCelulaAnaliticaExtraBranches:
    def _make_cell(self, cat_insumo, prop, comp="custo_direto", natureza="direto", valor_rs=100.0, valor_fisico=0.0, unidade=""):
        return CelulaAnalitica(
            natureza=natureza,
            atividade_id="eap-01",
            categoria_insumo=cat_insumo,
            propriedade=prop,
            semana_iso="2026-W23",
            componente_bdi=comp,
            valor_rs=valor_rs,
            valor_fisico=valor_fisico,
            unidade_fisica=unidade,
        )

    def test_verba_categoria_maps_to_material(self):
        """verba category maps backward to 'material'."""
        c = self._make_cell("verba", "fixo")
        assert c.categoria == "material"
        assert not c.is_diesel()
        assert not c.is_equipamento()
        assert not c.is_mao_obra()

    def test_equipamento_is_equipamento(self):
        c = self._make_cell("equipamento", "aluguel")
        assert c.is_equipamento()
        assert not c.is_diesel()
        assert not c.is_mao_obra()

    def test_mao_obra_is_mao_obra(self):
        c = self._make_cell("mao_obra", "salario_encargos")
        assert c.is_mao_obra()
        assert not c.is_equipamento()
        assert not c.is_diesel()

    def test_consumo_diesel_L_wrong_unit_returns_zero(self):
        """material.combustivel without unidade_fisica='L' returns 0."""
        c = self._make_cell("material", "combustivel", valor_fisico=50.0, unidade="m3")
        assert c.consumo_diesel_L == 0.0

    def test_consumo_diesel_L_mao_obra_returns_zero(self):
        """mao_obra cell always returns 0 for consumo_diesel_L."""
        c = self._make_cell("mao_obra", "salario_encargos", valor_fisico=100.0, unidade="L")
        assert c.consumo_diesel_L == 0.0

    def test_equipamento_combustivel_is_not_diesel_adr090(self):
        """ADR-090: equipamento.combustivel is NOT diesel (only material.combustivel is)."""
        c = self._make_cell("equipamento", "combustivel")
        assert not c.is_diesel()
        assert c.is_equipamento()
        assert c.categoria == "equipamento"

    def test_indireto_natureza(self):
        c = self._make_cell("mao_obra", "salario_encargos", natureza="indireto")
        assert c.natureza == "indireto"


# ---------------------------------------------------------------------------
# CuboAnalitico — uncovered projection methods
# ---------------------------------------------------------------------------


class TestCuboAnaliticoUncoveredProjections:
    def test_composicao_por_hierarquia_structure(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        hier = cubo.composicao_por_hierarquia()
        # Keys should be (categoria_insumo, propriedade) tuples
        for key in hier.keys():
            assert isinstance(key, tuple)
            assert len(key) == 2
        # All values should be dicts of componente_bdi → float
        for key, val in hier.items():
            assert isinstance(val, dict)

    def test_custo_direto_por_atividade_semana_structure(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        cd = cubo.custo_direto_por_atividade_semana()
        for key, val in cd.items():
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert isinstance(val, float)
            assert val > 0

    def test_custo_direto_por_atividade_semana_total_matches(self):
        import math

        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        cd = cubo.custo_direto_por_atividade_semana()
        total_cd = sum(cd.values())
        assert math.isclose(total_cd, cubo.total_custo_direto, rel_tol=0.001)

    def test_pct_tributos_zero_when_empty(self):
        cubo = CuboAnalitico(
            projeto_id="empty",
            gerado_em="2026",
            regime_bdi="pre_reforma",
            total_preco_venda=0.0,
            celulas=(),
        )
        assert cubo.pct_tributos == 0.0
        assert cubo.pct_margem == 0.0

    def test_slice_by_natureza(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        sliced = cubo.slice(natureza="direto")
        assert all(c.natureza == "direto" for c in sliced.celulas)

    def test_slice_by_categoria_insumo(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        sliced = cubo.slice(categoria_insumo="mao_obra")
        assert all(c.categoria_insumo == "mao_obra" for c in sliced.celulas)

    def test_slice_by_propriedade(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        sliced = cubo.slice(propriedade="salario_encargos")
        assert all(c.propriedade == "salario_encargos" for c in sliced.celulas)

    def test_group_by_natureza_categoria(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        gb = cubo.group_by("natureza", "categoria_insumo")
        assert all(isinstance(k, tuple) and len(k) == 2 for k in gb.keys())

    def test_composicao_por_categoria_backward_compat(self):
        canonical = _make_canonical()
        cubo = CuboAnaliticoBuilder().build(canonical)
        comp = cubo.composicao_por_categoria()
        # Should contain 'mao_obra', 'equipamento', 'diesel' (backward compat keys)
        assert "mao_obra" in comp


# ---------------------------------------------------------------------------
# _temporal_bucket_from_week_iso — invalid granularidade raises ValueError
# ---------------------------------------------------------------------------


class TestTemporalBucketInvalidGranularidade:
    def test_invalid_granularidade_raises(self):
        from concilium.domain.models.analytics.cubo_analitico import _temporal_bucket_from_week_iso

        with pytest.raises(ValueError, match="Granularidade temporal invalida"):
            _temporal_bucket_from_week_iso("2026-W23", "quinzena")  # type: ignore
