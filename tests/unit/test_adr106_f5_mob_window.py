"""ADR-106 F5 — Mob window e demob window no LifecycleEngine.

TDD: testes escritos para verificar que leadtime_mob_semanas e lag_demob_semanas
calculam corretamente as janelas de mobilização e desmobilização.

ADR spec F5:
    custo_mob_window = (c_mo + c_eq) × leadtime_mob_semanas   (sem comb, sem mat)
    custo_demob_window = (c_mo + c_eq) × lag_demob_semanas

Invariantes:
  - leadtime=0, lag=0 → mob_window=0, demob_window=0 (backward compat)
  - leadtime=2: mob_window = (c_mo + c_eq) × 2
  - lag=1: demob_window = (c_mo + c_eq) × 1
  - total = ativo + idle + mob + demob + mob_window + demob_window (IC-3)
  - Combustível e material NÃO incluídos nas janelas (recursos em trânsito, sem produção)
"""

from __future__ import annotations

import pytest


def _engine():
    from concilium.domain.services.equipe_custo_engine import LifecycleEngine

    return LifecycleEngine()


def _constants():
    from concilium.domain.constants import DEFAULT_LAG_DEMOB_SEMANAS, DEFAULT_LEADTIME_MOB_SEMANAS

    return DEFAULT_LEADTIME_MOB_SEMANAS, DEFAULT_LAG_DEMOB_SEMANAS


# ---------------------------------------------------------------------------
# Constantes padrão (ADR-106 F5)
# ---------------------------------------------------------------------------


class TestConstantesPadrao:
    def test_constantes_existem(self):
        lead, lag = _constants()
        assert lead is not None
        assert lag is not None

    def test_leadtime_default_e_2(self):
        lead, _ = _constants()
        assert lead == 2

    def test_lag_default_e_1(self):
        _, lag = _constants()
        assert lag == 1


# ---------------------------------------------------------------------------
# Backward compat: sem janelas (leadtime=0, lag=0)
# ---------------------------------------------------------------------------


class TestSemJanelas:
    def test_mob_window_zero_sem_leadtime(self):
        engine = _engine()
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=1000.0,
            c_eq=500.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=500.0,
            leadtime_mob_semanas=0,
            lag_demob_semanas=0,
        )
        assert result.mob_window == pytest.approx(0.0)
        assert result.demob_window == pytest.approx(0.0)

    def test_total_sem_janelas_igual_ativo_mais_mob_demob(self):
        engine = _engine()
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=2,
            c_mo=1000.0,
            c_eq=500.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=300.0,
            c_mob=2000.0,
            c_demob=1500.0,
            leadtime_mob_semanas=0,
            lag_demob_semanas=0,
        )
        esperado = (
            10 * (1000.0 + 500.0 + 200.0 + 100.0)  # ativo
            + 2 * 1000.0  # idle_mo
            + 2 * 300.0  # idle_eq
            + 2000.0  # mob
            + 1500.0  # demob
        )
        assert result.total == pytest.approx(esperado, abs=0.05)


# ---------------------------------------------------------------------------
# Mob window com leadtime > 0
# ---------------------------------------------------------------------------


class TestMobWindow:
    def test_mob_window_com_leadtime_2(self):
        """mob_window = (c_mo + c_eq) × 2 quando leadtime=2."""
        engine = _engine()
        c_mo = 1000.0
        c_eq = 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=500.0,
            leadtime_mob_semanas=2,
            lag_demob_semanas=0,
        )
        esperado_mob_window = (c_mo + c_eq) * 2
        assert result.mob_window == pytest.approx(esperado_mob_window, abs=0.01)

    def test_mob_window_sem_combustivel_nem_material(self):
        """Janela de mob não inclui combustível nem material (recursos em trânsito)."""
        engine = _engine()
        c_mo = 1000.0
        c_eq = 500.0
        c_comb = 300.0
        c_mat = 150.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=c_comb,
            c_mat=c_mat,
            c_idle_eq=500.0,
            leadtime_mob_semanas=2,
            lag_demob_semanas=0,
        )
        # Janela deve ser (c_mo + c_eq) × 2, sem c_comb e sem c_mat
        esperado = (c_mo + c_eq) * 2
        assert result.mob_window == pytest.approx(esperado, abs=0.01)
        # Verificar que c_comb e c_mat NÃO foram incluídos
        assert result.mob_window < (c_mo + c_eq + c_comb + c_mat) * 2

    def test_mob_window_com_leadtime_1(self):
        engine = _engine()
        c_mo = 800.0
        c_eq = 400.0
        result = engine.calcular(
            prod_weeks=5,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=100.0,
            c_mat=50.0,
            c_idle_eq=400.0,
            leadtime_mob_semanas=1,
        )
        assert result.mob_window == pytest.approx((c_mo + c_eq) * 1, abs=0.01)

    def test_mob_window_proporcional_ao_leadtime(self):
        """mob_window escala linearmente com leadtime_mob_semanas."""
        engine = _engine()
        c_mo, c_eq = 1000.0, 500.0

        r2 = engine.calcular(
            prod_weeks=10, idle_weeks=0, c_mo=c_mo, c_eq=c_eq,
            c_comb=0, c_mat=0, c_idle_eq=c_eq, leadtime_mob_semanas=2,
        )
        r4 = engine.calcular(
            prod_weeks=10, idle_weeks=0, c_mo=c_mo, c_eq=c_eq,
            c_comb=0, c_mat=0, c_idle_eq=c_eq, leadtime_mob_semanas=4,
        )
        assert r4.mob_window == pytest.approx(r2.mob_window * 2, abs=0.01)


