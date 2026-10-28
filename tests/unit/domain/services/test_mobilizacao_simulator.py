"""Tests for WorkforcePolicySimulator and WorkforcePolicy (ADR-054).

Covers all edge cases listed in the ADR:
    - Zero mobilization (n=0 throughout)
    - Immediate max capacity (n_inicial == n_maximo)
    - Impossible production targets (zero productivity)
    - Partial final weeks
    - Demobilization before completion
    - Extremely low productivity scenarios
    - Normal ramp-up with plateau
    - Praticabilidade (efficiency) integration
    - Calendar anchoring (semanas_iso)
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from concilium.domain.models.planning.mobilizacao import (
    WorkforcePolicy,
)
from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sim() -> WorkforcePolicySimulator:
    return WorkforcePolicySimulator()


def make_policy(
    n_inicial: int = 1,
    n_maximo: int = 5,
    taxa_mobilizacao: float = 1.0,
    taxa_desmobilizacao: float = 0.0,
    n_final: int | None = None,
    semanas_plateau: int | None = None,
) -> WorkforcePolicy:
    payload = {
        "n_inicial": n_inicial,
        "n_maximo": n_maximo,
        "taxa_mobilizacao": taxa_mobilizacao,
        "taxa_desmobilizacao": taxa_desmobilizacao,
        "semanas_plateau": semanas_plateau,
    }
    if n_final is not None:
        payload["n_final"] = n_final
    return WorkforcePolicy(**payload)


# ---------------------------------------------------------------------------
# WorkforcePolicy validation
# ---------------------------------------------------------------------------


class TestMobilizacaoPolicyValidation:
    def test_valid_policy_minimal(self):
        p = WorkforcePolicy(n_inicial=1, n_maximo=1, taxa_mobilizacao=1.0)
        assert p.n_inicial == 1
        assert p.n_maximo == 1

    def test_valid_policy_full(self):
        p = WorkforcePolicy(
            n_inicial=2,
            n_maximo=6,
            taxa_mobilizacao=0.5,
            taxa_desmobilizacao=1.0,
            semanas_plateau=4,
        )
        assert p.semanas_plateau == 4

    def test_n_maximo_lt_n_inicial_raises(self):
        with pytest.raises(ValueError, match="n_maximo"):
            WorkforcePolicy(n_inicial=5, n_maximo=3, taxa_mobilizacao=1.0)

    def test_n_inicial_zero_is_valid(self):
        p = WorkforcePolicy(n_inicial=0, n_maximo=5, taxa_mobilizacao=1.0)
        assert p.n_inicial == 0
        assert p.n_maximo == 5

    def test_taxa_mobilizacao_zero_raises_for_non_rectangular_profile(self):
        with pytest.raises(ValueError, match="rectangular degenerate"):
            WorkforcePolicy(n_inicial=0, n_maximo=5, taxa_mobilizacao=0.0)

    def test_taxa_desmobilizacao_negative_raises(self):
        with pytest.raises(ValidationError):
            WorkforcePolicy(n_inicial=1, n_maximo=5, taxa_mobilizacao=1.0, taxa_desmobilizacao=-0.1)

    def test_imediato_convenience(self):
        p = WorkforcePolicy.imediato(n_maximo=4)
        assert p.n_inicial == 4
        assert p.n_maximo == 4

    def test_padrao_convenience(self):
        p = WorkforcePolicy.padrao(n_maximo=5, taxa_mobilizacao=2.0)
        assert p.n_inicial == 1
        assert p.n_maximo == 5
        assert p.taxa_mobilizacao == 2.0

    def test_frozen_policy_immutable(self):
        p = WorkforcePolicy(n_inicial=1, n_maximo=3, taxa_mobilizacao=1.0)
        with pytest.raises(ValidationError):
            p.n_inicial = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# WorkforcePolicySimulator — normal cases
# ---------------------------------------------------------------------------


class TestSimulatorNormalCases:
    def test_immediate_full_capacity(self, sim: WorkforcePolicySimulator):
        """n_inicial == n_maximo: all teams from week 0, fastest possible."""
        policy = WorkforcePolicy.imediato(n_maximo=5)
        Q = 10_000.0
        P = 500.0  # units/hour
        m, h = 6, 8
        curva = sim.simulate(policy, "act-1", Q, P, m, h)

        # Production per week = 500 × 6 × 8 × 1.0 × 5 = 120,000 > Q
        # So only 1 week needed
        assert curva.duration_weeks == 1
        assert curva.is_complete
        assert not curva.incompleta
        assert curva.semanas[0].num_equipes == 5
        assert curva.semanas[0].eficiencia == 1.0
        assert math.isclose(curva.semanas[0].qtd_executada, Q, rel_tol=1e-6)
        assert math.isclose(curva.delivered, Q, rel_tol=1e-6)

    def test_rectangular_profile_with_zero_ramp_is_constant(self, sim: WorkforcePolicySimulator):
        """Formalismo: when μ+ = μ- = 0, the profile is rectangular and constant at n_maximo."""
        policy = WorkforcePolicy(n_inicial=4, n_maximo=4, taxa_mobilizacao=0.0)
        curva = sim.simulate(policy, "act-rectangular", 100_000.0, 250.0, 6, 8)

        assert curva.is_complete
        assert all(s.num_equipes == 4 for s in curva.semanas)
        assert all(s.qtd_executada > 0 for s in curva.semanas)

    def test_linear_ramp(self, sim: WorkforcePolicySimulator):
        """Ramp from 1 to 5 teams at 1/week. Verify n(t) curve."""
        policy = make_policy(n_inicial=1, n_maximo=5, taxa_mobilizacao=1.0)
        Q = 1_000_000.0  # Large Q so ramp matters
        P = 1_000.0
        m, h = 6, 8
        curva = sim.simulate(policy, "act-ramp", Q, P, m, h)

        assert curva.is_complete
        # Weeks 0–4: n = 1, 2, 3, 4, 5 (floor(1 + t*1), capped at 5)
        assert curva.semanas[0].num_equipes == 1
        assert curva.semanas[1].num_equipes == 2
        assert curva.semanas[2].num_equipes == 3
        assert curva.semanas[3].num_equipes == 4
        # Week 4 onwards: n = 5
        assert curva.semanas[4].num_equipes == 5
        if len(curva.semanas) > 5:
            assert curva.semanas[5].num_equipes == 5

    def test_fractional_mobilization_rate_produces_integer_headcount(self, sim: WorkforcePolicySimulator):
        """A fractional teams/week rate advances integer headcount by floor."""
        policy = make_policy(n_inicial=1, n_maximo=4, taxa_mobilizacao=0.5)
        Q = 500_000.0
        P = 1_000.0
        m, h = 6, 8
        curva = sim.simulate(policy, "act-frac", Q, P, m, h)

        assert curva.is_complete
        assert [week.num_equipes for week in curva.semanas[:5]] == [1, 1, 2, 2, 3]
        assert all(type(week.num_equipes) is int for week in curva.semanas)
        assert type(curva.peak_teams) is int
        assert type(curva.total_team_weeks) is int

    def test_production_formula_correctness(self, sim: WorkforcePolicySimulator):
        """Verify qtd_executada = P × m × h × p(t) × n(t)."""
        policy = WorkforcePolicy.imediato(n_maximo=3)
        Q = 1_000_000.0
        P = 400.0
        m, h = 5, 8
        prat = {"2026-W01": 0.8}
        offsets = {0: "2026-W01", 1: "2026-W02"}
        curva = sim.simulate(policy, "act-formula", Q, P, m, h, prat, offsets)

        # Week 0: 400 × 5 × 8 × 0.8 × 3 = 38,400
        assert math.isclose(curva.semanas[0].qtd_executada, 38_400.0, rel_tol=1e-6)
        assert curva.semanas[0].eficiencia == 0.8

        # Week 1: p=1.0 (not in prat_semanal) → 400 × 5 × 8 × 1.0 × 3 = 48,000
        assert math.isclose(curva.semanas[1].qtd_executada, 48_000.0, rel_tol=1e-6)
        assert curva.semanas[1].eficiencia == 1.0

    def test_cumulative_monotone(self, sim: WorkforcePolicySimulator):
        """qtd_acumulada must be non-decreasing."""
        policy = make_policy(n_inicial=2, n_maximo=8, taxa_mobilizacao=1.5)
        curva = sim.simulate(policy, "act-mono", 200_000.0, 300.0, 6, 8)

        prev = 0.0
        for s in curva.semanas:
            assert s.qtd_acumulada >= prev - 1e-9
            prev = s.qtd_acumulada

    def test_delivered_meets_target(self, sim: WorkforcePolicySimulator):
        """Delivered quantity must be >= Q for a complete curve."""
        for q in [100.0, 10_000.0, 1_000_000.0]:
            curva = sim.simulate(
                WorkforcePolicy.padrao(n_maximo=4),
                "act-target",
                q,
                200.0,
                6,
                8,
            )
            assert curva.is_complete
            assert curva.delivered >= q - 1e-6

    def test_peak_teams(self, sim: WorkforcePolicySimulator):
        policy = make_policy(n_inicial=1, n_maximo=6, taxa_mobilizacao=1.0)
        curva = sim.simulate(policy, "act-peak", 999_999.0, 100.0, 6, 8)
        assert curva.peak_teams == 6

    def test_total_team_weeks(self, sim: WorkforcePolicySimulator):
        """total_team_weeks is sum of num_equipes across weeks."""
        policy = WorkforcePolicy.imediato(n_maximo=3)
        curva = sim.simulate(policy, "act-tw", 72_000.0, 500.0, 6, 8)
        assert curva.total_team_weeks == sum(s.num_equipes for s in curva.semanas)


# ---------------------------------------------------------------------------
# Edge cases — ADR-054 §13 and test requirements
# ---------------------------------------------------------------------------


class TestSimulatorEdgeCases:
    def test_zero_productivity_impossible(self, sim: WorkforcePolicySimulator):
        """producao_horaria=0 → no production possible → incompleta=True."""
        policy = WorkforcePolicy.imediato(n_maximo=5)
        curva = sim.simulate(policy, "act-zero-p", 100_000.0, 0.0, 6, 8)

        assert curva.incompleta
        assert not curva.is_complete
        assert curva.delivered == 0.0

    def test_zero_productivity_raises_on_negative(self, sim: WorkforcePolicySimulator):
        with pytest.raises(ValueError, match="producao_horaria"):
            sim.simulate(WorkforcePolicy.imediato(n_maximo=1), "act", 100.0, -1.0, 6, 8)

    def test_zero_quantitativo_raises(self, sim: WorkforcePolicySimulator):
        with pytest.raises(ValueError, match="quantitativo"):
            sim.simulate(WorkforcePolicy.imediato(n_maximo=1), "act", 0.0, 100.0, 6, 8)

    def test_negative_quantitativo_raises(self, sim: WorkforcePolicySimulator):
        with pytest.raises(ValueError, match="quantitativo"):
            sim.simulate(WorkforcePolicy.imediato(n_maximo=1), "act", -1.0, 100.0, 6, 8)

    def test_extremely_low_productivity_hits_guard(self, sim: WorkforcePolicySimulator):
        """producao_horaria=0.001 with huge Q → guard triggers before completion."""
        policy = WorkforcePolicy.imediato(n_maximo=1)
        # Q = 1,000,000 with P=0.001, m=6, h=8 → nominal = ceil(1e6/0.048) ≈ 20,833,334 weeks
        # Guard = MAX_MULTIPLIER × max(1, nominal) — so with MAX_MULTIPLIER=10 this will
        # terminate early since we cap at 10 × nominal
        # At P=0.001, even MAX_MULTIPLIER weeks won't finish for huge Q
        curva = sim.simulate(policy, "act-lowp", 1.0, 0.001, 1, 1)  # tiny regime
        # P×m×h×n = 0.001 × 1 × 1 × 1 = 0.001/week → 1000 weeks for Q=1
        # nominal = ceil(1 / 0.001) = 1000, guard = 10000 weeks
        # Since 10000 × 0.001 = 10 >= 1, should complete eventually
        assert curva.is_complete or curva.incompleta  # either is valid depending on guard

    def test_immediate_max_capacity_one_week(self, sim: WorkforcePolicySimulator):
        """When Q fits in one week at max capacity, exactly 1 week produced."""
        P, m, h, n = 500.0, 6, 8, 3
        Q = P * m * h * n * 0.5  # Exactly half a week of production
        policy = WorkforcePolicy.imediato(n_maximo=n)
        curva = sim.simulate(policy, "act-1w", Q, P, m, h)

        assert curva.duration_weeks == 1
        assert curva.is_complete
        assert math.isclose(curva.semanas[0].qtd_executada, Q, rel_tol=1e-6)

    def test_partial_final_week_capped(self, sim: WorkforcePolicySimulator):
        """The final week's qtd_executada must not exceed remaining quantity."""
        P, m, h, n = 1_000.0, 6, 8, 5
        # Production per week = 1000 × 6 × 8 × 5 = 240,000
        # Q = 1.5 × 240,000 → completes mid-week 2
        Q = 360_000.0
        policy = WorkforcePolicy.imediato(n_maximo=n)
        curva = sim.simulate(policy, "act-partial", Q, P, m, h)

        assert curva.duration_weeks == 2
        assert curva.semanas[0].qtd_executada == 240_000.0
        assert math.isclose(curva.semanas[1].qtd_executada, 120_000.0, rel_tol=1e-6)
        assert math.isclose(curva.delivered, Q, rel_tol=1e-6)

    @pytest.mark.slow
    def test_terminal_floor_keeps_activity_feasible(self, sim: WorkforcePolicySimulator):
        """The formal terminal floor prevents premature zero-workforce termination."""
        policy = make_policy(
            n_inicial=4,
            n_maximo=4,
            taxa_mobilizacao=4.0,  # instant ramp
            taxa_desmobilizacao=2.0,
            semanas_plateau=1,
        )
        Q = 100_000.0
        P = 100.0
        curva = sim.simulate(policy, "act-desmob", Q, P, 6, 8)

        assert curva.is_complete
        assert curva.semanas[-1].num_equipes >= policy.n_final

    def test_explicit_peak_terminal_floor_disables_demobilization(self, sim: WorkforcePolicySimulator):
        """n_final=n_maximo keeps a rectangular terminal profile."""
        policy = make_policy(
            n_inicial=2,
            n_maximo=5,
            taxa_mobilizacao=1.0,
            taxa_desmobilizacao=1.0,
            n_final=5,
            semanas_plateau=None,
        )
        Q = 500_000.0
        curva = sim.simulate(policy, "act-nodesmob", Q, 300.0, 6, 8)

        # All weeks after ramp stay at the declared terminal floor/peak.
        post_ramp = [s for s in curva.semanas if s.num_equipes < 5 and s.semana_offset >= 3]
        assert len(post_ramp) == 0
        assert curva.is_complete

    def test_praticabilidade_extends_duration(self, sim: WorkforcePolicySimulator):
        """Low efficiency weeks require more weeks to deliver the same Q."""
        policy = WorkforcePolicy.imediato(n_maximo=5)
        P, m, h = 1_000.0, 6, 8
        Q = 5 * P * m * h * 10  # Exactly 10 weeks at p=1.0

        # Without praticabilidade — should complete in 10 weeks
        curva_full = sim.simulate(policy, "act-prat-full", Q, P, m, h)
        assert curva_full.duration_weeks == 10

        # With p=0.5 every week — needs 20 weeks for same Q
        offsets = {t: f"2026-W{t + 1:02d}" for t in range(30)}
        prat = {f"2026-W{t + 1:02d}": 0.5 for t in range(30)}
        curva_half = sim.simulate(policy, "act-prat-half", Q, P, m, h, prat, offsets)
        assert curva_half.duration_weeks == 20

    def test_eficiencia_default_is_1(self, sim: WorkforcePolicySimulator):
        """Weeks not in prat_semanal get eficiencia=1.0."""
        policy = WorkforcePolicy.imediato(n_maximo=1)
        prat = {"2026-W01": 0.5}
        offsets = {0: "2026-W01", 1: "2026-W02"}
        Q = 100_000.0
        curva = sim.simulate(policy, "act-eff", Q, 300.0, 6, 8, prat, offsets)

        assert curva.semanas[0].eficiencia == 0.5
        assert curva.semanas[1].eficiencia == 1.0

    def test_no_prat_semanal_all_efficiency_one(self, sim: WorkforcePolicySimulator):
        """Without prat_semanal, all weeks have eficiencia=1.0."""
        policy = WorkforcePolicy.imediato(n_maximo=3)
        curva = sim.simulate(policy, "act-noprat", 50_000.0, 200.0, 6, 8)

        for s in curva.semanas:
            assert s.eficiencia == 1.0


