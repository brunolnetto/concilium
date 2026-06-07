"""ADR-075: Foundation data classes — RampProfile, ActivityPlan, PerpetuationSolution.

Implements the three interface objects defined in ADR-075 §D3:

    RampProfile          — hyperparameter (planner input, immutable)
    ActivityPlan         — scheduling output (window per activity)
    PerpetuationSolution — matching oracle output (perpetuation edges + cost)

RampProfile.build() is the canonical factory.  Direct construction is allowed
but callers are responsible for computing m / boundary_* consistently.

Formula for m[t] (0-indexed, NEP-031 §L6):
  Ramp-up   (t < r)              : min(n_0 + floor(t * (K_max-n_0)/r), K_max)
  Plateau   (r <= t < n_i - d)   : K_max
  Ramp-down (n_i-d <= t < n_i)   : max(K_max - floor(j * K_max/d), 0)
                                   where j = t - (n_i - d)

Constraints validated by model_validator:
  - K_max >= n_0
  - r + d <= n_i
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ─────────────────────────────────────────────────────────────────────────────
# RampProfile (Pydantic frozen value object)
# ─────────────────────────────────────────────────────────────────────────────


class RampProfile(BaseModel):
    """Ramp hyperparameter — supplied by the planner, not optimised (ADR-075 D3).

    Treat as immutable: boundary_supply / boundary_demand are pre-computed once
    at construction and must not be mutated after creation.
    """

    model_config = ConfigDict(frozen=True)

    activity_id: str
    K_max: int = Field(ge=1, description="Número máximo de equipes (pico)")
    r: int = Field(ge=0, description="Semanas de ramp-up (fases antes do plateau)")
    d: int = Field(ge=0, description="Semanas de ramp-down (após o plateau)")
    n_i: int = Field(ge=1, description="Duração total da atividade em semanas")
    resources_per_team: dict[str, int] = Field(
        description="Recursos por equipe {resource_id: qty}",
        default_factory=dict,
    )
    n_0: int = Field(default=1, ge=0, description="Equipes na semana 0 (início do ramp-up)")
    m: tuple[int, ...] = Field(description="Vetor m[t] = equipes na semana t (0-indexed)")
    boundary_supply: dict[str, int] = Field(
        description="m[n_i-1] × resources_per_team[r] — equipes disponíveis para perpetuação no fim",
        default_factory=dict,
    )
    boundary_demand: dict[str, int] = Field(
        description="m[0] × resources_per_team[r] — equipes necessárias no início",
        default_factory=dict,
    )

    @model_validator(mode="after")
    def _validate_consistency(self) -> RampProfile:
        if self.K_max < self.n_0:
            raise ValueError(
                f"K_max ({self.K_max}) must be >= n_0 ({self.n_0}): "
                "peak team count cannot be less than initial team count"
            )
        if self.r + self.d > self.n_i:
            raise ValueError(
                f"r ({self.r}) + d ({self.d}) > n_i ({self.n_i}): ramp-up + ramp-down phases exceed activity duration"
            )
        return self

    # ── factory ──────────────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        activity_id: str,
        K_max: int,
        r: int,
        d: int,
        n_i: int,
        resources_per_team: dict[str, int],
        n_0: int = 1,
    ) -> RampProfile:
        """Build a RampProfile, computing m and boundary values from parameters.

        Args:
            activity_id: Unique identifier of the activity.
            K_max:       Peak team count.
            r:           Ramp-up duration in weeks (0 = instant mobilisation).
            d:           Ramp-down duration in weeks (0 = no planned demob).
            n_i:         Total productive duration in weeks.
            resources_per_team: {resource_id: units per team}.
            n_0:         Teams at week 0 (default 1).
        """
        if K_max < n_0:
            raise ValueError(
                f"K_max ({K_max}) must be >= n_0 ({n_0}): peak team count cannot be less than initial team count"
            )
        if r + d > n_i:
            raise ValueError(f"r ({r}) + d ({d}) > n_i ({n_i}): ramp-up + ramp-down phases exceed activity duration")

        t_demob_start = n_i - d  # first ramp-down week index
        c_mob_eff = (K_max - n_0) / r if r > 0 else 0.0
        c_demob_eff = K_max / d if d > 0 else 0.0

        m_list: list[int] = []
        for t in range(n_i):
            if d > 0 and t >= t_demob_start:
                # Ramp-down phase takes precedence (covers the case r + d == n_i)
                j = t - t_demob_start
                val = max(K_max - math.floor(j * c_demob_eff), 0)
            elif t < r:
                # Ramp-up phase
                val = min(n_0 + math.floor(t * c_mob_eff), K_max)
            else:
                # Plateau
                val = K_max
            m_list.append(val)

        m = tuple(m_list)
        boundary_supply = {res: m[-1] * qty for res, qty in resources_per_team.items()}
        boundary_demand = {res: m[0] * qty for res, qty in resources_per_team.items()}

        return cls(
            activity_id=activity_id,
            K_max=K_max,
            r=r,
            d=d,
            n_i=n_i,
            resources_per_team=resources_per_team,
            n_0=n_0,
            m=m,
            boundary_supply=boundary_supply,
            boundary_demand=boundary_demand,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ActivityPlan (scheduling output)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ActivityPlan:
    """Output of the Scheduling layer.

    window = (s_i, f_i) where s_i and f_i are absolute week indices.
    n_i = f_i - s_i (productive duration).
    """

    activity_id: str
    window: tuple[int, int]  # (s_i, f_i) — absolute weeks, 0-indexed
    n_i: int


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1-c: PerpetuationSolution (matching oracle output)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PerpetuationSolution:
    """Output of the Matching oracle.

    edges: list of (activity_i, activity_j, resource_id, qty_perpetuated)
    mob_cost_actual: total mobilisation cost after optimal perpetuation (R$)
    mob_events_by_resource: {resource_id: net_mobilisation_events}
    concurrent_pairs_lost: (i, j, r) triples blocked by conc(i,j)=1 —
        feedback signal for the LNS scheduler (Mode B).
    """

    edges: list[tuple[str, str, str, int]] = field(default_factory=list)
    mob_cost_actual: float = 0.0
    mob_events_by_resource: dict[str, int] = field(default_factory=dict)
    concurrent_pairs_lost: list[tuple[str, str, str]] = field(default_factory=list)


__all__ = ["RampProfile", "ActivityPlan", "PerpetuationSolution"]