# ---------------------------------------------------------------------------
# Demob window com lag > 0
# ---------------------------------------------------------------------------


class TestDemobWindow:
    def test_demob_window_com_lag_1(self):
        """demob_window = (c_mo + c_eq) × 1 quando lag=1."""
        engine = _engine()
        c_mo = 1000.0
        c_eq = 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=500.0,
            leadtime_mob_semanas=0,
            lag_demob_semanas=1,
        )
        esperado_demob_window = (c_mo + c_eq) * 1
        assert result.demob_window == pytest.approx(esperado_demob_window, abs=0.01)

    def test_demob_window_sem_combustivel_nem_material(self):
        engine = _engine()
        c_mo = 1000.0
        c_eq = 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=300.0,
            c_mat=150.0,
            c_idle_eq=500.0,
            lag_demob_semanas=2,
        )
        assert result.demob_window == pytest.approx((c_mo + c_eq) * 2, abs=0.01)


# ---------------------------------------------------------------------------
# Total IC-3: inclui janelas
# ---------------------------------------------------------------------------


class TestTotalComJanelas:
    def test_total_inclui_mob_window(self):
        """IC-3: total deve incluir mob_window."""
        engine = _engine()
        c_mo, c_eq = 1000.0, 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=500.0,
            leadtime_mob_semanas=2,
            lag_demob_semanas=0,
        )
        mob_window_esperada = (c_mo + c_eq) * 2
        ativo = 10 * (c_mo + c_eq)
        assert result.total == pytest.approx(ativo + mob_window_esperada, abs=0.01)

    def test_total_inclui_demob_window(self):
        engine = _engine()
        c_mo, c_eq = 1000.0, 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=500.0,
            lag_demob_semanas=1,
        )
        demob_window_esperada = (c_mo + c_eq) * 1
        ativo = 10 * (c_mo + c_eq)
        assert result.total == pytest.approx(ativo + demob_window_esperada, abs=0.01)

    def test_total_inclui_ambas_janelas(self):
        """total = ativo + idle + mob + demob + mob_window + demob_window."""
        engine = _engine()
        c_mo, c_eq, c_comb, c_mat = 1000.0, 500.0, 200.0, 100.0
        c_idle_eq = 300.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=2,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=c_comb,
            c_mat=c_mat,
            c_idle_eq=c_idle_eq,
            c_mob=2000.0,
            c_demob=1000.0,
            leadtime_mob_semanas=2,
            lag_demob_semanas=1,
        )
        mob_window = (c_mo + c_eq) * 2
        demob_window = (c_mo + c_eq) * 1
        ativo = 10 * (c_mo + c_eq + c_comb + c_mat)
        idle = 2 * c_mo + 2 * c_idle_eq
        esperado = ativo + idle + 2000.0 + 1000.0 + mob_window + demob_window
        assert result.total == pytest.approx(esperado, abs=0.05)

    def test_ic3_invariante_total_soma_componentes(self):
        """IC-3: total == soma dos componentes."""
        engine = _engine()
        result = engine.calcular(
            prod_weeks=8,
            idle_weeks=3,
            c_mo=1200.0,
            c_eq=600.0,
            c_comb=150.0,
            c_mat=80.0,
            c_idle_eq=400.0,
            c_mob=3000.0,
            c_demob=2000.0,
            leadtime_mob_semanas=2,
            lag_demob_semanas=1,
        )
        soma_componentes = (
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
        assert abs(result.total - soma_componentes) < 0.05


# ---------------------------------------------------------------------------
# Precedência: leadtime/lag sobrescreve mob_window/demob_window pré-calculado
# ---------------------------------------------------------------------------


class TestPrecedencia:
    def test_leadtime_sobrescreve_mob_window_precalculado(self):
        """Quando leadtime_mob_semanas > 0, recalcula mob_window mesmo que mob_window != 0."""
        engine = _engine()
        c_mo, c_eq = 1000.0, 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=c_eq,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=c_eq,
            mob_window=99999.0,  # valor que seria sobrescrito
            leadtime_mob_semanas=2,
        )
        assert result.mob_window == pytest.approx((c_mo + c_eq) * 2, abs=0.01)
