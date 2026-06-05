"""ADR-005 — Replanning data models.

Tiers:
  1 — Local Rebalancing  (no formal approval needed)
  2 — Tactical Replan    (senior engineer approval)
  3 — Strategic Replan   (director + client approval)
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

ReplannTierCode = Literal[1, 2, 3]

T1_CODES = Literal["T1-EARLY", "T1-SLACK", "T1-WEATHER", "T1-RESOURCE-PEAK"]
T2_CODES = Literal["T2-DELAY", "T2-BLOCKER-1W", "T2-RESOURCE-SUSTAINED", "T2-PRODUCTIVITY-DRIFT", "T2-COST-OVERRUN"]
T3_CODES = Literal["T3-DEADLINE", "T3-CASCADE", "T3-RESOURCE-SHORTAGE", "T3-COST-MILESTONE"]
TriggerCode = Literal[
    "T1-EARLY",
    "T1-SLACK",
    "T1-WEATHER",
    "T1-RESOURCE-PEAK",
    "T2-DELAY",
    "T2-BLOCKER-1W",
    "T2-RESOURCE-SUSTAINED",
    "T2-PRODUCTIVITY-DRIFT",
    "T2-COST-OVERRUN",
    "T3-DEADLINE",
    "T3-CASCADE",
    "T3-RESOURCE-SHORTAGE",
    "T3-COST-MILESTONE",
]


class ReplannTrigger(BaseModel):
    """Gatilho de replanejamento detectado durante monitoramento de progresso."""

    model_config = ConfigDict(extra="ignore")

    trigger_id: str = Field(default_factory=lambda: str(uuid4()))
    tier: ReplannTierCode
    code: TriggerCode
    activity_id: str | None = None
    resource_type: str | None = None

    # Quantitative context
    delay_weeks: float | None = None
    weeks_early: float | None = None
    usage_pct: float | None = None
    forecast_week: int | None = None
    days_late: int | None = None

    escalate_to: str | None = None
    auto_action: str | None = None
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReplannCandidate(BaseModel):
    """Uma opção de replanejamento gerada para um trigger."""

    model_config = ConfigDict(extra="ignore")

    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str

    # Deltas vs. current plan
    schedule_delta_weeks: float = 0.0  # negative = shortens project
    team_count_delta: int = 0  # additional teams added/removed
    cost_delta: float = 0.0  # R$ change (positive = more expensive)
    resource_pool_delta: dict[str, int] = Field(default_factory=dict)

    # Modified schedule (sparse: only changed activities)
    schedule_changes: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ReplannImpactAssessment(BaseModel):
    """Avaliação de custo/benefício de um candidato de replanejamento."""

    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    schedule_delta_days: float
    cost_delta: float

    penalty_avoided: float = 0.0  # R$ economia por evitar multa
    expedite_revenue: float = 0.0  # R$ ganho por conclusão antecipada
    efficiency_gain: float = 0.0  # R$ economizados em overhead
    disruption_cost: float = 0.0  # R$ custo de reatribuição de equipes
    admin_overhead: float = 0.0  # R$ custo administrativo

    net_benefit: float = 0.0  # computed: penalty_avoided + efficiency_gain - cost_delta - disruption_cost
    recommendation: Literal["PROCEED", "NEGOTIATE_EXTENSION", "ACCEPT_DELAY"] = "ACCEPT_DELAY"

    def model_post_init(self, __context: Any) -> None:
        if self.net_benefit == 0.0:
            self.net_benefit = (
                self.penalty_avoided
                + self.efficiency_gain
                + self.expedite_revenue
                - self.cost_delta
                - self.disruption_cost
                - self.admin_overhead
            )
        if self.net_benefit > 50_000:
            self.recommendation = "PROCEED"
        elif self.net_benefit > 0:
            self.recommendation = "NEGOTIATE_EXTENSION"
        else:
            self.recommendation = "ACCEPT_DELAY"


class ReplannDecision(BaseModel):
    """Registro imutável de uma decisão de replanejamento."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    replan_id: str = Field(default_factory=lambda: str(uuid4()))
    trigger: ReplannTrigger
    tier: ReplannTierCode

    candidates_generated: list[ReplannCandidate] = Field(default_factory=list)
    assessments: list[ReplannImpactAssessment] = Field(default_factory=list)

    selected_candidate_id: str | None = None
    selected_recommendation: str | None = None

    approval_chain: list[dict[str, Any]] = Field(default_factory=list)
    schedule_version_before: str = ""
    schedule_version_after: str = ""

    rationale: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None


class ReplannFrequencyPolicy(BaseModel):
    """Política de frequência de replanejamento."""

    model_config = ConfigDict(extra="ignore")

    min_days_between_replans: int = 7
    max_replans_per_activity: int = 3
    max_activities_per_replan: int = 30
