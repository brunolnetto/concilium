"""Coverage for diff_service, scheduling/models, progress/tracker, _explorador."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestGerарInterpretacaoImprovements:
    def _interp(self, delta_custo, delta_cronograma, delta_margem):
        from concilium.application.benchmarks.diff_service import BenchmarkDiffService

        return BenchmarkDiffService._gerar_interpretacao(delta_custo, delta_cronograma, delta_margem)

    def test_improvement_cost_lower(self):
        """Line 90: delta_custo < -0.5."""
        result = self._interp(-5.0, 0, 0.0)
        assert "Melhoria" in result and "custo" in result

    def test_improvement_cronograma_shorter(self):
        """Line 95: delta_cronograma < -1."""
        result = self._interp(0.0, -3, 0.0)
        assert "semanas menor" in result

    def test_improvement_margem_better(self):
        """Line 100: delta_margem > 0.5."""
        result = self._interp(0.0, 0, 2.0)
        assert "Margem melhorou" in result

    def test_all_improvements_combined(self):
        """Lines 90, 95, 100 all at once."""
        result = self._interp(-10.0, -5, 3.0)
        assert "Melhoria" in result
        assert "semanas menor" in result
        assert "Margem melhorou" in result


class TestActivityPostInit:
    def _make_activity(self, **kwargs):
        from concilium.application.scheduling.models import Activity

        defaults = {"activity_id": "A1", "description": "Test", "duration_weeks": 3, "required_resources": {"ESC": 2}}
        defaults.update(kwargs)
        return Activity(**defaults)

    def test_duration_weeks_zero_raises(self):
        """Line 41: duration_weeks < 1."""
        with pytest.raises(ValueError, match="duration_weeks must be >= 1"):
            self._make_activity(duration_weeks=0)

    def test_window_weeks_too_small_raises(self):
        """Line 43: window_weeks < duration_weeks."""
        with pytest.raises(ValueError, match="window_weeks"):
            self._make_activity(duration_weeks=5, window_weeks=3)

    def test_ramp_profile_wrong_length_raises(self):
        """Line 46: ramp_profile length != duration_weeks."""
        with pytest.raises(ValueError, match="ramp_profile length"):
            self._make_activity(duration_weeks=3, ramp_profile=[0.3, 0.7])


class TestActivityDAGCycle:
    def test_cycle_raises(self):
        """Line 111: cycle in DAG."""
        from concilium.application.scheduling.models import Activity, ActivityDAG

        a1 = Activity("A1", "Act1", 1, {"W": 1})
        a2 = Activity("A2", "Act2", 1, {"W": 1})
        dag = ActivityDAG(activities=[a1, a2], precedence=[("A1", "A2"), ("A2", "A1")])
        with pytest.raises(ValueError, match="cycle"):
            dag.topological_order()


class TestScheduleMetricsNoDeadline:
    def _metrics(self):
        from concilium.application.scheduling.models import ScheduleMetrics

        return ScheduleMetrics(
            makespan=10,
            resource_leveling_score=0.8,
            idle_time=2,
            activity_fragmentation=0,
            critical_path_slack_min=1.0,
            resource_utilization_avg=0.75,
        )

    def test_quality_score_no_deadline(self):
        """Line 168: deadline_weeks=0."""
        assert 0.0 < self._metrics().quality_score(deadline_weeks=0) < 1.0

    def test_quality_score_with_deadline_higher(self):
        """Lines 165-166 vs 168."""
        m = self._metrics()
        assert m.quality_score(deadline_weeks=12) > m.quality_score(deadline_weeks=0)


class TestRuValidateWeekly:
    def _canonical(self, week_key, planned):
        dist = SimpleNamespace(qtd_executada=planned)
        sa = SimpleNamespace(activity_id="A1", distribuicao_semanal={week_key: dist})
        return SimpleNamespace(cronograma=SimpleNamespace(scheduled_activities=[sa]))

    def _update(self, week_key, qty):
        return SimpleNamespace(activity_id="A1", week_key=week_key, quantidade_realizada=qty)

    def test_over_report_triggers_warning(self):
        """Lines 74-77."""
        from concilium.application.progress.tracker import _ru_validate_weekly

        result = _ru_validate_weekly(self._canonical("2024-W01", 10.0), self._update("2024-W01", 20.0))
        assert result is not None and result.codigo == "VAL-PROG-01"

    def test_within_threshold_returns_none(self):
        """Line 85."""
        from concilium.application.progress.tracker import _ru_validate_weekly

        assert _ru_validate_weekly(self._canonical("2024-W01", 10.0), self._update("2024-W01", 12.0)) is None

    def test_weekly_appended_to_validacoes(self):
        """Line 115."""
        from concilium.application.progress.tracker import _ru_run_validations

        vs = _ru_run_validations(self._canonical("2024-W01", 10.0), self._update("2024-W01", 20.0), [], 100.0)
        assert any(v.codigo == "VAL-PROG-01" for v in vs)


class TestFindCronItemNotFound:
    def test_returns_none(self):
        """Line 127."""
        from concilium.application.progress.tracker import _find_cron_item

        sa = SimpleNamespace(activity_id="A2")
        canonical = SimpleNamespace(cronograma=SimpleNamespace(scheduled_activities=[sa]))
        assert _find_cron_item(canonical, "A1") is None


class TestDetectDriftSkips:
    def test_skips_zero_quantitativo(self):
        """Line 250."""
        from concilium.application.progress.tracker import ProgressTracker

        canonical = MagicMock()
        canonical.eap = [SimpleNamespace(item_id="A1", quantitativo=0.0)]
        canonical.progresso = {}
        canonical.cronograma = SimpleNamespace(scheduled_activities=[])
        assert ProgressTracker().detect_drift(canonical, "2024-W10") == []

    def test_skips_no_cron_entry(self):
        """Line 254."""
        from concilium.application.progress.tracker import ProgressTracker

        canonical = MagicMock()
        canonical.eap = [SimpleNamespace(item_id="A1", quantitativo=100.0)]
        canonical.progresso = {"A1": []}
        canonical.cronograma = SimpleNamespace(scheduled_activities=[])
        assert ProgressTracker().detect_drift(canonical, "2024-W10") == []


class TestExploradorInternals:
    def _mod(self):
        import sys

        from concilium.application.skills import run_replanejamento_e_cenarios  # noqa: F401

        return sys.modules["_concilium_skillpkg_11_replanejamento_e_cenarios._explorador"]

    def test_classify_status_amarelo(self):
        """Lines 58-59: AMARELO."""
        assert self._mod()._classify_status(0.07, {"min": 0.08}, {"min": 0.06}) == "AMARELO"

    def test_classify_status_vermelho(self):
        """Lines 58, 60: VERMELHO."""
        assert self._mod()._classify_status(0.03, {"min": 0.08}, {"min": 0.06}) == "VERMELHO"

    def test_build_levers_zero_venda(self):
        """Line 77: venda <= 0."""
        canonical = MagicMock()
        canonical.ponto_equilibrio = []
        assert self._mod()._build_levers(canonical, 0.0) == []

    def test_build_levers_unknown_id_skipped(self):
        """Line 86: lever id not in _LEVER_ID_TO_TIPO."""
        mod = self._mod()
        lv = SimpleNamespace(id="UNKNOWN_XYZ", delta_margin=1000.0, restricoes=[])
        pe = SimpleNamespace(item_id="A1", custo_venda_cpu=100_000.0, levers_equilibrio=[lv])
        canonical = MagicMock()
        canonical.ponto_equilibrio = [pe]
        assert mod._build_levers(canonical, 1_000_000.0) == []

    def test_build_levers_negative_delta_skipped(self):
        """Line 101: delta_rs <= 0."""
        mod = self._mod()
        valid_id = next(iter(mod._LEVER_ID_TO_TIPO))
        lv = SimpleNamespace(id=valid_id, delta_margin=-500.0, restricoes=[])
        pe = SimpleNamespace(item_id="A1", custo_venda_cpu=100_000.0, levers_equilibrio=[lv])
        canonical = MagicMock()
        canonical.ponto_equilibrio = [pe]
        assert mod._build_levers(canonical, 1_000_000.0) == []
