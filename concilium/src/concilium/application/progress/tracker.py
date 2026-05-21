"""ADR-003 — ProgressTracker: records actuals and computes SPI/forecast."""

from __future__ import annotations

from typing import TYPE_CHECKING

from concilium.application.progress.models import ActivityProgress, ProgressUpdate, WeeklyProgressReport
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

if TYPE_CHECKING:
    pass

# Thresholds for drift detection
_DELAY_TIER2_WEEKS = 1.0
_SPI_TIER2_THRESHOLD = 0.80


def _iso_week_to_int(week_key: str) -> int:
    """Convert 'AAAA-Www' to comparable integer AAAAWW."""
    year, week = week_key.split("-W")
    return int(year) * 100 + int(week)


def _planned_qty_up_to_week(
    cronograma_item: dict,
    week_key: str,
) -> float:
    """Sum planned quantities from distribuicao_semanal up to and including week_key."""
    target = _iso_week_to_int(week_key)
    total = 0.0
    for wk, dist in cronograma_item.get("distribuicao_semanal", {}).items():
        if _iso_week_to_int(wk) <= target:
            total += dist.get("qtd_executada", 0.0) if isinstance(dist, dict) else getattr(dist, "qtd_executada", 0.0)
    return total


def _ru_validate_dup(existing: list, update: object) -> object | None:
    """VAL-PROG-04: checks for duplicate week entry."""
    from concilium.domain.models.canonical import ValidacaoItem

    if any(u.week_key == update.week_key and u.activity_id == update.activity_id for u in existing):
        return ValidacaoItem(
            codigo="VAL-PROG-04",
            status="AVISO",
            mensagem=f"Possível entrada dupla: {update.activity_id} na semana {update.week_key}",
        )
    return None


def _ru_validate_over_report(total_after: float, qtd_planejada_total: float, activity_id: str) -> object | None:
    """VAL-PROG-03: checks if total realizado exceeds planejado."""
    from concilium.domain.models.canonical import ValidacaoItem

    if qtd_planejada_total > 0 and total_after > qtd_planejada_total * 1.001:
        return ValidacaoItem(
            codigo="VAL-PROG-03",
            status="ERRO",
            mensagem=(
                f"Total realizado ({total_after:.2f}) excede planejado ({qtd_planejada_total:.2f}) para {activity_id}"
            ),
        )
    return None


def _ru_validate_weekly(canonical: object, update: object) -> object | None:
    """VAL-PROG-01: checks for over-reporting in a single week vs planned qty."""
    from concilium.domain.models.canonical import ValidacaoItem

    acts = canonical.cronograma.scheduled_activities if canonical.cronograma else []
    cron_item = next((sa for sa in acts if sa.activity_id == update.activity_id), None)
    if not cron_item or update.week_key not in cron_item.distribuicao_semanal:
        return None
    dist = cron_item.distribuicao_semanal[update.week_key]
    planned_wk = getattr(dist, "qtd_executada", 0.0)
    if planned_wk > 0 and update.quantidade_realizada > planned_wk * 1.5:
        return ValidacaoItem(
            codigo="VAL-PROG-01",
            status="AVISO",
            mensagem=(
                f"Quantidade realizada ({update.quantidade_realizada:.2f}) "
                f"é >150% do planejado ({planned_wk:.2f}) na semana {update.week_key}"
            ),
        )
    return None


def _ru_validate_efficiency(existing: list, update: object, activity_id: str) -> object | None:
    """VAL-PROG-02: checks sustained low efficiency over 2+ weeks."""
    from concilium.domain.models.canonical import ValidacaoItem

    recent = [u for u in existing[-1:]] + [update]
    if len(recent) >= 2 and all(u.efficiency_observed < 0.3 for u in recent):
        return ValidacaoItem(
            codigo="VAL-PROG-02",
            status="AVISO",
            mensagem=f"Eficiência observada <30% por 2+ semanas em {activity_id}",
        )
    return None


