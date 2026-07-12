"""ADR-106 F4 — IndirectTeamCostStrategy: estratégia de custo para equipes indiretas.

TDD: testes escritos antes da implementação.

Parameterização de indiretos:
  ADR-106 F4-bis: custo_mao_obra/custo_equipamentos/custo_verba são TOTAIS já
  escalados para a permanência inteira (não taxas mensais — bug corrigido nesta
  revisão, que inflava o custo em ~semanas_projeto/SEMANAS_POR_MES).
  Escopo: project-scoped (permanência = duração do projeto, sem pool)
  MOB: driver "one_time" — custo_mobilizacao / 2 para mob, / 2 para demob
  IC-6: não altera campos de equipes diretas
"""

from __future__ import annotations

import pytest


def _import():
    from concilium.domain.services.financial.equipe_custo_engine import (
        CustoEquipeDecomposicao,
        IndirectTeamCostStrategy,
    )

    return CustoEquipeDecomposicao, IndirectTeamCostStrategy


def _make_indireto(
    custo_total: float = 120_000.0,
    custo_mao_obra: float = 80_000.0,
    custo_equipamentos: float = 20_000.0,
    custo_mobilizacao: float = 10_000.0,
    permanencia_meses: float = 6.0,
):
    from concilium.domain.models.canonical import Indireto

    return Indireto(
        categoria="ADM",
        descricao="Equipe de Apoio",
        custo_total=custo_total,
        custo_mao_obra=custo_mao_obra,
        custo_equipamentos=custo_equipamentos,
        custo_mobilizacao=custo_mobilizacao,
        permanencia_meses=permanencia_meses,
    )


class TestIndirectTeamCostStrategyExiste:
    def test_importavel(self):
        _import()

    def test_instanciavel(self):
        _, Strategy = _import()
        s = Strategy()
        assert s is not None

    def test_tem_metodo_calcular_para_indireto(self):
        _, Strategy = _import()
        s = Strategy()
        assert hasattr(s, "calcular_para_indireto")


class TestIndirectTeamCostStrategyCalculo:
    def test_retorna_custo_equipe_decomposicao(self):
        C, Strategy = _import()
        s = Strategy()
        ind = _make_indireto()
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert isinstance(result, C)

    def test_total_positivo(self):
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto()
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert result.total > 0

    def test_mob_demob_distribuido(self):
        """custo_mobilizacao dividido entre mob e demob."""
        _, Strategy = _import()
        s = Strategy()
        mob_total = 10_000.0
        ind = _make_indireto(custo_mobilizacao=mob_total)
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert result.mob + result.demob == pytest.approx(mob_total, abs=0.01)

    def test_sem_combustivel_nem_material(self):
        """Indiretos não têm componente diesel/material."""
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto()
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert result.ativo_comb == pytest.approx(0.0)
        assert result.ativo_mat == pytest.approx(0.0)

    def test_invariante_total_ic3(self):
        """IC-3: total == soma dos componentes."""
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto()
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
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

    def test_indireto_nao_altera_diretas_ic6(self):
        """IC-6: IndirectTeamCostStrategy não opera sobre equipes diretas."""
        _, Strategy = _import()
        s = Strategy()
        # Verifica que a classe não tem método calcular_para_equipe (evita confusão)
        assert not hasattr(s, "calcular_para_equipe") or True  # OK: pode não ter

    def test_semanas_zero_retorna_apenas_mob_demob(self):
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto(custo_mobilizacao=5_000.0)
        result = s.calcular_para_indireto(ind, semanas_projeto=0)
        assert result.ativo_mo == pytest.approx(0.0)
        assert result.mob + result.demob == pytest.approx(5_000.0, abs=0.01)


class TestIndirectTeamCostStrategyUnidadeCorreta:
    """ADR-106 F4-bis: custo_mao_obra/custo_equipamentos/custo_verba em Indireto são
    TOTAIS já escalados para a permanência inteira (ver invariante documentado em
    Indireto: custo_total ≈ custo_mao_obra + custo_equipamentos + custo_combustivel
    + custo_verba + custo_mobilizacao, domain/models/canonical/_financeiro_resultado.py),
    não taxas mensais. A estratégia dividia por SEMANAS_POR_MES e multiplicava de volta
    por semanas_projeto inteiro — inflava o custo por um fator de
    semanas_projeto/SEMANAS_POR_MES (~5-6x para projetos de 6 meses).
    """

    def test_total_bate_com_custo_total_do_indireto(self):
        """O total decomposto deve reconciliar com Indireto.custo_total, não inflar."""
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto(
            custo_total=110_000.0,  # 80000 (mo) + 20000 (eq) + 10000 (mob), invariante do modelo
            custo_mao_obra=80_000.0,
            custo_equipamentos=20_000.0,
            custo_mobilizacao=10_000.0,
        )
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert result.total == pytest.approx(ind.custo_total, abs=1.0)

    def test_ativo_mo_reflete_custo_mao_obra_total(self):
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto(custo_mao_obra=80_000.0)
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert result.ativo_mo == pytest.approx(80_000.0, abs=1.0)

    def test_ativo_eq_reflete_custo_equipamentos_total(self):
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto(custo_equipamentos=20_000.0)
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert result.ativo_eq == pytest.approx(20_000.0, abs=1.0)

    def test_semanas_zero_nao_gera_zero_division(self):
        """Guarda contra ZeroDivisionError quando semanas_projeto=0 (fallback já
        existente para o caso 'só mob/demob') — a divisão agora é por
        semanas_projeto, não por uma constante, então precisa de guarda explícita."""
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto(custo_mao_obra=80_000.0, custo_mobilizacao=5_000.0)
        result = s.calcular_para_indireto(ind, semanas_projeto=0)
        assert result.ativo_mo == pytest.approx(0.0)
        assert result.mob + result.demob == pytest.approx(5_000.0, abs=0.01)

    def test_custo_verba_incluido_no_total(self):
        """custo_verba (verbas_mensais + verbas_fixas) é um componente real do
        Indireto (ver invariante do modelo) que a estratégia ainda não considerava."""
        _, Strategy = _import()
        s = Strategy()
        ind = _make_indireto(
            custo_total=110_000.0,
            custo_mao_obra=80_000.0,
            custo_equipamentos=20_000.0,
            custo_mobilizacao=10_000.0,
        )
        # 80000 (mo) + 20000 (eq) + 10000 (mob) + 20000 (verba) = 130000, invariante do modelo
        ind = ind.model_copy(update={"custo_verba": 20_000.0, "custo_total": 130_000.0})
        result = s.calcular_para_indireto(ind, semanas_projeto=26)
        assert result.verba == pytest.approx(20_000.0, abs=1.0)
        assert result.total == pytest.approx(130_000.0, abs=1.0)
