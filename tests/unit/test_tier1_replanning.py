"""Tier 1 coverage — application/replanning: assessor, detector, validator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from concilium.application.progress.models import ActivityProgress, WeeklyProgressReport
from concilium.application.replanning.assessor import ImpactAssessor
from concilium.application.replanning.detector import ReplannTriggerDetector
from concilium.application.replanning.models import ReplannCandidate, ReplannTrigger
from concilium.application.replanning.validator import ReplannValidator

# ── helpers ───────────────────────────────────────────────────────────────────


def _candidate(
    name="Adicionar turno noturno",
    schedule_delta_weeks=-1.0,
    cost_delta=50_000.0,
) -> ReplannCandidate:
    return ReplannCandidate(
        name=name,
        description="Acelera atividade crítica",
        schedule_delta_weeks=schedule_delta_weeks,
        cost_delta=cost_delta,
    )


def _canonical(makespan_weeks=20, replanning_history=None) -> MagicMock:
    c = MagicMock()
    c.cronograma = MagicMock()
    c.cronograma.makespan_weeks = makespan_weeks
    c.cronograma.scheduled_activities = []
    c.replanning_history = replanning_history or []
    c.projeto = MagicMock(spec=[])  # sem multa_atraso_per_day → usa default
    return c


def _activity_progress(
    activity_id="EAP-01",
    pct_completude=0.5,
    delay_weeks=0.0,
) -> ActivityProgress:
    return ActivityProgress(
        activity_id=activity_id,
        quantidade_planejada_total=100.0,
        quantidade_realizada_total=pct_completude * 100.0,
        pct_completude=pct_completude,
        delay_weeks=delay_weeks,
    )


def _report(
    spi=1.0,
    forecast_completion_week=15,
    activities=None,
) -> WeeklyProgressReport:
    return WeeklyProgressReport(
        project_id="proj-001",
        week_key="2026-W10",
        spi=spi,
        forecast_completion_week=forecast_completion_week,
        activities=activities or [],
    )


# ── ImpactAssessor ────────────────────────────────────────────────────────────


class TestImpactAssessor:
    def setup_method(self):
        self.assessor = ImpactAssessor()

    def test_proceed_quando_beneficio_alto(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=-3.0, cost_delta=0.0)
        result = self.assessor.assess(canonical, c, days_late_current=30.0)
        assert result.recommendation == "PROCEED"
        assert result.penalty_avoided > 0

    def test_accept_delay_quando_custo_alto_sem_prazo(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=0.0, cost_delta=500_000.0)
        result = self.assessor.assess(canonical, c, days_late_current=0.0)
        assert result.recommendation == "ACCEPT_DELAY"
        assert result.net_benefit < 0

    def test_negotiate_quando_beneficio_pequeno(self):
        canonical = _canonical()
        # pequena economia de prazo e custo baixo
        c = _candidate(schedule_delta_weeks=-0.1, cost_delta=100.0)
        result = self.assessor.assess(canonical, c, days_late_current=1.0)
        # net_benefit positivo mas menor que 50k → NEGOTIATE
        assert result.recommendation in ("NEGOTIATE_EXTENSION", "ACCEPT_DELAY")

    def test_usa_multa_do_canonical_se_disponivel(self):
        canonical = _canonical()
        canonical.projeto.multa_atraso_per_day = 50_000.0
        c = _candidate(schedule_delta_weeks=-2.0, cost_delta=0.0)
        result = self.assessor.assess(canonical, c, days_late_current=14.0)
        assert result.penalty_avoided == 14 * 50_000.0

    def test_sem_atraso_penalty_avoided_zero(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=-1.0, cost_delta=10_000.0)
        result = self.assessor.assess(canonical, c, days_late_current=0.0)
        assert result.penalty_avoided == 0.0

    def test_schedule_delta_days_calculado(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=-2.0, cost_delta=0.0)
        result = self.assessor.assess(canonical, c)
        assert result.schedule_delta_days == -14.0

    def test_assess_all_ordena_por_beneficio(self):
        canonical = _canonical()
        c1 = _candidate("C1", schedule_delta_weeks=-3.0, cost_delta=0.0)
        c2 = _candidate("C2", schedule_delta_weeks=0.0, cost_delta=1_000_000.0)
        results = self.assessor.assess_all(canonical, [c1, c2], days_late_current=30.0)
        assert results[0].net_benefit >= results[1].net_benefit

    def test_assess_all_lista_vazia(self):
        canonical = _canonical()
        assert self.assessor.assess_all(canonical, []) == []

    def test_efficiency_gain_apenas_com_cost_delta_negativo(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=0.0, cost_delta=-100_000.0)
        result = self.assessor.assess(canonical, c)
        assert result.efficiency_gain > 0.0

    def test_disruption_cost_proporcional_ao_delta(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=0.0, cost_delta=200_000.0)
        result = self.assessor.assess(canonical, c)
        assert abs(result.disruption_cost - 200_000.0 * 0.10) < 1.0


# ── ReplannTriggerDetector ────────────────────────────────────────────────────


class TestReplannTriggerDetector:
    def setup_method(self):
        self.detector = ReplannTriggerDetector()

    def _canonical_com_atividade(self, activity_id="EAP-01", dist_weeks=5):
        """Canonical com uma atividade agendada com distribuição semanal."""
        sa = MagicMock()
        sa.activity_id = activity_id
        sa.distribuicao_semanal = {f"2026-W{i:02d}": {} for i in range(1, dist_weeks + 1)}
        c = _canonical()
        c.cronograma.scheduled_activities = [sa]
        return c

    def test_sem_atividades_sem_triggers(self):
        triggers = self.detector.check_triggers(_canonical(), _report(), current_week=5)
        assert triggers == []

    def test_t2_delay_atividade_atrasada(self):
        canonical = self._canonical_com_atividade()
        report = _report(
            activities=[_activity_progress("EAP-01", pct_completude=0.2, delay_weeks=2.0)]
        )
        triggers = self.detector.check_triggers(canonical, report, current_week=5)
        codes = [t.code for t in triggers]
        assert "T2-DELAY" in codes

    def test_t1_early_atividade_completa_adiantada(self):
        canonical = self._canonical_com_atividade()
        report = _report(
            activities=[_activity_progress("EAP-01", pct_completude=1.0, delay_weeks=-2.0)]
        )
        triggers = self.detector.check_triggers(canonical, report, current_week=5)
        codes = [t.code for t in triggers]
        assert "T1-EARLY" in codes

    def test_t1_slack_adiantada_nao_completa(self):
        canonical = self._canonical_com_atividade()
        report = _report(
            activities=[_activity_progress("EAP-01", pct_completude=0.7, delay_weeks=-2.0)]
        )
        triggers = self.detector.check_triggers(canonical, report, current_week=5)
        codes = [t.code for t in triggers]
        assert "T1-SLACK" in codes

    def test_t2_productivity_drift_spi_baixo(self):
        triggers = self.detector.check_triggers(
            _canonical(), _report(spi=0.5), current_week=5
        )
        codes = [t.code for t in triggers]
        assert "T2-PRODUCTIVITY-DRIFT" in codes

    def test_t2_productivity_drift_nao_dispara_se_spi_zero(self):
        triggers = self.detector.check_triggers(
            _canonical(), _report(spi=0.0), current_week=5
        )
        codes = [t.code for t in triggers]
        assert "T2-PRODUCTIVITY-DRIFT" not in codes

    def test_t3_deadline_forecast_excede_makespan(self):
        canonical = _canonical(makespan_weeks=10)
        report = _report(forecast_completion_week=15)
        triggers = self.detector.check_triggers(canonical, report, current_week=5)
        codes = [t.code for t in triggers]
        assert "T3-DEADLINE" in codes
        t3 = next(t for t in triggers if t.code == "T3-DEADLINE")
        assert t3.days_late == (15 - 10) * 7

    def test_t3_cascade_muitas_atividades_atrasadas(self):
        canonical = _canonical()
        activities = [
            _activity_progress(f"EAP-{i:02d}", delay_weeks=2.0) for i in range(10)
        ]
        report = _report(activities=activities)
        triggers = self.detector.check_triggers(canonical, report, current_week=5)
        codes = [t.code for t in triggers]
        assert "T3-CASCADE" in codes

    def test_atividade_completa_nao_dispara_t2_delay(self):
        canonical = self._canonical_com_atividade()
        report = _report(
            activities=[_activity_progress("EAP-01", pct_completude=1.0, delay_weeks=5.0)]
        )
        triggers = self.detector.check_triggers(canonical, report, current_week=5)
        codes = [t.code for t in triggers]
        assert "T2-DELAY" not in codes

    def test_sem_cronograma_skips_t1(self):
        canonical = _canonical()
        canonical.cronograma.scheduled_activities = []
        report = _report(
            activities=[_activity_progress("EAP-01", pct_completude=1.0, delay_weeks=-3.0)]
        )
        triggers = self.detector.check_triggers(canonical, report, current_week=5)
        codes = [t.code for t in triggers]
        assert "T1-EARLY" not in codes


# ── ReplannValidator ──────────────────────────────────────────────────────────


class TestReplannValidator:
    def setup_method(self):
        self.validator = ReplannValidator()

    def test_candidato_valido_retorna_ok(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=1.0)
        validacoes = self.validator.validate(c, canonical)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-REPLAN-OK" in codigos
        assert not any(v.status == "ERRO" for v in validacoes)

    def test_val_replan_02_extensao_excessiva(self):
        canonical = _canonical()
        c = _candidate(schedule_delta_weeks=5.0)
        validacoes = self.validator.validate(c, canonical)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-REPLAN-02" in codigos

    def test_val_replan_05_replan_muito_recente(self):
        recente = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        canonical = _canonical(replanning_history=[{"approved_at": recente}])
        c = _candidate(schedule_delta_weeks=1.0)
        validacoes = self.validator.validate(c, canonical)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-REPLAN-05" in codigos

    def test_val_replan_05_replan_antigo_ok(self):
        antigo = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        canonical = _canonical(replanning_history=[{"approved_at": antigo}])
        c = _candidate(schedule_delta_weeks=1.0)
        validacoes = self.validator.validate(c, canonical)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-REPLAN-05" not in codigos

    def test_val_replan_05_sem_historico(self):
        canonical = _canonical(replanning_history=[])
        c = _candidate(schedule_delta_weeks=1.0)
        validacoes = self.validator.validate(c, canonical)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-REPLAN-05" not in codigos

    def test_val_replan_05_approved_at_none(self):
        canonical = _canonical(replanning_history=[{"approved_at": None}])
        c = _candidate(schedule_delta_weeks=1.0)
        validacoes = self.validator.validate(c, canonical)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-REPLAN-05" not in codigos

    def test_val_replan_05_approved_at_datetime_objeto(self):
        recente = datetime.now(UTC) - timedelta(days=1)
        canonical = _canonical(replanning_history=[{"approved_at": recente}])
        c = _candidate(schedule_delta_weeks=1.0)
        validacoes = self.validator.validate(c, canonical)
        codigos = [v.codigo for v in validacoes]
        assert "VAL-REPLAN-05" in codigos

    def test_val_replan_05_approved_at_string_invalida(self):
        canonical = _canonical(replanning_history=[{"approved_at": "nao-e-data"}])
        c = _candidate(schedule_delta_weeks=1.0)
        # não deve lançar exceção
        validacoes = self.validator.validate(c, canonical)
        assert validacoes is not None

    def test_val_replan_05_tipo_nao_suportado(self):
        canonical = _canonical(replanning_history=[{"approved_at": 12345}])
        c = _candidate(schedule_delta_weeks=1.0)
        validacoes = self.validator.validate(c, canonical)
        assert validacoes is not None


# ── ReplannCandidate / ReplannTrigger ─────────────────────────────────────────


class TestReplannModels:
    def test_candidate_id_gerado(self):
        c1 = _candidate()
        c2 = _candidate()
        assert c1.candidate_id != c2.candidate_id

    def test_trigger_id_gerado(self):
        t1 = ReplannTrigger(tier=1, code="T1-EARLY")
        t2 = ReplannTrigger(tier=1, code="T1-EARLY")
        assert t1.trigger_id != t2.trigger_id

    def test_trigger_campos_opcionais(self):
        t = ReplannTrigger(tier=2, code="T2-DELAY")
        assert t.activity_id is None
        assert t.delay_weeks is None
        assert t.escalate_to is None
