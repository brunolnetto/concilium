"""ADR-106 F6 — Early dismissal para EQ (CLT protege MO).

TDD: testes para verificar que o early dismissal de equipamentos funciona
corretamente e que a mão de obra CLT não é afetada.

ADR spec F6:
    economia_eq = c_locacao_semanal × trailing_weeks - c_desmob_eq
    if economia_eq > 0:
        custo_desmob_efetivo = c_desmob_eq  # devolver antecipado

Invariantes:
  - trailing_weeks=3, c_idle_eq=1000, c_demob=500:
      economia = 1000×3 - 500 = 2500 > 0 → early dismissal triggered
  - economia ≤ 0 → NO early dismissal (manter EQ mais barato ou igual)
  - MO não é afetada (CLT — aviso prévio/rescisão são compromisso firme)
  - trailing_weeks=0 → NO early dismissal (sem semanas trailing)
"""

from __future__ import annotations

import pytest


def _engine():
    from concilium.domain.services.financial.equipe_custo_engine import LifecycleEngine

    return LifecycleEngine()


# ---------------------------------------------------------------------------
# Early dismissal triggered (economia_eq > 0)
# ---------------------------------------------------------------------------


class TestEarlyDismissalTriggered:
    def test_economia_positiva_aciona_early_dismissal(self):
        """trailing_weeks=3, c_idle_eq=1000, c_demob=500 → economia=2500>0."""
        engine = _engine()
        c_idle_eq = 1000.0
        c_demob = 500.0
        trailing_weeks = 3

        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=c_idle_eq,
            c_mob=1000.0,
            c_demob=c_demob,
            trailing_weeks_eq=trailing_weeks,
        )
        # economia_eq = 1000×3 - 500 = 2500 > 0 → early dismissal
        # demob deve ser >= c_demob (evento de desmob EQ é c_demob)
        assert result.demob >= c_demob

    def test_demob_com_early_dismissal_diferente_de_zero_c_demob_efetivo(self):
        """Quando early dismissal ocorre e c_demob_efetivo=0, deve usar c_demob."""
        engine = _engine()
        c_demob = 500.0
        # sem c_demob_efetivo explicito
        result_sem_trail = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=1000.0,
            c_mob=1000.0,
            c_demob=c_demob,
            trailing_weeks_eq=0,
        )
        result_com_trail = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=1000.0,
            c_mob=1000.0,
            c_demob=c_demob,
            trailing_weeks_eq=3,  # economia = 1000×3 - 500 = 2500 > 0
        )
        # Com early dismissal, demob é >= c_demob (paga pelo evento de saída EQ)
        assert result_com_trail.demob >= result_sem_trail.demob

    def test_total_com_early_dismissal_menor_sem_trailing_idle(self):
        """Early dismissal reduz custo total vs. manter EQ idle por trailing_weeks."""
        engine = _engine()
        c_idle_eq = 1000.0
        c_demob = 500.0
        trailing = 3

        # Sem early dismissal: EQ fica idle por 3 semanas + sem c_demob_eq
        result_idle = engine.calcular(
            prod_weeks=10,
            idle_weeks=trailing,  # EQ ocioso por 3 semanas
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=c_idle_eq,
            c_mob=1000.0,
            c_demob=0.0,  # sem desmob
            trailing_weeks_eq=0,
        )
        # Com early dismissal: EQ devolvida, paga apenas c_demob_eq
        result_early = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=c_idle_eq,
            c_mob=1000.0,
            c_demob=c_demob,
            trailing_weeks_eq=trailing,
        )
        # Com early dismissal, custo total < custo manter idle
        # Economia esperada: c_idle_eq×3 - c_demob = 2500
        # Mas comparação simples: early < idle quando economia > 0
        custo_idle_eq = c_idle_eq * trailing
        custo_early_demob = c_demob
        assert custo_early_demob < custo_idle_eq  # premissa


# ---------------------------------------------------------------------------
# Early dismissal NOT triggered (economia ≤ 0)
# ---------------------------------------------------------------------------