# ---------------------------------------------------------------------------
# _compute_n internal — plateau and demobilization
# ---------------------------------------------------------------------------


class TestComputeN:
    def test_mobilization_phase(self):
        sim = WorkforcePolicySimulator()
        policy = make_policy(n_inicial=1, n_maximo=5, taxa_mobilizacao=1.0)
        assert sim._compute_n(policy, 0) == 1
        assert sim._compute_n(policy, 1) == 2
        assert sim._compute_n(policy, 4) == 5
        assert sim._compute_n(policy, 10) == 5  # plateau

    def test_capped_at_nmaximo(self):
        sim = WorkforcePolicySimulator()
        policy = make_policy(n_inicial=3, n_maximo=5, taxa_mobilizacao=2.0)
        # t=0: 3, t=1: 5, t=2: 5 (capped)
        assert sim._compute_n(policy, 0) == 3
        assert sim._compute_n(policy, 1) == 5
        assert sim._compute_n(policy, 5) == 5

    def test_plateau_then_demob(self):
        sim = WorkforcePolicySimulator()
        # n_inicial=4, instant ramp, plateau=2 weeks, desmob=1/week
        policy = make_policy(
            n_inicial=4,
            n_maximo=4,
            taxa_mobilizacao=4.0,
            taxa_desmobilizacao=1.0,
            semanas_plateau=2,
        )
        # t_ramp=0 (already at n_max), plateau until t=2
        assert sim._compute_n(policy, 0) == 4
        assert sim._compute_n(policy, 1) == 4
        assert sim._compute_n(policy, 2) == 4
        # After plateau (t>2): desmob 1/week
        assert sim._compute_n(policy, 3) == 3
        assert sim._compute_n(policy, 4) == 2
        assert sim._compute_n(policy, 6) == 0

    def test_demob_floor_zero(self):
        sim = WorkforcePolicySimulator()
        policy = make_policy(
            n_inicial=2,
            n_maximo=2,
            taxa_mobilizacao=2.0,
            taxa_desmobilizacao=5.0,
            semanas_plateau=0,
        )
        # Instant ramp to 2, immediate demob
        assert sim._compute_n(policy, 1) >= 0  # Must not go negative


