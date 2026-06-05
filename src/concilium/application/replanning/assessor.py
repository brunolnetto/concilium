"""ADR-005 — ImpactAssessor: cost/benefit analysis for replan candidates."""

from __future__ import annotations

from concilium.application.replanning.models import ReplannCandidate, ReplannImpactAssessment
from concilium.domain.models.canonical import CanonicalModel

_DEFAULT_PENALTY_RATE_PER_DAY = 10_000.0  # R$/day (override via projeto.multa_atraso_per_day)
_DEFAULT_DISRUPTION_RATE = 0.10  # 10% of cost_delta as disruption overhead


class ImpactAssessor:
    """Calcula custo/benefício de candidatos de replanejamento."""

    def assess(
        self,
        canonical: CanonicalModel,
        candidate: ReplannCandidate,
        days_late_current: float = 0.0,
    ) -> ReplannImpactAssessment:
        """Compute net_benefit for a replan candidate.

        Args:
            canonical: current project state
            candidate: replan option to evaluate
            days_late_current: how many days late the project is currently forecast to be
        """
        penalty_rate = getattr(canonical.projeto, "multa_atraso_per_day", _DEFAULT_PENALTY_RATE_PER_DAY)

        schedule_delta_days = candidate.schedule_delta_weeks * 7

        # Penalty avoided: days saved × daily penalty rate
        if days_late_current > 0 and schedule_delta_days < 0:
            days_saved = min(days_late_current, abs(schedule_delta_days))
            penalty_avoided = days_saved * penalty_rate
        else:
            penalty_avoided = 0.0

        # Expedite revenue: only if project has early-completion bonus (not modelled here)
        expedite_revenue = 0.0

        # Disruption cost: proportional to absolute cost delta
        disruption_cost = abs(candidate.cost_delta) * _DEFAULT_DISRUPTION_RATE

        # Efficiency gain: modest savings from better resource utilization
        efficiency_gain = max(0.0, -candidate.cost_delta * 0.05) if candidate.cost_delta < 0 else 0.0

        net_benefit = penalty_avoided + expedite_revenue + efficiency_gain - candidate.cost_delta - disruption_cost

        # Determine recommendation
        if net_benefit > 50_000:
            recommendation = "PROCEED"
        elif net_benefit > 0:
            recommendation = "NEGOTIATE_EXTENSION"
        else:
            recommendation = "ACCEPT_DELAY"

        return ReplannImpactAssessment(
            candidate_id=candidate.candidate_id,
            schedule_delta_days=schedule_delta_days,
            cost_delta=candidate.cost_delta,
            penalty_avoided=penalty_avoided,
            expedite_revenue=expedite_revenue,
            efficiency_gain=efficiency_gain,
            disruption_cost=disruption_cost,
            net_benefit=net_benefit,
            recommendation=recommendation,  # type: ignore[arg-type]
        )

    def assess_all(
        self,
        canonical: CanonicalModel,
        candidates: list[ReplannCandidate],
        days_late_current: float = 0.0,
    ) -> list[ReplannImpactAssessment]:
        """Assess all candidates and return sorted by net_benefit descending."""
        assessments = [self.assess(canonical, c, days_late_current) for c in candidates]
        return sorted(assessments, key=lambda a: a.net_benefit, reverse=True)
