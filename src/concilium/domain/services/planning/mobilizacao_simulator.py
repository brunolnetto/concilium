"""WorkforcePolicySimulator — pure deterministic domain service (ADR-054).

All assumptions are explicit; no global state; no I/O.

Production formula (shared with Skill 04, invariant):
    q(t) = min(Q_remaining, F(n(t)) × H × eta_jornada × p(t) × c(t))

Where:
    P           = producao_horaria (units/hour per independent front)
    F(n)        = optional physical graph capacity function for mobilized teams
    m           = dias_semana (working days/week, from regime)
    h           = horas_dia  (working hours/day, from regime)
    eta_jornada = ADR-148 fração produtiva do dia (structural, not week-varying), defaults to 1.0
    p(t)        = practicability in [0,1], defaults to 1.0
    c(t)        = operating calendar availability in [0,1], defaults to 1.0
    n(t)        = teams active in week t, derived from WorkforcePolicy

Termination:
    SUCCESS  — cumulative production >= quantitativo_alvo
    INFEASIBLE — MAX_MULTIPLIER * nominal_weeks elapsed without success
               (e.g., zero productivity, demobilization before completion)

Partial final week:
    qtd_executada in the last week is capped at the remaining quantity.
    The week is counted as a full week for cost purposes (duration_weeks = len(semanas)).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import ClassVar

from concilium.domain.models.planning.mobilizacao import (
    CurvaForca,
    CurvaForcaSemanal,
    WorkforcePolicy,
)
from concilium.domain.services.planning.produtividade import produtividade_realizavel


class WorkforcePolicySimulator:
    """Derives execution timeline and weekly team curve from a mobilization policy.

    Usage:
        sim = WorkforcePolicySimulator()
        curve = sim.simulate(
            policy=WorkforcePolicy(n_inicial=2, n_maximo=5, taxa_mobilizacao=1.0),
            atividade_id="eap-1_0",
            quantitativo=100_000.0,
            producao_horaria=500.0,
            dias_semana=6,
            horas_dia=8,
        )
        print(curve.duration_weeks, curve.is_complete)
    """

    # Safety guard: simulation terminates after this multiple of the nominal
    # minimum weeks (computed at n_maximo, p=1.0). Prevents infinite loops when
    # productivity is severely degraded by praticabilidade.
    MAX_MULTIPLIER: ClassVar[int] = 10

    def simulate(
        self,
        policy: WorkforcePolicy,
        atividade_id: str,
        quantitativo: float,
        producao_horaria: float,
        dias_semana: int,
        horas_dia: int,
        prat_semanal: dict[str, float] | None = None,
        semanas_iso_por_offset: dict[int, str] | None = None,
        eta_jornada: float = 1.0,
        capacidade_horaria_por_frentes: Callable[[float], float] | None = None,
        calendario_semanal: dict[str, float] | None = None,
    ) -> CurvaForca:
        """Simulate the execution of one activity under the given policy.

        Args:
            policy: Mobilization policy (immutable value object).
            atividade_id: Activity identifier — stored in result for audit.
            quantitativo: Q — total quantity to be delivered (must be > 0).
            producao_horaria: P — production rate in units/hour per team (>= 0).
            dias_semana: m — working days per week.
            horas_dia: h — working hours per day.
            prat_semanal: Optional map {ISO_week: float} of practicability factors.
                          Entries not found default to 1.0 (no weather constraint).
            semanas_iso_por_offset: Optional map {week_offset: ISO_week_key}.
                          Anchors the simulation to calendar weeks so that
                          prat_semanal lookup works correctly.
            calendario_semanal: Optional ISO-week calendar availability (default 1.0).
            capacidade_horaria_por_frentes: optional F(n) in units/hour; if supplied,
                          it replaces the per-front P*n assumption everywhere.
        eta_jornada: ADR-148 — fração produtiva do dia, (horas_dia - horas_improdutivas_dia) /
                          horas_dia. Determinístico/estrutural (não semanal como prat_semanal),
                          por isso dimensiona producao_semanal_base diretamente.

        Returns:
            CurvaForca: complete (or incomplete) simulation result.

        Raises:
            ValueError: if quantitativo <= 0 or producao_horaria < 0.
        """
        self._validate_simulate_inputs(quantitativo, producao_horaria)

        horas_efetivas = dias_semana * horas_dia * eta_jornada
        if capacidade_horaria_por_frentes is None:
            peak_hourly = producao_horaria * policy.n_maximo
        else:
            peak_hourly = capacidade_horaria_por_frentes(float(policy.n_maximo))
        if not math.isfinite(peak_hourly) or peak_hourly < 0:
            raise ValueError("physical peak F(m_max) must be finite and nonnegative")
        # Nominal guard uses the actual installed peak, never P * m_max
        # when P is already calibrated to the graph's whole composition.
        producao_semanal_base = peak_hourly * horas_efetivas / policy.n_maximo
        max_weeks = self._compute_max_weeks(producao_semanal_base, quantitativo, policy)

        semanas, incompleta = self._simulate_weeks(
            policy,
            quantitativo,
            producao_semanal_base,
            max_weeks,
            prat_semanal,
            semanas_iso_por_offset,
            capacidade_horaria_por_frentes=capacidade_horaria_por_frentes,
            horas_efetivas=horas_efetivas,
            calendario_semanal=calendario_semanal,
        )

        return CurvaForca(
            atividade_id=atividade_id,
            quantitativo_alvo=quantitativo,
            producao_horaria=producao_horaria,
            dias_semana=dias_semana,
            horas_dia=horas_dia,
            policy=policy,
            semanas=semanas,
            incompleta=incompleta,
        )

    # ------------------------------------------------------------------
    # Internal helpers — pure functions, no side effects
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_simulate_inputs(quantitativo: float, producao_horaria: float) -> None:
        if quantitativo <= 0:
            raise ValueError(f"quantitativo must be > 0, got {quantitativo}")
        if producao_horaria < 0:
            raise ValueError(f"producao_horaria must be >= 0, got {producao_horaria}")

    def _compute_max_weeks(self, producao_semanal_base: float, quantitativo: float, policy: WorkforcePolicy) -> int:
        """Guard computation: based on peak teams at full efficiency."""
        if producao_semanal_base <= 0 or policy.n_maximo <= 0:
            return 1  # Will immediately produce incompleta=True
        nominal_weeks = math.ceil(quantitativo / (producao_semanal_base * policy.n_maximo))
        return self.MAX_MULTIPLIER * max(1, nominal_weeks)

    def _simulate_weeks(
        self,
        policy: WorkforcePolicy,
        quantitativo: float,
        producao_semanal_base: float,
        max_weeks: int,
        prat_semanal: dict[str, float] | None,
        semanas_iso_por_offset: dict[int, str] | None,
        *,
        capacidade_horaria_por_frentes: Callable[[float], float] | None = None,
        horas_efetivas: float = 0.0,
        calendario_semanal: dict[str, float] | None = None,
    ) -> tuple[list[CurvaForcaSemanal], bool]:
        if producao_semanal_base <= 0:
            return [], True

        duration_initial = max(1, math.ceil(quantitativo / (producao_semanal_base * policy.n_maximo)))
        last_curve: list[CurvaForcaSemanal] = []
        for duration_weeks in range(duration_initial, max_weeks + 1):
            semanas: list[CurvaForcaSemanal] = []
            qtd_acumulada = 0.0
            for t, n_t in enumerate(policy.build_profile(duration_weeks)):
                semana_iso = semanas_iso_por_offset.get(t) if semanas_iso_por_offset else None
                praticabilidade = self._lookup_eficiencia(semana_iso, prat_semanal)
                calendario = (
                    calendario_semanal.get(semana_iso, 1.0)
                    if calendario_semanal is not None and semana_iso is not None
                    else 1.0
                )
                if capacidade_horaria_por_frentes is None:
                    capacidade_instalada = producao_semanal_base * n_t
                else:
                    capacidade_hora = capacidade_horaria_por_frentes(float(n_t))
                    if not math.isfinite(capacidade_hora) or capacidade_hora < 0:
                        raise ValueError("physical F(m) must be finite and nonnegative")
                    capacidade_instalada = capacidade_hora * horas_efetivas
                # MANUAL/AUTO and WMP share the same availability equation.
                # H already includes eta_jornada and cannot be multiplied again.
                qtd_semana_max = produtividade_realizavel(
                    capacidade_instalada, praticabilidade, calendario
                )
                qtd_semana = min(qtd_semana_max, quantitativo - qtd_acumulada)
                qtd_acumulada = round(qtd_acumulada + qtd_semana, 6)
                semanas.append(
                    CurvaForcaSemanal(
                        semana_offset=t,
                        num_equipes=n_t,
                        eficiencia=round(praticabilidade * calendario, 6),
                        qtd_executada=round(qtd_semana, 4),
                        qtd_acumulada=round(qtd_acumulada, 4),
                        semana_iso=semana_iso,
                    )
                )
            if qtd_acumulada >= quantitativo:
                return semanas, False
            last_curve = semanas
        return last_curve, True

    def _compute_n(self, policy: WorkforcePolicy, t: int) -> int:
        """Return the legacy unbounded team count at week offset t.

        Phase 1 — Mobilization:
            n(t) = min(floor(n_inicial + t × taxa_mobilizacao), n_maximo)

        Phase 2 — Plateau:
            n(t) = n_maximo
            Duration: semanas_plateau weeks (unlimited if None).

        Phase 3 — Demobilization (only when semanas_plateau is set):
            n(t) = max(floor(n_maximo - j × taxa_desmobilizacao), 0)
            where j = weeks elapsed since plateau ended.

        Demobilization is modelled only when semanas_plateau is explicitly set.
        When semanas_plateau is None, the activity stays at n_maximo until Q is
        delivered — demobilization is a post-delivery cost consideration.

        ---
        NEP-031 L6 — Equivalência com a fórmula do enunciado (§5):

        O enunciado descreve:
            m_j = round(m_max × j/r)        j = 1 … r   [ramp-up]
            m_j = m_max                      r < j ≤ n-d [plateau]
            m_j = round(m_max × (n-j+1)/d)  j > n-d     [ramp-down]

        Esta implementação usa parâmetros diferentes mas equivalentes:
            taxa_mobilizacao  ≈  m_max / r   (equipes por semana, no ramp-up)
            taxa_desmobilizacao ≈ m_max / d  (equipes por semana, no ramp-down)
            n_inicial         ≥  0           (equipes no início; enunciado implica 0)

        Diferenças intencionais:
        1. Arredondamento: `floor` em vez de `round`. Preferimos arredondamento
           conservador (nunca sobre-aloca) ao invés de arredondamento simétrico.
        2. `n_inicial > 0`: permite mobilização parcial prévia (ex.: equipe de setup).
           O enunciado assume implicitamente n_inicial = 0 (início do zero).
        3. `semanas_plateau`: quando None, a plateau não tem fim definido —
           o simulador continua até Q ser atingido. O enunciado exige n e d explícitos.

        Parametrização equivalente ao enunciado:
            n_inicial = 0
            taxa_mobilizacao = m_max / r
            semanas_plateau = n - r - d     (onde n = duração total em semanas)
            taxa_desmobilizacao = m_max / d
        """
        if policy.taxa_mobilizacao <= 0:
            # Formalismo: degenerate rectangular profile, μ+ = μ- = 0 => n(t)=n_maximo.
            return policy.n_maximo

        # Week at which n_maximo is first reached.
        t_ramp = math.ceil((policy.n_maximo - policy.n_inicial) / policy.taxa_mobilizacao)

        if t < t_ramp:
            # Mobilization phase
            return min(
                math.floor(policy.n_inicial + t * policy.taxa_mobilizacao),
                policy.n_maximo,
            )

        # At or beyond n_maximo
        if policy.semanas_plateau is None:
            # Unlimited plateau — stay at n_maximo
            return policy.n_maximo

        t_plateau_end = t_ramp + policy.semanas_plateau

        if t <= t_plateau_end:
            return policy.n_maximo

        # Demobilization phase (forced by semanas_plateau)
        if policy.taxa_desmobilizacao <= 0:
            # No demobilization rate defined — stay at n_maximo despite plateau end
            return policy.n_maximo

        weeks_since_plateau = t - t_plateau_end
        n_desmob = policy.n_maximo - math.floor(weeks_since_plateau * policy.taxa_desmobilizacao)
        return max(0, n_desmob)

    @staticmethod
    def _lookup_eficiencia(
        semana_iso: str | None,
        prat_semanal: dict[str, float] | None,
    ) -> float:
        """Return practicability factor p(t) for a calendar week.

        Defaults to 1.0 (no weather constraint) when:
        - semana_iso is None (simulation not anchored to calendar)
        - prat_semanal is None (no climate data provided)
        - semana_iso not found in prat_semanal (week outside data range)
        """
        if not semana_iso or not prat_semanal:
            return 1.0
        return float(prat_semanal.get(semana_iso, 1.0))

    @staticmethod
    def derive_semanas_iso(
        semana_inicio: str,
        n_semanas: int,
    ) -> dict[int, str]:
        """Build offset→ISO_week map starting from semana_inicio.

        Args:
            semana_inicio: ISO week key of the activity's first week, e.g. "2026-W23".
            n_semanas: number of weeks to generate.

        Returns:
            {0: "2026-W23", 1: "2026-W24", ...}

        Useful for anchoring prat_semanal lookup when the activity start week is known.
        """
        from datetime import date, timedelta

        year_str, week_str = semana_inicio.split("-W")
        year, week = int(year_str), int(week_str)

        # ISO week 1 of year starts on the Monday of the week containing Jan 4
        jan4 = date(year, 1, 4)
        start_of_week1 = jan4 - timedelta(days=jan4.weekday())
        anchor = start_of_week1 + timedelta(weeks=week - 1)

        result: dict[int, str] = {}
        for offset in range(n_semanas):
            d = anchor + timedelta(weeks=offset)
            iso = d.isocalendar()
            result[offset] = f"{iso.year}-W{iso.week:02d}"
        return result