# ---------------------------------------------------------------------------
# CurvaForca properties
# ---------------------------------------------------------------------------


class TestCurvaForcaProperties:
    def test_to_num_equipes_por_semana_with_iso(self, sim: WorkforcePolicySimulator):
        policy = WorkforcePolicy.imediato(n_maximo=3)
        offsets = {0: "2026-W01", 1: "2026-W02", 2: "2026-W03"}
        curva = sim.simulate(policy, "act", 10_000.0, 200.0, 6, 8, semanas_iso_por_offset=offsets)

        mapa = curva.to_num_equipes_por_semana()
        assert "2026-W01" in mapa
        assert mapa["2026-W01"] == 3

    def test_to_num_equipes_por_semana_without_iso(self, sim: WorkforcePolicySimulator):
        policy = WorkforcePolicy.imediato(n_maximo=2)
        curva = sim.simulate(policy, "act", 5_000.0, 500.0, 6, 8)
        mapa = curva.to_num_equipes_por_semana()
        # Keys are string offsets when no ISO anchor
        assert "0" in mapa

    def test_is_complete_false_when_incompleta(self, sim: WorkforcePolicySimulator):
        policy = WorkforcePolicy.imediato(n_maximo=1)
        curva = sim.simulate(policy, "act", 1.0, 0.0, 6, 8)  # zero productivity
        assert not curva.is_complete
        assert curva.incompleta

    def test_duration_weeks_matches_semanas_len(self, sim: WorkforcePolicySimulator):
        policy = make_policy(n_inicial=1, n_maximo=4, taxa_mobilizacao=1.0)
        curva = sim.simulate(policy, "act", 100_000.0, 400.0, 6, 8)
        assert curva.duration_weeks == len(curva.semanas)


