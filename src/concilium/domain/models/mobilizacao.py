"""Domain value objects for workforce mobilization policy (ADR-054).

All types are immutable (frozen Pydantic models) — treat as value objects.
Simulation logic lives in domain.services.mobilizacao_simulator.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MobilizacaoPolicy(BaseModel):
    """Declarative workforce mobilization policy for a compositional activity.

    Describes HOW teams ramp up and (optionally) wind down — not WHEN.
    The execution horizon (number of weeks) is derived from the policy plus
    productivity and quantity by WorkforcePolicySimulator.

    Phase semantics:
        1. Mobilization: n(t) = min(n_inicial + floor(t × taxa_mobilizacao), n_maximo)
        2. Plateau:      n(t) = n_maximo  (unlimited if semanas_plateau is None)
        3. Demobilization (forced only if semanas_plateau is set):
                         n(t) = max(n_maximo - floor(j × taxa_desmobilizacao), 0)
                         where j = weeks elapsed since plateau ended

    Assumptions documented explicitly (ADR-054 §7.4):
        - Weekly granularity
        - n(t) is integer (floor applied to ramp)
        - Demobilization during active production triggers VAL-WMP-03
        - taxa_desmobilizacao = 0 means no wind-down is modelled
    """

    model_config = ConfigDict(frozen=True)

    n_inicial: int = Field(ge=1, description="Teams at week 0 of activity (n_0)")
    n_maximo: int = Field(ge=1, description="Peak team count ceiling (n_max)")
    taxa_mobilizacao: float = Field(
        gt=0,
        description="Teams added per week during ramp-up (c_mob). "
        "Fractional values allowed: 0.5 = one extra team every 2 weeks.",
    )
    taxa_desmobilizacao: float = Field(
        default=0.0,
        ge=0,
        description="Teams removed per week after plateau (c_desmob). "
        "0 = no demobilization modelled during production horizon.",
    )
    semanas_plateau: int | None = Field(
        default=None,
        ge=0,
        description="Fixed plateau duration in weeks before demobilization begins. "
        "None = plateau lasts until Q is fully delivered.",
    )

    @model_validator(mode="after")
    def _validate_ordering(self) -> MobilizacaoPolicy:
        if self.n_maximo < self.n_inicial:
            raise ValueError(f"n_maximo ({self.n_maximo}) must be >= n_inicial ({self.n_inicial})")
        return self

    @classmethod
    def imediato(cls, n_maximo: int) -> MobilizacaoPolicy:
        """Convenience: deploy all teams from week 0 (no ramp)."""
        return cls(n_inicial=n_maximo, n_maximo=n_maximo, taxa_mobilizacao=n_maximo)

    @classmethod
    def padrao(cls, n_maximo: int, taxa_mobilizacao: float = 1.0) -> MobilizacaoPolicy:
        """Convenience: start with 1 team, ramp at given rate."""
        return cls(n_inicial=1, n_maximo=n_maximo, taxa_mobilizacao=taxa_mobilizacao)


class CurvaForcaSemanal(BaseModel):
    """Production and workforce data for one week of an activity's execution.

    Produced by WorkforcePolicySimulator — never constructed manually.
    semana_iso is None when simulation is not anchored to a calendar date.
    """

    model_config = ConfigDict(frozen=True)

    semana_offset: int = Field(ge=0, description="0-indexed week within this activity")
    num_equipes: int = Field(ge=0)
    eficiencia: float = Field(ge=0.0, le=1.0, description="Practicability factor p(t)")
    qtd_executada: float = Field(ge=0.0)
    qtd_acumulada: float = Field(ge=0.0)
    semana_iso: str | None = Field(default=None, description="ISO week key 'AAAA-Www' if anchored to calendar")


class CurvaForca(BaseModel):
    """Complete derived execution curve for one compositional activity.

    Produced by WorkforcePolicySimulator.simulate(). Immutable — a cached
    derivation artifact. Re-derivable from (policy, quantitativo, P, regime, p_t).

    The curve terminates when:
        - qtd_acumulada >= quantitativo_alvo  →  incompleta=False (success)
        - simulation guard exceeded            →  incompleta=True  (policy infeasible)
    """

    model_config = ConfigDict(frozen=True)

    atividade_id: str
    quantitativo_alvo: float = Field(gt=0)
    producao_horaria: float = Field(ge=0)
    dias_semana: int = Field(ge=1, le=7)
    horas_dia: int = Field(ge=1, le=24)
    policy: MobilizacaoPolicy
    semanas: list[CurvaForcaSemanal] = Field(default_factory=list)
    incompleta: bool = Field(
        default=False,
        description="True if the simulation guard was exhausted before Q was delivered. "
        "Signals that the policy is infeasible for this activity.",
    )

    @property
    def duration_weeks(self) -> int:
        """Derived execution horizon in weeks."""
        return len(self.semanas)

    @property
    def delivered(self) -> float:
        """Total quantity delivered (last cumulative entry)."""
        return self.semanas[-1].qtd_acumulada if self.semanas else 0.0

    @property
    def is_complete(self) -> bool:
        """True iff delivered quantity meets or exceeds target."""
        return not self.incompleta and self.delivered >= self.quantitativo_alvo

    @property
    def peak_teams(self) -> int:
        """Maximum teams deployed in any single week."""
        return max((s.num_equipes for s in self.semanas), default=0)

    @property
    def total_team_weeks(self) -> int:
        """Sum of num_equipes across all weeks — proportional to total labour cost."""
        return sum(s.num_equipes for s in self.semanas)

    def to_num_equipes_por_semana(self) -> dict[str, int]:
        """Convert to the historical Skill 04 MANUAL mode input format.

        Returns {semana_iso: num_equipes} for all weeks where semana_iso is known.
        Falls back to str(offset) as key when not anchored to calendar.
        """
        result: dict[str, int] = {}
        for s in self.semanas:
            key = s.semana_iso if s.semana_iso else str(s.semana_offset)
            result[key] = s.num_equipes
        return result
