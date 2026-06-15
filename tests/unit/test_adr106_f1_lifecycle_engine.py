"""ADR-106 F1 — LifecycleEngine base e CustoEquipeDecomposicao.

TDD: testes escritos antes da implementação em domain/services/equipe_custo_engine.py.

Invariantes cobertos (NEP-028 IC-1 a IC-6):
  IC-3: total == soma de todos os componentes
  IC-5: idempotência — mesmo input → mesmo output
  IC-6: estratégias operam em partições disjuntas (DirectTeam vs IndirectTeam)

F1 cobre:
  - CustoEquipeDecomposicao dataclass com campos corretos e default=0.0
  - LifecycleEngine.calcular() → CustoEquipeDecomposicao
  - calcular_custo_instancia_composicional movida para o engine (compatibilidade)
  - Paridade numérica com a implementação atual em _05_equipes_custo_helpers.py
"""

from __future__ import annotations

import pytest


def _import():
    from concilium.domain.services.financial.equipe_custo_engine import (
        CustoEquipeDecomposicao,
        LifecycleEngine,
    )

    return CustoEquipeDecomposicao, LifecycleEngine


# ── CustoEquipeDecomposicao ───────────────────────────────────────────────────


class TestCustoEquipeDecomposicao:
    def test_campos_obrigatorios_existem(self):
        C, _ = _import()
        d = C(
            ativo_mo=0,
            ativo_eq=0,
            ativo_comb=0,
            ativo_mat=0,
            idle_mo=0,
            idle_eq=0,
            mob=0,
            demob=0,
            semanas_off=0,
            total=0,
        )
        for campo in (
            "ativo_mo",
            "ativo_eq",
            "ativo_comb",
            "ativo_mat",
            "idle_mo",
            "idle_eq",
            "mob",
            "demob",
            "mob_window",
            "demob_window",
            "semanas_off",
            "total",
        ):
            assert hasattr(d, campo), f"campo '{campo}' ausente"

    def test_defaults_zero(self):
        C, _ = _import()
        d = C(
            ativo_mo=0,
            ativo_eq=0,
            ativo_comb=0,
            ativo_mat=0,
            idle_mo=0,
            idle_eq=0,
            mob=0,
            demob=0,
            semanas_off=0,
            total=0,
        )
        assert d.mob_window == pytest.approx(0.0)
        assert d.demob_window == pytest.approx(0.0)

    def test_total_coerente_ic3(self):
        """IC-3: total == soma de todos os componentes de custo."""
        C, _ = _import()
        d = C(
            ativo_mo=1000,
            ativo_eq=400,
            ativo_comb=200,
            ativo_mat=100,
            idle_mo=500,
            idle_eq=80,
            mob=300,
            demob=300,
            mob_window=0,
            demob_window=0,
            semanas_off=2,
            total=1000 + 400 + 200 + 100 + 500 + 80 + 300 + 300,
        )
        esperado = d.ativo_mo + d.ativo_eq + d.ativo_comb + d.ativo_mat + d.idle_mo + d.idle_eq + d.mob + d.demob
        assert d.total == pytest.approx(esperado, abs=0.01)


# ── LifecycleEngine ───────────────────────────────────────────────────────────


class TestLifecycleEngine:
    def test_instanciavel(self):
        _, Engine = _import()
        engine = Engine()
        assert engine is not None

    def test_calcular_retorna_custo_equipe_decomposicao(self):
        C, Engine = _import()
        engine = Engine()
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=2,
            c_mo=1000,
            c_eq=400,
            c_comb=200,
            c_mat=100,
            c_idle_eq=80,
        )
        assert isinstance(result, C)

    def test_calcular_apenas_ativo(self):
        """Sem idle: total = prod_weeks × (mo + eq + comb + mat)."""
        _, Engine = _import()
        engine = Engine()
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=1000,
            c_eq=400,
            c_comb=200,
            c_mat=100,
            c_idle_eq=80,
        )
        esperado = 10 * (1000 + 400 + 200 + 100)
        assert result.total == pytest.approx(esperado, abs=0.01)
        assert result.idle_mo == pytest.approx(0.0)
        assert result.idle_eq == pytest.approx(0.0)

    def test_calcular_idle_sem_comb_mat(self):
        """Idle: MO integral + EQ reduzida; combustível e material zerados."""
        _, Engine = _import()
        engine = Engine()
        result = engine.calcular(
            prod_weeks=0,
            idle_weeks=5,
            c_mo=1000,
            c_eq=400,
            c_comb=200,
            c_mat=100,
            c_idle_eq=80,
        )
        assert result.idle_mo == pytest.approx(5 * 1000, abs=0.01)
        assert result.idle_eq == pytest.approx(5 * 80, abs=0.01)
        assert result.ativo_comb == pytest.approx(0.0)
        assert result.ativo_mat == pytest.approx(0.0)

    def test_calcular_com_mob_demob(self):
        """mob e demob somam ao total."""
        _, Engine = _import()
        engine = Engine()
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=1000,
            c_eq=400,
            c_comb=200,
            c_mat=100,
            c_idle_eq=80,
            c_mob=2000,
            c_demob=1500,
        )
        base = 10 * (1000 + 400 + 200 + 100)
        assert result.total == pytest.approx(base + 2000 + 1500, abs=0.01)
        assert result.mob == pytest.approx(2000)
        assert result.demob == pytest.approx(1500)

    def test_idempotencia_ic5(self):
        """IC-5: chamadas consecutivas com mesmo input → mesmo output."""
        _, Engine = _import()
        engine = Engine()
        kwargs = dict(prod_weeks=8, idle_weeks=3, c_mo=800, c_eq=300, c_comb=150, c_mat=80, c_idle_eq=60)
        r1 = engine.calcular(**kwargs)
        r2 = engine.calcular(**kwargs)
        assert r1.total == pytest.approx(r2.total)
        assert r1.idle_mo == pytest.approx(r2.idle_mo)

    def test_invariante_total_ic3(self):
        """IC-3: total == soma dos componentes."""
        _, Engine = _import()
        engine = Engine()
        result = engine.calcular(
            prod_weeks=12,
            idle_weeks=4,
            c_mo=1200,
            c_eq=500,
            c_comb=300,
            c_mat=150,
            c_idle_eq=100,
            c_mob=3000,
            c_demob=2000,
        )
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


# ── Paridade com implementação atual ─────────────────────────────────────────


class TestParidadeComHelperExistente:
    """Engine deve produzir mesmos números que calcular_custo_instancia_composicional atual."""

    def test_paridade_numerica(self):
        from concilium.application.skills.manifests._05_equipes_custo_helpers import (
            calcular_custo_instancia_composicional as calc_atual,
        )

        _, Engine = _import()
        engine = Engine()

        kwargs = dict(prod_weeks=10, idle_weeks=3, c_mo=1000, c_eq=400, c_comb=200, c_mat=100, c_idle_eq=80)
        atual = calc_atual(**kwargs)
        novo = engine.calcular(**kwargs)

        assert novo.ativo_mo == pytest.approx(atual["ativo_mo"], abs=0.01)
        assert novo.ativo_eq == pytest.approx(atual["ativo_eq"], abs=0.01)
        assert novo.idle_mo == pytest.approx(atual["idle_mo"], abs=0.01)
        assert novo.total == pytest.approx(atual["total"], abs=0.01)
