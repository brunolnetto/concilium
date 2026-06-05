"""ADR-005 — ReplannGenerator: generates candidate schedules for a trigger."""

from __future__ import annotations

from concilium.application.replanning.models import ReplannCandidate, ReplannTrigger
from concilium.domain.models.canonical import CanonicalModel


class ReplannGenerator:
    """Gera candidatos de replanejamento baseados no trigger e tier."""

    def generate_candidates(
        self,
        canonical: CanonicalModel,
        trigger: ReplannTrigger,
    ) -> list[ReplannCandidate]:
        """Generate 1 (Tier 1) to 3+ (Tier 2/3) replan options."""
        if trigger.tier == 1:
            return self._generate_t1(canonical, trigger)
        elif trigger.tier == 2:
            return self._generate_t2(canonical, trigger)
        else:
            return self._generate_t3(canonical, trigger)

    def _generate_t1(
        self,
        canonical: CanonicalModel,
        trigger: ReplannTrigger,
    ) -> list[ReplannCandidate]:
        candidates: list[ReplannCandidate] = []

        if trigger.code == "T1-EARLY" and trigger.activity_id and trigger.weeks_early:
            candidates.append(
                ReplannCandidate(
                    name=f"Acelerar sucessoras de {trigger.activity_id}",
                    description=(
                        f"{trigger.activity_id} concluída {trigger.weeks_early:.1f} semanas antes. "
                        "Oferecer antecipação das atividades sucessoras."
                    ),
                    schedule_delta_weeks=-trigger.weeks_early,
                    cost_delta=0.0,
                )
            )

        return candidates

    def _generate_t2(
        self,
        canonical: CanonicalModel,
        trigger: ReplannTrigger,
    ) -> list[ReplannCandidate]:
        candidates: list[ReplannCandidate] = []

        if trigger.code == "T2-DELAY" and trigger.activity_id:
            delay = trigger.delay_weeks or 1.0

            # Option 1: add 1 team to delayed activity
            candidates.append(
                ReplannCandidate(
                    name=f"Adicionar 1 equipe a {trigger.activity_id}",
                    description=(
                        f"Aumentar número de equipes em {trigger.activity_id} para recuperar "
                        f"{delay:.1f} semana(s) de atraso."
                    ),
                    schedule_delta_weeks=-min(delay, 1.0),
                    team_count_delta=1,
                    cost_delta=15_000.0,  # estimated R$ per extra team-week
                )
            )

            # Option 2: reorder slack activities to free resources
            candidates.append(
                ReplannCandidate(
                    name="Reorganizar atividades com folga para liberar recursos",
                    description=(
                        "Adiar atividades não-críticas para liberar recursos para "
                        f"{trigger.activity_id}. Sem custo adicional."
                    ),
                    schedule_delta_weeks=-min(delay * 0.5, 1.0),
                    team_count_delta=0,
                    cost_delta=-5_000.0,  # saves some overhead
                )
            )

            # Option 3: consolidate downstream (accept slight extension)
            candidates.append(
                ReplannCandidate(
                    name="Consolidar atividades a jusante — aceitar pequeno atraso",
                    description=(
                        "Consolidar atividades seguintes para minimizar impacto total. Prazo se estende ligeiramente."
                    ),
                    schedule_delta_weeks=delay * 0.5,
                    team_count_delta=0,
                    cost_delta=0.0,
                )
            )

        elif trigger.code == "T2-PRODUCTIVITY-DRIFT":
            # Add supplemental teams across all lagging activities
            candidates.append(
                ReplannCandidate(
                    name="Aumentar equipes em atividades com produtividade baixa",
                    description=(
                        f"SPI atual: {trigger.usage_pct:.2f}. Adicionar equipes às atividades "
                        "com maior desvio para recuperar ritmo."
                    ),
                    schedule_delta_weeks=-2.0,
                    team_count_delta=2,
                    cost_delta=30_000.0,
                )
            )

        return candidates

    def _generate_t3(
        self,
        canonical: CanonicalModel,
        trigger: ReplannTrigger,
    ) -> list[ReplannCandidate]:
        candidates: list[ReplannCandidate] = []

        # Option 1: expand resource pool (hire contractors)
        candidates.append(
            ReplannCandidate(
                name="Expansão do pool de recursos (+20%)",
                description="Contratar equipes adicionais para recuperar prazo.",
                schedule_delta_weeks=-4.0,
                team_count_delta=3,
                cost_delta=100_000.0,
            )
        )

        # Option 2: deadline extension
        days_late = trigger.days_late or 14
        candidates.append(
            ReplannCandidate(
                name=f"Negociar extensão de prazo (+{days_late // 7} semanas)",
                description=(f"Solicitar extensão contratual de {days_late} dias. Sem custo adicional de mão de obra."),
                schedule_delta_weeks=days_late / 7,
                team_count_delta=0,
                cost_delta=0.0,
            )
        )

        # Option 3: reduce scope (defer non-critical activities)
        candidates.append(
            ReplannCandidate(
                name="Redução de escopo — adiar atividades não-críticas",
                description="Diferir atividades de baixa criticidade para fase posterior.",
                schedule_delta_weeks=-3.0,
                team_count_delta=-1,
                cost_delta=-50_000.0,
            )
        )

        # Option 4: full restructure
        candidates.append(
            ReplannCandidate(
                name="Reestruturação completa do cronograma",
                description="Replanejamento total a partir da semana atual.",
                schedule_delta_weeks=0.0,
                team_count_delta=0,
                cost_delta=20_000.0,  # admin / re-planning cost
            )
        )

        return candidates