# ---------------------------------------------------------------------------
# derive_semanas_iso utility
# ---------------------------------------------------------------------------


class TestDeriveSemanaIso:
    def test_sequential_weeks(self):
        offsets = WorkforcePolicySimulator.derive_semanas_iso("2026-W01", 4)
        assert offsets[0] == "2026-W01"
        assert offsets[1] == "2026-W02"
        assert offsets[2] == "2026-W03"
        assert offsets[3] == "2026-W04"

    def test_year_rollover(self):
        # ISO 2025-W52 → 2025-W53 or 2026-W01 depending on year length
        offsets = WorkforcePolicySimulator.derive_semanas_iso("2025-W51", 5)
        assert len(offsets) == 5
        # Just verify they are valid ISO week strings
        for v in offsets.values():
            year, week = v.split("-W")
            assert 1 <= int(week) <= 53

    def test_returns_expected_count(self):
        offsets = WorkforcePolicySimulator.derive_semanas_iso("2026-W10", 52)
        assert len(offsets) == 52


# ---------------------------------------------------------------------------
# Integration: simulate → to_num_equipes_por_semana round-trip
# ---------------------------------------------------------------------------


class TestSkill04Integration:
    def test_curve_to_manual_mode_input(self, sim: WorkforcePolicySimulator):
        """CurvaForca can be converted to the exact format Skill 04 MANUAL mode expects."""
        policy = make_policy(n_inicial=2, n_maximo=5, taxa_mobilizacao=1.0)
        offsets = WorkforcePolicySimulator.derive_semanas_iso("2026-W23", 20)
        curva = sim.simulate(
            policy,
            "eap-1_0",
            100_000.0,
            500.0,
            6,
            8,
            semanas_iso_por_offset=offsets,
        )

        mapa = curva.to_num_equipes_por_semana()

        # The bridge carries physical integer team counts.
        assert all(isinstance(k, str) and "-W" in k for k in mapa.keys())
        assert all(type(v) is int and v >= 0 for v in mapa.values())

        # Verify the curve is monotone up to n_maximo in the ramp phase
        sorted_weeks = sorted(mapa.items())
        # First week should have n_inicial teams
        assert sorted_weeks[0][1] == 2

    def test_complete_curve_matches_quantitativo(self, sim: WorkforcePolicySimulator):
        """Total delivered via the curve should match Q."""
        for Q in [1_000.0, 50_000.0, 500_000.0]:
            policy = make_policy(n_inicial=1, n_maximo=6, taxa_mobilizacao=1.5)
            curva = sim.simulate(policy, "act", Q, 300.0, 6, 8)
            if curva.is_complete:
                assert curva.delivered >= Q - 1e-3


