"""ADR-106 F1 — LifecycleEngine base e CustoEquipeDecomposicao.

TDD: testes escritos antes da implementação em domain/services/equipe_custo_engine.py.

Invariantes cobertos (NEP-028 IC-1 a IC-6):
  IC-3: total == soma de todos os componentes
  IC-5: idempotência — mesmo input → mesmo output
  IC-6: estratégias operam em partições disjuntas (DirectTeam vs IndirectTeam)

F1 cobre:
  - CustoEquipeDecomposicao dataclass com campos corretos e default=0.0
  - LifecycleEngine.calcular() → CustoEquipeDecomposicao

ADR-136 F5: calcular_custo_instancia_composicional (05-equipes-e-alocacao/
_skill_helpers/_custo_diferenciado_permanencia.py) foi consolidada neste engine —
_compute_instancia_lifecycle (skill-05) chama LifecycleEngine.calcular() diretamente.
Testes de regressão numérica fixam os valores que antes eram comparados ao vivo
contra a implementação duplicada, agora removida.
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


class TestRegressaoNumericaConsolidacao:
    """ADR-136 F5: LifecycleEngine consolidou calcular_custo_instancia_composicional
    (05-equipes-e-alocacao/_skill_helpers/_custo_diferenciado_permanencia.py), removida
    após confirmação de paridade numérica exata (inclusive com mob/demob efetivos) —
    ver commit de consolidação. Estes testes fixam os valores esperados como regressão,
    já que não há mais uma segunda implementação para comparar ao vivo.
    """

    def test_regressao_numerica_produtivo_e_idle(self):
        _, Engine = _import()
        dec = Engine().calcular(prod_weeks=10, idle_weeks=3, c_mo=1000, c_eq=400, c_comb=200, c_mat=100, c_idle_eq=80)

        assert dec.ativo_mo == pytest.approx(10000.0)
        assert dec.ativo_eq == pytest.approx(4000.0)
        assert dec.idle_mo == pytest.approx(3000.0)
        assert dec.total == pytest.approx(20240.0)

    def test_regressao_numerica_com_mob_demob(self):
        """Caso com mob/demob efetivos (não só o produtivo/idle trivial)."""
        _, Engine = _import()
        dec = Engine().calcular(
            prod_weeks=6,
            idle_weeks=2,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=80.0,
            c_mob=1800.0,
            c_demob_efetivo=2500.0,
        )

        assert dec.mob == pytest.approx(1800.0)
        assert dec.demob == pytest.approx(2500.0)
        assert dec.total == pytest.approx(16660.0)


# ── ADR-125: hierarquia C_prod / C_pool / total ──────────────────────────────


class TestCustoProdutivo:
    """ADR-125 — C_prod ≤ C_pool ≤ total.

    C_prod  = semanas ativas (base de γ_i)
    C_pool  = ativo + ocioso, sem mob/demob (base de p_i^o = C_pool / Q)
    total   = C_pool + mob + demob + windows (custo contratual completo)
    mob/demob → custos indiretos (BDI/DI)
    """

    def test_custo_produtivo_somente_ativo(self):
        """C_prod = semanas ativas — idle (κ) não é produção."""
        _, Engine = _import()
        result = Engine().calcular(
            prod_weeks=10,
            idle_weeks=3,
            c_mo=1000,
            c_eq=400,
            c_comb=200,
            c_mat=100,
            c_idle_eq=80,
        )
        esperado = 10 * (1000 + 400 + 200 + 100)
        assert result.custo_produtivo == pytest.approx(esperado, abs=0.01)

    def test_custo_pool_inclui_idle(self):
        """C_pool = C_prod + idle (CLT irredutível, κ aplicado ao equipamento)."""
        _, Engine = _import()
        result = Engine().calcular(
            prod_weeks=10,
            idle_weeks=3,
            c_mo=1000,
            c_eq=400,
            c_comb=0,
            c_mat=0,
            c_idle_eq=80,
        )
        assert result.custo_pool == pytest.approx(
            result.custo_produtivo + result.idle_mo + result.idle_eq,
            abs=0.01,
        )

    def test_custo_pool_exclui_mob_demob(self):
        """C_pool não inclui mob/demob (custos indiretos de canteiro)."""
        _, Engine = _import()
        result = Engine().calcular(
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
        assert result.custo_pool == pytest.approx(result.custo_produtivo, abs=0.01)
        assert result.total == pytest.approx(result.custo_pool + 2000 + 1500, abs=0.01)

    def test_hierarquia_c_prod_le_c_pool_le_total(self):
        """Invariante ADR-125: C_prod ≤ C_pool ≤ total."""
        _, Engine = _import()
        result = Engine().calcular(
            prod_weeks=8,
            idle_weeks=2,
            c_mo=800,
            c_eq=300,
            c_comb=0,
            c_mat=0,
            c_idle_eq=60,
            c_mob=3000,
            c_demob=3000,
        )
        assert result.custo_produtivo <= result.custo_pool
        assert result.custo_pool <= result.total

    def test_custo_pool_exclui_mob_window(self):
        """Janelas de mob/demob (leadtime/lag) também são indiretos — excluídas de C_pool."""
        _, Engine = _import()
        result = Engine().calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=1000,
            c_eq=400,
            c_comb=0,
            c_mat=0,
            c_idle_eq=400,
            c_mob=1000,
            c_demob=1000,
            leadtime_mob_semanas=2,
            lag_demob_semanas=1,
        )
        assert result.mob_window > 0
        assert result.demob_window > 0
        assert result.custo_pool == pytest.approx(result.custo_produtivo, abs=0.01)
        assert result.total == pytest.approx(
            result.custo_pool + result.mob + result.demob + result.mob_window + result.demob_window,
            abs=0.01,
        )