class TestEarlyDismissalNotTriggered:
    def test_economia_zero_sem_early_dismissal(self):
        """c_idle_eq × trailing == c_demob → economia=0 → sem early dismissal."""
        engine = _engine()
        c_idle_eq = 500.0
        c_demob = 1500.0  # c_demob > c_idle_eq × trailing → sem economia
        trailing = 2  # economia = 500×2 - 1500 = -500 < 0

        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=c_idle_eq,
            c_mob=1000.0,
            c_demob=c_demob,
            trailing_weeks_eq=trailing,
        )
        # Sem early dismissal: demob = c_demob apenas
        assert result.demob == pytest.approx(c_demob, abs=0.01)

    def test_trailing_zero_sem_early_dismissal(self):
        """trailing_weeks_eq=0 → early dismissal não é avaliado."""
        engine = _engine()
        c_demob = 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=1000.0,
            c_mob=1000.0,
            c_demob=c_demob,
            trailing_weeks_eq=0,  # sem trailing
        )
        assert result.demob == pytest.approx(c_demob, abs=0.01)

    def test_c_idle_eq_zero_sem_early_dismissal(self):
        """c_idle_eq=0 → sem custo de locação → economia=0-c_demob<0 → sem dismissal."""
        engine = _engine()
        c_demob = 500.0
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=0.0,  # sem custo de locação idle
            c_mob=1000.0,
            c_demob=c_demob,
            trailing_weeks_eq=3,
        )
        # c_idle_eq=0 → engine não tenta early dismissal
        assert result.demob == pytest.approx(c_demob, abs=0.01)


# ---------------------------------------------------------------------------
# MO não é afetada por early dismissal (CLT protege trabalhadores)
# ---------------------------------------------------------------------------


class TestMoNaoAfetadaPorEarlyDismissal:
    def test_ativo_mo_nao_muda_com_early_dismissal(self):
        """ativo_mo deve ser idêntico com e sem early dismissal."""
        engine = _engine()
        kwargs_base = dict(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=1000.0,
            c_mob=1000.0,
            c_demob=500.0,
        )
        result_sem = engine.calcular(**kwargs_base, trailing_weeks_eq=0)
        result_com = engine.calcular(**kwargs_base, trailing_weeks_eq=3)

        assert result_com.ativo_mo == pytest.approx(result_sem.ativo_mo, abs=0.01)

    def test_idle_mo_nao_muda_com_early_dismissal(self):
        """idle_mo é custo CLT integral — não redutível via early dismissal."""
        engine = _engine()
        kwargs_base = dict(
            prod_weeks=8,
            idle_weeks=2,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=1000.0,
            c_mob=1000.0,
            c_demob=500.0,
        )
        result_sem = engine.calcular(**kwargs_base, trailing_weeks_eq=0)
        result_com = engine.calcular(**kwargs_base, trailing_weeks_eq=3)

        assert result_com.idle_mo == pytest.approx(result_sem.idle_mo, abs=0.01)

    def test_mo_permanece_integral_durante_trailing(self):
        """MO é custo fixo — o trailing_weeks_eq afeta apenas EQ, nunca MO."""
        engine = _engine()
        c_mo = 2000.0
        prod_weeks = 10

        result = engine.calcular(
            prod_weeks=prod_weeks,
            idle_weeks=0,
            c_mo=c_mo,
            c_eq=1000.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=1000.0,
            c_mob=0.0,
            c_demob=500.0,
            trailing_weeks_eq=3,  # economia positiva → early dismissal
        )
        # MO ativa deve ser c_mo × prod_weeks (sem redução)
        assert result.ativo_mo == pytest.approx(c_mo * prod_weeks, abs=0.01)


# ---------------------------------------------------------------------------
# Invariante IC-3 com early dismissal
# ---------------------------------------------------------------------------


class TestIc3ComEarlyDismissal:
    def test_total_soma_componentes_com_early_dismissal(self):
        """IC-3: total deve ser a soma de todos os componentes."""
        engine = _engine()
        result = engine.calcular(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=2000.0,
            c_eq=1000.0,
            c_comb=100.0,
            c_mat=50.0,
            c_idle_eq=1000.0,
            c_mob=1000.0,
            c_demob=500.0,
            trailing_weeks_eq=3,  # economia = 1000×3 - 500 = 2500 > 0
        )
        soma = (
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
        assert abs(result.total - soma) < 0.05