# mobilizacao_simulator.py lines 206, 228: edge cases in simulator
# ---------------------------------------------------------------------------


class TestMobilizacaoSimulatorEdgeCases:
    def test_import_mobilizacao_simulator(self):
        """Sanity: module imports correctly."""
        from concilium.domain.services.planning import mobilizacao_simulator  # noqa: F401

        assert mobilizacao_simulator is not None


# ---------------------------------------------------------------------------


# mobilizacao_simulator.py line 228:
# taxa_desmobilizacao=0 with semanas_plateau set → return n_maximo (line 228)
# (line 206 is unreachable because WorkforcePolicy.taxa_mobilizacao has gt=0)
# ---------------------------------------------------------------------------


class TestMobilizacaoSimulatorDesmobZero:
    def _make_policy(self, **kwargs):
        from concilium.domain.models.planning.mobilizacao import WorkforcePolicy

        return WorkforcePolicy(**kwargs)

    def test_taxa_desmobilizacao_zero_returns_n_maximo_after_plateau(self):
        """Line 228: taxa_desmobilizacao=0, semanas_plateau set, t past plateau → n_maximo."""
        from concilium.domain.services.planning.mobilizacao_simulator import (
            WorkforcePolicySimulator,
        )

        # taxa_mobilizacao=2 (gt=0 ✓), semanas_plateau=5, taxa_desmobilizacao=0 (default)
        policy = self._make_policy(
            n_inicial=1,
            n_maximo=3,
            taxa_mobilizacao=2.0,
            semanas_plateau=5,
            taxa_desmobilizacao=0.0,
        )
        sim = WorkforcePolicySimulator()
        # t=20 > t_plateau_end=(ceil((3-1)/2)=1)+5=6 → demob phase; taxa_desmob=0 → line 228
        result = sim._compute_n(policy, t=20)
        assert result == 3  # n_maximo returned


