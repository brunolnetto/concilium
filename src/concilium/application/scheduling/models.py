"""ADR-004: Scheduling data models.

Defines Activity, ActivityDAG, ResourcePool, ScheduledActivity,
ScheduleMetrics, ScheduleOutput, SchedulingStrategy and ScheduleError.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel


class ScheduleError(Exception):
    """Raised when a feasible schedule cannot be produced."""


@dataclass
class Activity:
    """A schedulable activity with resource requirements and duration.

    ADR-072 (Direção A): ``duration_weeks`` is the *productive* duration
    derived from Q / production_rate, NOT the corridor calendar span.
    ``window_weeks``, when set, is the corridor calendar span — the outer
    envelope within which the productive activity must be scheduled.
    Constraint enforced by the scheduler: finish ≤ window_weeks from t=0.
    """

    activity_id: str
    description: str
    duration_weeks: int
    required_resources: dict[str, int] = field(default_factory=dict)
    # ADR-072: corridor window (calendar span); None = no window constraint
    window_weeks: int | None = None
    # ADR-074: normalized ramp profile per week; values in [0.0, 1.0] where 1.0 = peak demand.
    # Length must equal duration_weeks when set.
    # Actual demand for resource r at week offset t = max(0, round(required_resources[r] × ramp_profile[t]))
    # None = flat demand (historical behaviour, no change).
    ramp_profile: list[float] | None = None

    def __post_init__(self) -> None:
        if self.duration_weeks < 1:
            raise ValueError(f"duration_weeks must be >= 1, got {self.duration_weeks}")
        if self.window_weeks is not None and self.window_weeks < self.duration_weeks:
            raise ValueError(f"window_weeks ({self.window_weeks}) must be >= duration_weeks ({self.duration_weeks})")
        if self.ramp_profile is not None:
            if len(self.ramp_profile) != self.duration_weeks:
                raise ValueError(
                    f"ramp_profile length ({len(self.ramp_profile)}) must equal duration_weeks ({self.duration_weeks})"
                )


@dataclass
class ActivityDAG:
    """Directed Acyclic Graph of activities with precedence constraints.

    ADR-081: ``thresholds`` maps (pred_id, succ_id) → completion_threshold_pct ∈ [0,1].
    Default value for any missing pair is 1.0 (classic FS 100%).

    Semântica de threshold para FS:
        start_j ≥ start_i + ceil(θ × duration_i)
    θ=1.0 → comportamento clássico FS.  θ=0.0 → equivalente a SS.

    NEP-031 L4: ``extended_precedences`` transporta relações SS/FF com lag derivadas
    de EapItem.predecessores ou rcpsp_spec. O CP-SAT scheduler as aplica diretamente.
    Compatível com SerialScheduler (que as ignora graciosamente).
    """

    activities: list[Activity]
    precedence: list[tuple[str, str]] = field(default_factory=list)
    # ADR-081: per-edge completion threshold. Missing pair → 1.0 (FS strict).
    thresholds: dict[tuple[str, str], float] = field(default_factory=dict)
    # NEP-031 L4: relações SS/FF com lag (além do FS codificado em thresholds).
    extended_precedences: list = field(default_factory=list)

    def _activity_map(self) -> dict[str, Activity]:
        return {a.activity_id: a for a in self.activities}

    def get_activity(self, activity_id: str) -> Activity:
        return self._activity_map()[activity_id]

    def get_threshold(self, pred_id: str, succ_id: str) -> float:
        """Return completion_threshold_pct for edge (pred_id → succ_id). Default 1.0."""
        return self.thresholds.get((pred_id, succ_id), 1.0)

    def predecessors(self, activity_id: str) -> list[str]:
        """Return list of immediate predecessor IDs."""
        return [pred for pred, succ in self.precedence if succ == activity_id]

    def successors(self, activity_id: str) -> list[str]:
        """Return list of immediate successor IDs."""
        return [succ for pred, succ in self.precedence if pred == activity_id]

    def topological_order(self) -> list[str]:
        """Return activity IDs in topological order (Kahn's algorithm)."""
        from collections import deque

        in_degree: dict[str, int] = {a.activity_id: 0 for a in self.activities}
        for _pred, succ in self.precedence:
            in_degree[succ] += 1

        queue: deque[str] = deque(aid for aid, deg in in_degree.items() if deg == 0)
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for succ in self.successors(node):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(order) != len(self.activities):
            raise ValueError("ActivityDAG contains a cycle")
        return order


@dataclass
class ResourcePool:
    """Available resources and their capacities."""

    resources: dict[str, int] = field(default_factory=dict)


@dataclass
class ReplenishableResource:
    """ADR-128 D2: recurso consumível opcional com estoque/reabastecimento.

    Paralelo a ``ResourcePool``, mas com semântica de fluxo/estoque em vez de contagem
    de unidades reutilizáveis: o recurso se esgota com o uso e é reabastecido ao longo
    do tempo (ver ``concilium.application.scheduling.replenishable``). Opt-in — quando
    não passado ao scheduler, o comportamento é idêntico ao anterior à ADR-128.
    """

    resource_id: str
    disponibilidade: DisponibilidadeConsumivel
    # activity_id -> taxa de consumo projetada por semana ativa da atividade
    consumo_por_semana: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for activity_id, taxa in self.consumo_por_semana.items():
            if not math.isfinite(taxa) or taxa < 0:
                raise ValueError(
                    f"consumo_por_semana['{activity_id}'] must be finite and >= 0, got {taxa!r} "
                    f"(valores negativos/NaN/infinitos podem 'aumentar' estoque no motor de "
                    f"reabastecimento e mascarar inviabilidades — ADR-128)"
                )


@dataclass
class ScheduledActivity:
    """An activity that has been placed on the schedule."""

    activity_id: str
    start_week: int
    end_week: int
    duration_weeks: int
    assigned_resources: dict[str, int] = field(default_factory=dict)
    # ADR-074: propagated from Activity.ramp_profile for post-scheduling cost computation
    ramp_profile: list[float] | None = None


@dataclass
class ScheduleMetrics:
    """Quality metrics for a produced schedule."""

    makespan: int
    resource_leveling_score: float  # 0-1, higher is more level
    idle_time: int  # total idle resource-weeks
    activity_fragmentation: int  # activities split across non-contiguous slots
    critical_path_slack_min: float  # min float slack on critical path
    resource_utilization_avg: float  # 0-1 average weekly utilization

    def quality_score(
        self,
        weight_makespan: float = 0.5,
        weight_leveling: float = 0.2,
        weight_idle: float = 0.15,
        weight_utilization: float = 0.15,
        deadline_weeks: int = 0,
    ) -> float:
        """Composite quality score in [0, 1] (higher = better).

        Components:
          - makespan_score: 1 if makespan <= deadline, linearly penalised beyond
          - leveling_score: resource_leveling_score directly
          - idle_score:     1 / (1 + idle_time)
          - utilization_score: resource_utilization_avg
        """
        # Makespan component
        if deadline_weeks and deadline_weeks > 0:
            # Quadratic penalty: score = (deadline/makespan)^2, capped at 1
            ratio = deadline_weeks / max(self.makespan, 1)
            makespan_score = min(1.0, ratio * ratio)
        else:
            makespan_score = 1.0 / (1.0 + self.makespan / 10.0)

        leveling_score = self.resource_leveling_score
        idle_score = 1.0 / (1.0 + self.idle_time)
        utilization_score = self.resource_utilization_avg

        return (
            weight_makespan * makespan_score
            + weight_leveling * leveling_score
            + weight_idle * idle_score
            + weight_utilization * utilization_score
        )


@dataclass
class ScheduleOutput:
    """Result of a scheduling run."""

    scheduled_activities: list[ScheduledActivity]
    makespan: int
    feasible: bool
    metrics: ScheduleMetrics
    heuristic: str = ""

    def get_weekly_resource_usage(self, week: int) -> dict[str, int]:
        """Return total resource usage in a given week."""
        usage: dict[str, int] = {}
        for act in self.scheduled_activities:
            if act.start_week <= week < act.end_week:
                for res, qty in act.assigned_resources.items():
                    usage[res] = usage.get(res, 0) + qty
        return usage


@dataclass
class SchedulingStrategy:
    """Decision output from select_scheduling_algorithm()."""

    algorithm: str  # "MILP" | "SerialScheduler"
    heuristics: list[str] = field(default_factory=list)
    timeout_seconds: int = 60
    leveling_pass: bool = False
    rationale: str = ""