def _ru_run_validations(canonical: object, update: object, existing: list, qtd_planejada_total: float) -> list:
    """Runs all VAL-PROG-XX validation checks and returns list of ValidacaoItem."""
    validacoes = []
    total_before = sum(u.quantidade_realizada for u in existing)
    total_after = total_before + update.quantidade_realizada
    dup = _ru_validate_dup(existing, update)
    if dup:
        validacoes.append(dup)
    over = _ru_validate_over_report(total_after, qtd_planejada_total, update.activity_id)
    if over:
        validacoes.append(over)
    weekly = _ru_validate_weekly(canonical, update)
    if weekly:
        validacoes.append(weekly)
    eff = _ru_validate_efficiency(existing, update, update.activity_id)
    if eff:
        validacoes.append(eff)
    return validacoes


class ProgressTracker:
    """Registra atualizações de progresso e computa métricas (ADR-003)."""

    def record_update(
        self,
        canonical: CanonicalModel,
        update: ProgressUpdate,
    ) -> SkillResult:
        """Appends a ProgressUpdate to canonical.progresso[activity_id].

        Emits VAL-PROG-XX validations on anomalies.
        Never modifies existing updates (append-only contract).
        """
        eap_item = next((e for e in canonical.eap if e.item_id == update.activity_id), None)
        if eap_item is None:
            return SkillResult(
                canonical,
                [
                    ValidacaoItem(
                        codigo="VAL-PROG-00",
                        status="ERRO",
                        mensagem=f"activity_id '{update.activity_id}' não encontrado na EAP",
                    )
                ],
            )

        existing = list(canonical.progresso.get(update.activity_id, []))
        validacoes = _ru_run_validations(canonical, update, existing, eap_item.quantitativo)

        new_progresso = {**canonical.progresso, update.activity_id: existing + [update]}
        novo = canonical.model_copy(update={"progresso": new_progresso})

        if not any(v.status == "ERRO" for v in validacoes):
            validacoes.append(ValidacaoItem(codigo="VAL-PROG-OK", status="OK"))

        return SkillResult(novo, validacoes)

    def compute_spi(
        self,
        canonical: CanonicalModel,
        week_key: str,
    ) -> float:
        """SPI = Σ earned_value / Σ planned_value for all activities up to week_key.

        earned_value_activity = (qty_realizada / qty_planejada_total) * weight
        Returns 1.0 if no planned data is available.
        """
        total_earned = 0.0
        total_planned = 0.0

        for eap_item in canonical.eap:
            if eap_item.quantitativo <= 0:
                continue

            planned_to_week = 0.0
            cron_item = next(
                (
                    sa
                    for sa in (canonical.cronograma.scheduled_activities if canonical.cronograma else [])
                    if sa.activity_id == eap_item.item_id
                ),
                None,
            )
            if cron_item:
                planned_to_week = _planned_qty_up_to_week(
                    {"distribuicao_semanal": {k: v for k, v in cron_item.distribuicao_semanal.items()}},
                    week_key,
                )

            updates = canonical.progresso.get(eap_item.item_id, [])
            realized = sum(
                u.quantidade_realizada for u in updates if _iso_week_to_int(u.week_key) <= _iso_week_to_int(week_key)
            )

            total_planned += planned_to_week
            total_earned += realized

        if total_planned <= 0:
            return 1.0
        return min(total_earned / total_planned, 2.0)  # cap at 2x to avoid outliers

    def forecast_completion(
        self,
        canonical: CanonicalModel,
        current_week_int: int,
    ) -> int:
        """Linear forecast: remaining_qty / avg_weekly_rate -> remaining weeks.

        current_week_int: integer week number (1-based, from project start)
        Returns estimated end week number.
        """
        if current_week_int <= 0:
            return current_week_int

        total_planned = sum(e.quantitativo for e in canonical.eap if e.quantitativo > 0)
        total_realized = sum(sum(u.quantidade_realizada for u in updates) for updates in canonical.progresso.values())
        remaining = max(0.0, total_planned - total_realized)

        if remaining <= 0:
            return current_week_int

        if current_week_int > 0 and total_realized > 0:
            avg_rate = total_realized / current_week_int  # qty per week so far
        else:
            return current_week_int + 1  # no data yet

        if avg_rate <= 0:
            return current_week_int + 999  # unable to forecast

        weeks_remaining = int(remaining / avg_rate) + 1
        return current_week_int + weeks_remaining

    def detect_drift(
        self,
        canonical: CanonicalModel,
        week_key: str,
    ) -> list[str]:
        """Return alert strings for activities with delay >= threshold."""
        alerts: list[str] = []

        for eap_item in canonical.eap:
            if eap_item.quantitativo <= 0:
                continue

            cron_item = next(
                (
                    sa
                    for sa in (canonical.cronograma.scheduled_activities if canonical.cronograma else [])
                    if sa.activity_id == eap_item.item_id
                ),
                None,
            )
            if not cron_item:
                continue

            planned_to_week = _planned_qty_up_to_week(
                {"distribuicao_semanal": {k: v for k, v in cron_item.distribuicao_semanal.items()}},
                week_key,
            )

            updates = canonical.progresso.get(eap_item.item_id, [])
            realized = sum(
                u.quantidade_realizada for u in updates if _iso_week_to_int(u.week_key) <= _iso_week_to_int(week_key)
            )

            if planned_to_week <= 0:
                continue

            spi_activity = realized / planned_to_week if planned_to_week > 0 else 1.0

            if spi_activity < _SPI_TIER2_THRESHOLD:
                delay_pct = (1.0 - spi_activity) * 100
                alerts.append(
                    f"{eap_item.item_id}: {delay_pct:.0f}% abaixo do planejado "
                    f"(realizado {realized:.1f} / planejado {planned_to_week:.1f})"
                )

        return alerts

    def build_progress_report(
        self,
        canonical: CanonicalModel,
        week_key: str,
        project_id: str,
    ) -> WeeklyProgressReport:
        """Generate a full WeeklyProgressReport for the given week."""
        activities: list[ActivityProgress] = []

        for eap_item in canonical.eap:
            updates_all = canonical.progresso.get(eap_item.item_id, [])
            total_realized = sum(u.quantidade_realizada for u in updates_all)
            pct = total_realized / eap_item.quantitativo if eap_item.quantitativo > 0 else 0.0

            # Estimate delay: compare pct to expected pct at this week
            cron_item = next(
                (
                    sa
                    for sa in (canonical.cronograma.scheduled_activities if canonical.cronograma else [])
                    if sa.activity_id == eap_item.item_id
                ),
                None,
            )
            expected_pct = 0.0
            if cron_item and eap_item.quantitativo > 0:
                planned = _planned_qty_up_to_week(
                    {"distribuicao_semanal": {k: v for k, v in cron_item.distribuicao_semanal.items()}},
                    week_key,
                )
                expected_pct = planned / eap_item.quantitativo

            pct_gap = expected_pct - pct
            delay_weeks = pct_gap / (1.0 / max(len(cron_item.distribuicao_semanal), 1)) if cron_item else 0.0

            activities.append(
                ActivityProgress(
                    activity_id=eap_item.item_id,
                    quantidade_planejada_total=eap_item.quantitativo,
                    quantidade_realizada_total=round(total_realized, 4),
                    pct_completude=round(pct, 4),
                    delay_weeks=round(delay_weeks, 2),
                    updates=list(updates_all),
                )
            )

        spi = self.compute_spi(canonical, week_key)
        week_int = _iso_week_to_int(week_key) % 100  # approximate
        forecast = self.forecast_completion(canonical, week_int)
        alerts = self.detect_drift(canonical, week_key)

        return WeeklyProgressReport(
            project_id=project_id,
            week_key=week_key,
            activities=activities,
            spi=round(spi, 4),
            forecast_completion_week=forecast,
            drift_alerts=alerts,
        )
