"""ADR-106 F2 — DirectTeamCostStrategy: parameterização de custo para equipes diretas.

TDD: testes escritos antes da implementação.

A strategy converte os campos mensais de EquipeDireta em taxas semanais e
delega para LifecycleEngine.calcular(). É o ponto de entrada canônico para
skill-05 calcular custo instancial de qualquer equipe direta.

Invariantes:
  - Converte custos mensais → semanais (÷ SEMANAS_POR_MES)
  - Retorna CustoEquipeDecomposicao com total positivo
  - IC-6: não altera campos de indiretos
"""

from __future__ import annotations

import pytest


def _import():
    from concilium.domain.services.equipe_custo_engine import (
        CustoEquipeDecomposicao,
        DirectTeamCostStrategy,
        LifecycleEngine,
    )

    return CustoEquipeDecomposicao, DirectTeamCostStrategy, LifecycleEngine


def _make_equipe(**overrides):
    from concilium.domain.models.canonical import EquipeDireta

    defaults = dict(
        item_id="i1",
        custo_total=100_000.0,
        custo_mao_obra_mensal=20_000.0,
        custo_encargos_mensal=35_540.0,  # 20k × 1.777
        custo_equipamentos_mensal=15_000.0,
        custo_combustivel_total_mensal=5_000.0,
        custo_material_mensal=1_000.0,
        permanencia_meses=5.0,
    )
    defaults.update(overrides)
    return EquipeDireta(**defaults)


class TestDirectTeamCostStrategyExiste:
    def test_importavel(self):
        _import()

    def test_instanciavel(self):
        _, Strategy, _ = _import()
        s = Strategy()
        assert s is not None

    def test_tem_metodo_calcular_para_equipe(self):
        _, Strategy, _ = _import()
        s = Strategy()
        assert hasattr(s, "calcular_para_equipe")


class TestDirectTeamCostStrategyCalculo:
    def test_retorna_custo_equipe_decomposicao(self):
        C, Strategy, _ = _import()
        s = Strategy()
        eq = _make_equipe()
        result = s.calcular_para_equipe(eq, semanas_ativas=20, semanas_idle=2)
        assert isinstance(result, C)

    def test_total_positivo(self):
        _, Strategy, _ = _import()
        s = Strategy()
        eq = _make_equipe()
        result = s.calcular_para_equipe(eq, semanas_ativas=20, semanas_idle=0)
        assert result.total > 0

    def test_conversao_mensal_para_semanal(self):
        """Custos mensais divididos por SEMANAS_POR_MES para obter taxa semanal."""
        from concilium.domain.constants import SEMANAS_POR_MES

        _, Strategy, _ = _import()
        s = Strategy()
        eq = _make_equipe(
            custo_mao_obra_mensal=10_000.0,
            custo_encargos_mensal=0.0,
            custo_equipamentos_mensal=0.0,
            custo_combustivel_total_mensal=0.0,
            custo_material_mensal=0.0,
        )
        result = s.calcular_para_equipe(eq, semanas_ativas=4, semanas_idle=0)
        # Apenas MO: 4 semanas × (10000 / SEMANAS_POR_MES)
        c_mo_semanal = 10_000.0 / SEMANAS_POR_MES
        esperado = 4 * c_mo_semanal
        assert result.total == pytest.approx(esperado, abs=1.0)

    def test_idle_cobra_mo_integral(self):
        """Durante idle: MO integral, EQ à taxa idle, combustível/material = 0."""
        _, Strategy, _ = _import()
        s = Strategy()
        eq = _make_equipe(
            custo_mao_obra_mensal=10_000.0,
            custo_encargos_mensal=0.0,
            custo_equipamentos_mensal=5_000.0,
            custo_combustivel_total_mensal=2_000.0,
            custo_material_mensal=0.0,
        )
        result = s.calcular_para_equipe(eq, semanas_ativas=0, semanas_idle=5)
        assert result.ativo_comb == pytest.approx(0.0)
        assert result.ativo_mat == pytest.approx(0.0)
        assert result.idle_mo > 0  # MO integral durante idle

    def test_invariante_total_ic3(self):
        """IC-3: total == soma de todos os componentes."""
        _, Strategy, _ = _import()
        s = Strategy()
        eq = _make_equipe()
        result = s.calcular_para_equipe(eq, semanas_ativas=15, semanas_idle=3)
        componentes = (
            result.ativo_mo
            + result.ativo_eq
            + result.ativo_comb
            + result.ativo_mat
            + result.idle_mo
            + result.idle_eq
            + result.mob
            + result.demob
            + result.mob_window
            + result.demob_window
        )
        assert abs(result.total - componentes) < 0.05

    def test_sem_atividade_retorna_zero_custo(self):
        _, Strategy, _ = _import()
        s = Strategy()
        eq = _make_equipe()
        result = s.calcular_para_equipe(eq, semanas_ativas=0, semanas_idle=0)
        assert result.total == pytest.approx(0.0, abs=0.01)