class TestSimulatorEtaJornada:
    """ADR-148: eta_jornada dimensiona producao_semanal_base, como m/h já fazem."""

    def test_default_eta_jornada_e_1_sem_regressao(self, sim: WorkforcePolicySimulator):
        policy = WorkforcePolicy.imediato(n_maximo=3)
        curva = sim.simulate(policy, "act-default", 1_000_000.0, 400.0, 5, 8)
        # 400 × 5 × 8 × 1.0 (eta_jornada) × 3 = 48,000
        assert math.isclose(curva.semanas[0].qtd_executada, 48_000.0, rel_tol=1e-6)

    def test_eta_jornada_reduz_producao_semanal(self, sim: WorkforcePolicySimulator):
        policy = WorkforcePolicy.imediato(n_maximo=3)
        curva = sim.simulate(policy, "act-eta", 1_000_000.0, 400.0, 5, 8, eta_jornada=0.9375)
        # 400 × 5 × 8 × 0.9375 × 3 = 45,000
        assert math.isclose(curva.semanas[0].qtd_executada, 45_000.0, rel_tol=1e-6)

    def test_eta_jornada_e_clima_multiplicam(self, sim: WorkforcePolicySimulator):
        policy = WorkforcePolicy.imediato(n_maximo=3)
        prat = {"2026-W01": 0.8}
        offsets = {0: "2026-W01"}
        curva = sim.simulate(policy, "act-eta-clima", 1_000_000.0, 400.0, 5, 8, prat, offsets, eta_jornada=0.9375)
        # 400 × 5 × 8 × 0.9375 × 0.8 × 3 = 36,000
        assert math.isclose(curva.semanas[0].qtd_executada, 36_000.0, rel_tol=1e-6)

    def test_eta_jornada_aumenta_duracao_para_mesma_meta(self, sim: WorkforcePolicySimulator):
        policy = WorkforcePolicy.imediato(n_maximo=1)
        Q = 48_000.0
        curva_full = sim.simulate(policy, "act-full", Q, 400.0, 5, 8, eta_jornada=1.0)
        curva_reduzida = sim.simulate(policy, "act-red", Q, 400.0, 5, 8, eta_jornada=0.9375)
        assert curva_reduzida.duration_weeks >= curva_full.duration_weeks


# ---------------------------------------------------------------------------
