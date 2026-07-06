"""Tier 1 coverage — application/progress: models e tracker."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from concilium.application.progress.models import (
    ActivityProgress,
    ProgressUpdate,
    WeeklyProgressReport,
)
from concilium.application.progress.tracker import (
    ProgressTracker,
    _iso_week_to_int,
    _planned_qty_up_to_week,
    _realized_up_to,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _update(activity_id="EAP-01", week_key="2026-W01", quantidade=10.0, efficiency=0.9) -> ProgressUpdate:
    return ProgressUpdate(
        activity_id=activity_id,
        week_key=week_key,
        quantidade_realizada=quantidade,
        efficiency_observed=efficiency,
        recorded_by="engenheiro",
    )


def _make_canonical(activities: list | None = None, progresso: dict | None = None):
    """Constrói um MagicMock de CanonicalModel com o mínimo necessário para o tracker."""
    canonical = MagicMock()
    canonical.progresso = progresso or {}

    eap_items = []
    for act in activities or []:
        item = MagicMock()
        item.item_id = act["id"]
        item.quantitativo = act.get("qtd", 100.0)
        eap_items.append(item)
    canonical.eap = eap_items

    # Cronograma com scheduled_activities correspondentes
    sched_acts = []
    for act in activities or []:
        sa = MagicMock()
        sa.activity_id = act["id"]
        sa.distribuicao_semanal = act.get("dist", {})
        sched_acts.append(sa)
    canonical.cronograma = MagicMock()
    canonical.cronograma.scheduled_activities = sched_acts
    canonical.cronograma.makespan_weeks = 20

    # model_copy retorna um novo MagicMock com progresso atualizado
    def _model_copy(*, update=None):
        novo = MagicMock()
        novo.progresso = update.get("progresso", {}) if update else {}
        novo.eap = canonical.eap
        novo.cronograma = canonical.cronograma
        return novo

    canonical.model_copy = _model_copy
    return canonical


# ── ProgressUpdate ────────────────────────────────────────────────────────────


class TestProgressUpdate:
    def test_instanciacao_basica(self):
        u = _update()
        assert u.activity_id == "EAP-01"
        assert u.week_key == "2026-W01"
        assert u.notes is None

    def test_update_id_gerado(self):
        u1 = _update()
        u2 = _update()
        assert u1.update_id != u2.update_id

    def test_recorded_at_auto(self):
        u = _update()
        assert u.recorded_at.tzinfo is not None

    def test_frozen(self):
        u = _update()
        with pytest.raises(ValidationError):
            u.quantidade_realizada = 999.0

    def test_rejeita_quantidade_negativa(self):
        with pytest.raises(ValidationError):
            ProgressUpdate(
                activity_id="X",
                week_key="2026-W01",
                quantidade_realizada=-1.0,
                efficiency_observed=0.5,
                recorded_by="eng",
            )

    def test_rejeita_efficiency_acima_1(self):
        with pytest.raises(ValidationError):
            ProgressUpdate(
                activity_id="X",
                week_key="2026-W01",
                quantidade_realizada=10.0,
                efficiency_observed=1.1,
                recorded_by="eng",
            )


# ── ActivityProgress ──────────────────────────────────────────────────────────


class TestActivityProgress:
    def test_instanciacao(self):
        ap = ActivityProgress(
            activity_id="EAP-01",
            quantidade_planejada_total=100.0,
            quantidade_realizada_total=50.0,
            pct_completude=0.5,
            delay_weeks=0.0,
        )
        assert ap.updates == []

    def test_rejeita_pct_acima_1(self):
        with pytest.raises(ValidationError):
            ActivityProgress(
                activity_id="X",
                quantidade_planejada_total=100.0,
                quantidade_realizada_total=110.0,
                pct_completude=1.1,
                delay_weeks=0.0,
            )


# ── WeeklyProgressReport ──────────────────────────────────────────────────────


class TestWeeklyProgressReport:
    def test_instanciacao(self):
        r = WeeklyProgressReport(
            project_id="proj-001",
            week_key="2026-W10",
            spi=0.95,
            forecast_completion_week=22,
        )
        assert r.activities == []
        assert r.drift_alerts == []

    def test_generated_at_auto(self):
        r = WeeklyProgressReport(
            project_id="p",
            week_key="2026-W01",
            spi=1.0,
            forecast_completion_week=10,
        )
        assert r.generated_at.tzinfo is not None


# ── helpers de módulo ─────────────────────────────────────────────────────────


class TestIsoWeekToInt:
    def test_conversao_basica(self):
        assert _iso_week_to_int("2026-W01") == 202601
        assert _iso_week_to_int("2026-W52") == 202652

    def test_ordem_cronologica(self):
        assert _iso_week_to_int("2026-W10") < _iso_week_to_int("2027-W01")


class TestPlannedQtyUpToWeek:
    def test_soma_ate_semana(self):
        dist = {
            "2026-W01": {"qtd_executada": 20.0},
            "2026-W02": {"qtd_executada": 30.0},
            "2026-W03": {"qtd_executada": 50.0},
        }
        assert _planned_qty_up_to_week({"distribuicao_semanal": dist}, "2026-W02") == 50.0

    def test_sem_distribuicao(self):
        assert _planned_qty_up_to_week({}, "2026-W05") == 0.0

    def test_aceita_objeto_com_atributo(self):
        dist_obj = MagicMock()
        dist_obj.qtd_executada = 25.0
        item = {"distribuicao_semanal": {"2026-W01": dist_obj}}
        result = _planned_qty_up_to_week(item, "2026-W01")
        assert result == 25.0


class TestRealizedUpTo:
    def test_soma_ate_semana(self):
        updates = [
            _update(week_key="2026-W01", quantidade=10.0),
            _update(week_key="2026-W02", quantidade=20.0),
            _update(week_key="2026-W03", quantidade=15.0),
        ]
        assert _realized_up_to(updates, "2026-W02") == 30.0

    def test_vazio(self):
        assert _realized_up_to([], "2026-W05") == 0.0


# ── ProgressTracker ───────────────────────────────────────────────────────────


class TestProgressTrackerRecordUpdate:
    def setup_method(self):
        self.tracker = ProgressTracker()

    def test_activity_nao_encontrada_retorna_erro(self):
        canonical = _make_canonical(activities=[])
        result = self.tracker.record_update(canonical, _update("INEXISTENTE"))
        codigos = [v.codigo for v in result.validacoes]
        assert "VAL-PROG-00" in codigos
        assert any(v.status == "ERRO" for v in result.validacoes)

    def test_primeira_atualizacao_ok(self):
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 100.0}])
        result = self.tracker.record_update(canonical, _update("EAP-01", quantidade=10.0))
        assert any(v.codigo == "VAL-PROG-OK" for v in result.validacoes)

    def test_alerta_dup_na_mesma_semana(self):
        update1 = _update("EAP-01", week_key="2026-W01", quantidade=10.0)
        canonical = _make_canonical(
            activities=[{"id": "EAP-01", "qtd": 100.0}],
            progresso={"EAP-01": [update1]},
        )
        update2 = _update("EAP-01", week_key="2026-W01", quantidade=5.0)
        result = self.tracker.record_update(canonical, update2)
        codigos = [v.codigo for v in result.validacoes]
        assert "VAL-PROG-04" in codigos

    def test_alerta_over_report(self):
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 10.0}])
        result = self.tracker.record_update(canonical, _update("EAP-01", quantidade=20.0))
        codigos = [v.codigo for v in result.validacoes]
        assert "VAL-PROG-03" in codigos

    def test_alerta_eficiencia_baixa_2_semanas(self):
        update1 = ProgressUpdate(
            activity_id="EAP-01",
            week_key="2026-W01",
            quantidade_realizada=5.0,
            efficiency_observed=0.2,
            recorded_by="eng",
        )
        canonical = _make_canonical(
            activities=[{"id": "EAP-01", "qtd": 500.0}],
            progresso={"EAP-01": [update1]},
        )
        update2 = ProgressUpdate(
            activity_id="EAP-01",
            week_key="2026-W02",
            quantidade_realizada=5.0,
            efficiency_observed=0.2,
            recorded_by="eng",
        )
        result = self.tracker.record_update(canonical, update2)
        codigos = [v.codigo for v in result.validacoes]
        assert "VAL-PROG-02" in codigos


class TestProgressTrackerComputeSpi:
    def setup_method(self):
        self.tracker = ProgressTracker()

    def test_sem_planejado_retorna_1(self):
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 0.0}])
        assert self.tracker.compute_spi(canonical, "2026-W05") == 1.0

    def test_sem_atividades_retorna_1(self):
        canonical = _make_canonical(activities=[])
        assert self.tracker.compute_spi(canonical, "2026-W05") == 1.0

    def test_realizado_maior_que_planejado_capeado_em_2(self):
        dist = {"2026-W01": {"qtd_executada": 10.0}}
        canonical = _make_canonical(
            activities=[{"id": "EAP-01", "qtd": 10.0, "dist": dist}],
            progresso={"EAP-01": [_update("EAP-01", week_key="2026-W01", quantidade=50.0)]},
        )
        spi = self.tracker.compute_spi(canonical, "2026-W01")
        assert spi <= 2.0

    def test_atividade_sem_cron_item_ignora_planejado(self):
        """Quando a atividade não tem entrada correspondente no cronograma,
        cron_item é None e planned_to_week permanece 0 (branch `if cron_item`
        falso)."""
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 10.0}])
        canonical.cronograma.scheduled_activities = []
        # sem planejado algum -> compute_spi cai no early-return de total_planned<=0
        assert self.tracker.compute_spi(canonical, "2026-W01") == 1.0


class TestProgressTrackerForecastCompletion:
    def setup_method(self):
        self.tracker = ProgressTracker()

    def test_sem_progresso_retorna_semana_mais_1(self):
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 100.0}])
        assert self.tracker.forecast_completion(canonical, 5) == 6

    def test_tudo_completo_retorna_semana_atual(self):
        canonical = _make_canonical(
            activities=[{"id": "EAP-01", "qtd": 50.0}],
            progresso={"EAP-01": [_update("EAP-01", quantidade=50.0)]},
        )
        assert self.tracker.forecast_completion(canonical, 5) == 5

    def test_current_week_zero_retorna_zero(self):
        canonical = _make_canonical(activities=[])
        assert self.tracker.forecast_completion(canonical, 0) == 0

    def test_avg_rate_underflows_to_zero_retorna_nao_previsivel(self):
        """total_realized positivo porém subnormal faz avg_rate = total_realized /
        current_week_int arredondar para 0.0 por underflow de ponto flutuante,
        exercitando o ramo `avg_rate <= 0` (linha 238-239 de tracker.py)."""
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 1e10}])
        canonical.progresso = {"EAP-01": [_update("EAP-01", quantidade=5e-324)]}
        assert self.tracker.forecast_completion(canonical, 2) == 2 + 999


class TestProgressTrackerDetectDrift:
    def setup_method(self):
        self.tracker = ProgressTracker()

    def test_sem_planejado_nao_gera_alerta(self):
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 100.0, "dist": {}}])
        alerts = self.tracker.detect_drift(canonical, "2026-W05")
        assert alerts == []

    def test_atividade_muito_atrasada_gera_alerta(self):
        dist = {"2026-W01": {"qtd_executada": 50.0}, "2026-W02": {"qtd_executada": 50.0}}
        canonical = _make_canonical(
            activities=[{"id": "EAP-01", "qtd": 100.0, "dist": dist}],
            progresso={"EAP-01": [_update("EAP-01", week_key="2026-W01", quantidade=5.0)]},
        )
        alerts = self.tracker.detect_drift(canonical, "2026-W02")
        assert len(alerts) > 0
        assert "EAP-01" in alerts[0]


class TestProgressTrackerBuildReport:
    def setup_method(self):
        self.tracker = ProgressTracker()

    def test_retorna_weekly_progress_report(self):
        dist = {"2026-W01": {"qtd_executada": 20.0}}
        canonical = _make_canonical(
            activities=[{"id": "EAP-01", "qtd": 100.0, "dist": dist}],
            progresso={"EAP-01": [_update("EAP-01", week_key="2026-W01", quantidade=20.0)]},
        )
        report = self.tracker.build_progress_report(canonical, "2026-W01", "proj-001")
        assert isinstance(report, WeeklyProgressReport)
        assert report.project_id == "proj-001"
        assert len(report.activities) == 1

    def test_pct_completude_calculado(self):
        dist = {"2026-W01": {"qtd_executada": 50.0}}
        canonical = _make_canonical(
            activities=[{"id": "EAP-01", "qtd": 100.0, "dist": dist}],
            progresso={"EAP-01": [_update("EAP-01", week_key="2026-W01", quantidade=50.0)]},
        )
        report = self.tracker.build_progress_report(canonical, "2026-W01", "p")
        assert abs(report.activities[0].pct_completude - 0.5) < 1e-4

    def test_quantitativo_zero_pula_calculo_expected_pct(self):
        """Com quantitativo<=0 mas cron_item presente, a condição
        `cron_item and eap_item.quantitativo > 0` deve ser falsa por causa do
        segundo operando, pulando o cálculo de expected_pct (linha 293->300)."""
        dist = {"2026-W01": {"qtd_executada": 20.0}}
        canonical = _make_canonical(activities=[{"id": "EAP-01", "qtd": 0.0, "dist": dist}])
        report = self.tracker.build_progress_report(canonical, "2026-W01", "p")
        assert report.activities[0].pct_completude == 0.0
        assert report.activities[0].delay_weeks == 0.0
