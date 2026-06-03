"""ADR-005 — ReplannTriggerDetector: monitors progress and emits triggers."""

from __future__ import annotations

from concilium.application.progress.models import WeeklyProgressReport
from concilium.application.replanning.models import ReplannTrigger
from concilium.domain.models.canonical import CanonicalModel

# Thresholds
_T1_EARLY_MIN_WEEKS = 1.0
_T2_DELAY_MIN_WEEKS = 1.0
_T2_PRODUCTIVITY_DRIFT_THRESHOLD = 0.80  # <80% of baseline SPI
_T1_RESOURCE_PEAK_PCT = 0.95
_T2_RESOURCE_SUSTAINED_PCT = 1.0
_T3_DEADLINE_OVERRUN = 0


class ReplannTriggerDetector:
    """Detecta gatilhos de replanejamento a partir do relatório de progresso semanal."""

    def check_triggers(
        self,
        canonical: CanonicalModel,
        progress_report: WeeklyProgressReport,
        current_week: int,
    ) -> list[ReplannTrigger]:
        """Evaluate all T1/T2/T3 trigger conditions and return detected triggers."""
        triggers: list[ReplannTrigger] = []

        triggers.extend(self._check_t1_triggers(canonical, progress_report, current_week))
        triggers.extend(self._check_t2_triggers(canonical, progress_report, current_week))
        triggers.extend(self._check_t3_triggers(canonical, progress_report, current_week))

        return triggers

    def _check_t1_triggers(
        self,
        canonical: CanonicalModel,
        report: WeeklyProgressReport,
        current_week: int,
    ) -> list[ReplannTrigger]:
        triggers: list[ReplannTrigger] = []

        for activity_prog in report.activities:
            cron_item = next(
                (
                    sa
                    for sa in (canonical.cronograma.scheduled_activities if canonical.cronograma else [])
                    if sa.activity_id == activity_prog.activity_id
                ),
                None,
            )
            if cron_item is None:
                continue

            len(cron_item.distribuicao_semanal)

            # T1-EARLY: activity completed before planned end
            if activity_prog.pct_completude >= 1.0 and activity_prog.delay_weeks < -_T1_EARLY_MIN_WEEKS:
                triggers.append(
                    ReplannTrigger(
                        tier=1,
                        code="T1-EARLY",
                        activity_id=activity_prog.activity_id,
                        weeks_early=abs(activity_prog.delay_weeks),
                        auto_action="offer_acceleration",
                    )
                )

            # T1-SLACK: activity is ahead but not yet complete
            if 0 < activity_prog.pct_completude < 1.0 and activity_prog.delay_weeks < -_T1_EARLY_MIN_WEEKS:
                triggers.append(
                    ReplannTrigger(
                        tier=1,
                        code="T1-SLACK",
                        activity_id=activity_prog.activity_id,
                        weeks_early=abs(activity_prog.delay_weeks),
                    )
                )

        return triggers

    def _check_t2_triggers(
        self,
        canonical: CanonicalModel,
        report: WeeklyProgressReport,
        current_week: int,
    ) -> list[ReplannTrigger]:
        triggers: list[ReplannTrigger] = []

        for activity_prog in report.activities:
            if activity_prog.pct_completude >= 1.0:
                continue

            # T2-DELAY: activity is 1+ weeks behind
            if activity_prog.delay_weeks >= _T2_DELAY_MIN_WEEKS:
                triggers.append(
                    ReplannTrigger(
                        tier=2,
                        code="T2-DELAY",
                        activity_id=activity_prog.activity_id,
                        delay_weeks=activity_prog.delay_weeks,
                        escalate_to="scheduling_engineer",
                    )
                )

        # T2-PRODUCTIVITY-DRIFT: overall SPI below threshold for this report
        if report.spi < _T2_PRODUCTIVITY_DRIFT_THRESHOLD and report.spi > 0:
            triggers.append(
                ReplannTrigger(
                    tier=2,
                    code="T2-PRODUCTIVITY-DRIFT",
                    escalate_to="scheduling_engineer",
                    usage_pct=report.spi,
                )
            )

        return triggers

    def _check_t3_triggers(
        self,
        canonical: CanonicalModel,
        report: WeeklyProgressReport,
        current_week: int,
    ) -> list[ReplannTrigger]:
        triggers: list[ReplannTrigger] = []

        # T3-DEADLINE: forecast exceeds contract deadline
        deadline_weeks = canonical.cronograma.makespan_weeks if canonical.cronograma else 0
        if deadline_weeks > 0 and report.forecast_completion_week > deadline_weeks + _T3_DEADLINE_OVERRUN:
            days_late = (report.forecast_completion_week - deadline_weeks) * 7
            triggers.append(
                ReplannTrigger(
                    tier=3,
                    code="T3-DEADLINE",
                    forecast_week=report.forecast_completion_week,
                    days_late=days_late,
                    escalate_to="director",
                )
            )

        # T3-CASCADE: count how many activities are behind (proxy for cascade risk)
        behind_count = sum(1 for a in report.activities if a.delay_weeks >= _T2_DELAY_MIN_WEEKS)
        if behind_count >= 8:
            triggers.append(
                ReplannTrigger(
                    tier=3,
                    code="T3-CASCADE",
                    escalate_to="director",
                )
            )

        return triggers
