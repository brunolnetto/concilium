"""Tests for application/scheduling/selector.py — boost coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSelectSchedulingAlgorithm:
    def test_small_n_selects_cpsat(self):
        from concilium.application.scheduling.selector import select_scheduling_algorithm

        strategy = select_scheduling_algorithm(100, 3, 20, 0.1)
        assert strategy.algorithm == "CP-SAT"

    def test_large_n_selects_lns(self):
        from concilium.application.scheduling.selector import select_scheduling_algorithm

        strategy = select_scheduling_algorithm(300, 5, 30, 0.1)
        assert strategy.algorithm == "LNS"

    def test_boundary_n_200_uses_cpsat(self):
        from concilium.application.scheduling.selector import select_scheduling_algorithm

        strategy = select_scheduling_algorithm(200, 3, 20, 0.1)
        assert strategy.algorithm == "CP-SAT"

    def test_rationale_is_set(self):
        from concilium.application.scheduling.selector import select_scheduling_algorithm

        strategy = select_scheduling_algorithm(50, 2, 10, 0.0)
        assert strategy.rationale


class TestExploreSchedules:
    def _make_dag(self):
        dag = MagicMock()
        dag.activities = {}
        return dag

    def _make_pool(self):
        return MagicMock()

    def _make_strategy(self, algorithm="CP-SAT"):
        from concilium.application.scheduling.models import SchedulingStrategy

        return SchedulingStrategy(
            algorithm=algorithm, heuristics=[], timeout_seconds=60, leveling_pass=False, rationale="test"
        )

    def test_cpsat_success(self):
        from concilium.application.scheduling.selector import explore_schedules

        dag = self._make_dag()
        pool = self._make_pool()

        sched_mock = MagicMock()
        sched_mock.feasible = True
        sched_mock.metrics.quality_score.return_value = 0.9
        sched_mock.makespan = 10

        cpsat_mock = MagicMock()
        cpsat_mock.schedule.return_value = sched_mock

        with patch(
            "concilium.application.scheduling.cpsat_scheduler.CpSatScheduler",
            return_value=cpsat_mock,
        ):
            results = explore_schedules(
                activities=[],
                dag=dag,
                pool=pool,
                deadline_weeks=10,
                strategy=self._make_strategy("CP-SAT"),
            )
        assert len(results) == 1
        assert results[0].heuristic == "CP-SAT"

    def test_cpsat_infeasible_raises_schedule_error(self):
        from concilium.application.scheduling.selector import ScheduleError, explore_schedules

        dag = self._make_dag()
        pool = self._make_pool()

        sched_mock = MagicMock()
        sched_mock.feasible = False

        cpsat_mock = MagicMock()
        cpsat_mock.schedule.return_value = sched_mock

        with (
            patch("concilium.application.scheduling.cpsat_scheduler.CpSatScheduler", return_value=cpsat_mock),
            pytest.raises(ScheduleError),
        ):
            explore_schedules(
                activities=[], dag=dag, pool=pool, deadline_weeks=10, strategy=self._make_strategy("CP-SAT")
            )

    def test_cpsat_unexpected_exception_wrapped_in_schedule_error(self):
        """Erro inesperado (não infeasible) do CP-SAT vira ScheduleError com a causa original."""
        from concilium.application.scheduling.selector import ScheduleError, explore_schedules

        dag = self._make_dag()
        pool = self._make_pool()

        cpsat_mock = MagicMock()
        cpsat_mock.schedule.side_effect = RuntimeError("solver crashed")

        with (
            patch("concilium.application.scheduling.cpsat_scheduler.CpSatScheduler", return_value=cpsat_mock),
            pytest.raises(ScheduleError, match="solver crashed"),
        ):
            explore_schedules(
                activities=[], dag=dag, pool=pool, deadline_weeks=10, strategy=self._make_strategy("CP-SAT")
            )

    def test_cpsat_infeasible_by_estoque_returns_error_result_without_raising(self):
        """ADR-128 F5: infeasibilidade causada por estoque de consumível insuficiente é
        um resultado de negócio — não deve levantar ScheduleError, ao contrário de
        qualquer outra causa de infeasibilidade (test_cpsat_infeasible_raises_schedule_error)."""
        from concilium.application.scheduling.models import EstoqueDelayCause
        from concilium.application.scheduling.selector import explore_schedules

        dag = self._make_dag()
        pool = self._make_pool()

        sched_mock = MagicMock()
        sched_mock.feasible = False
        sched_mock.estoque_delays = [EstoqueDelayCause(resource_id="DIESEL", activity_id="A1", delay_weeks=3)]

        cpsat_mock = MagicMock()
        cpsat_mock.schedule.return_value = sched_mock

        with patch("concilium.application.scheduling.cpsat_scheduler.CpSatScheduler", return_value=cpsat_mock):
            results = explore_schedules(
                activities=[],
                dag=dag,
                pool=pool,
                deadline_weeks=10,
                strategy=self._make_strategy("CP-SAT"),
                replenishable_resources=[MagicMock()],
            )
        assert len(results) == 1
        assert results[0].error == "estoque_insuficiente"
        assert results[0].quality_score == 0.0
        assert results[0].schedule is sched_mock

    def test_cpsat_infeasible_without_replenishable_resources_still_raises(self):
        """Sem replenishable_resources, infeasibilidade continua levantando ScheduleError
        mesmo que sched.estoque_delays (um MagicMock) seja truthy — a checagem exige
        replenishable_resources ter sido passado."""
        from concilium.application.scheduling.models import EstoqueDelayCause
        from concilium.application.scheduling.selector import ScheduleError, explore_schedules

        dag = self._make_dag()
        pool = self._make_pool()

        sched_mock = MagicMock()
        sched_mock.feasible = False
        sched_mock.estoque_delays = [EstoqueDelayCause(resource_id="DIESEL", activity_id="A1", delay_weeks=3)]

        cpsat_mock = MagicMock()
        cpsat_mock.schedule.return_value = sched_mock

        with (
            patch("concilium.application.scheduling.cpsat_scheduler.CpSatScheduler", return_value=cpsat_mock),
            pytest.raises(ScheduleError),
        ):
            explore_schedules(
                activities=[], dag=dag, pool=pool, deadline_weeks=10, strategy=self._make_strategy("CP-SAT")
            )

    def test_serial_scheduler_heuristic(self):
        from concilium.application.scheduling.selector import explore_schedules

        dag = self._make_dag()
        pool = self._make_pool()

        sched_mock = MagicMock()
        sched_mock.feasible = True
        sched_mock.metrics.quality_score.return_value = 0.8
        sched_mock.makespan = 12

        scheduler_mock = MagicMock()
        scheduler_mock.schedule.return_value = sched_mock

        with patch("concilium.application.scheduling.selector.SerialScheduler", return_value=scheduler_mock):
            results = explore_schedules(
                activities=[],
                dag=dag,
                pool=pool,
                deadline_weeks=10,
                heuristics=["MINSLK"],
                # no strategy → falls through to SerialScheduler path
            )
        assert len(results) >= 1

    def test_no_strategy_uses_serial(self):
        from concilium.application.scheduling.selector import explore_schedules

        dag = self._make_dag()
        pool = self._make_pool()

        sched_mock = MagicMock()
        sched_mock.feasible = True
        sched_mock.metrics.quality_score.return_value = 0.5
        sched_mock.makespan = 15

        with patch(
            "concilium.application.scheduling.selector.SerialScheduler",
            return_value=MagicMock(schedule=MagicMock(return_value=sched_mock)),
        ):
            results = explore_schedules(
                activities=[],
                dag=dag,
                pool=pool,
                deadline_weeks=10,
                heuristics=["MINSLK"],
            )
        assert isinstance(results, list)


class TestCompareAllAlgorithms:
    def test_compare_serial_algorithm(self):
        from concilium.application.scheduling.selector import compare_all_algorithms

        dag = MagicMock()
        dag.activities = {}
        pool = MagicMock()

        sched_mock = MagicMock()
        sched_mock.feasible = True
        sched_mock.metrics.quality_score.return_value = 0.7
        sched_mock.makespan = 10

        with patch(
            "concilium.application.scheduling.selector.SerialScheduler",
            return_value=MagicMock(schedule=MagicMock(return_value=sched_mock)),
        ):
            results = compare_all_algorithms(
                activities=[],
                dag=dag,
                pool=pool,
                deadline_weeks=10,
                algorithms=["MINSLK"],
            )
        assert isinstance(results, list)


class TestExploreLnsPaths:
    """Cover LNS paths in explore_schedules (lines 137-156) and compare_all_algorithms (259-261)."""

    def _make_dag_pool(self):
        dag = MagicMock()
        dag.activities = {}
        return dag, MagicMock()

    def _make_strategy(self, algorithm="LNS"):
        from concilium.application.scheduling.models import SchedulingStrategy

        return SchedulingStrategy(
            algorithm=algorithm, heuristics=[], timeout_seconds=0, leveling_pass=False, rationale="test"
        )

    def test_lns_feasible(self):
        from concilium.application.scheduling.selector import explore_schedules

        dag, pool = self._make_dag_pool()
        sched = MagicMock(feasible=True, makespan=10)
        sched.metrics.quality_score.return_value = 0.8
        lns_mock = MagicMock(schedule=MagicMock(return_value=sched))
        oracle_mock = MagicMock()
        with (
            patch("concilium.application.scheduling.lns_scheduler.LnsScheduler", return_value=lns_mock),
            patch("concilium.domain.services.planning.matching_oracle.MatchingOracle", return_value=oracle_mock),
        ):
            results = explore_schedules([], dag, pool, deadline_weeks=10, strategy=self._make_strategy("LNS"))
        assert len(results) == 1
        assert results[0].heuristic == "LNS"

    def test_lns_infeasible_raises_schedule_error(self):
        from concilium.application.scheduling.selector import ScheduleError, explore_schedules

        dag, pool = self._make_dag_pool()
        sched = MagicMock(feasible=False)
        lns_mock = MagicMock(schedule=MagicMock(return_value=sched))
        oracle_mock = MagicMock()
        with (
            patch("concilium.application.scheduling.lns_scheduler.LnsScheduler", return_value=lns_mock),
            patch("concilium.domain.services.planning.matching_oracle.MatchingOracle", return_value=oracle_mock),
            pytest.raises(ScheduleError),
        ):
            explore_schedules([], dag, pool, deadline_weeks=10, strategy=self._make_strategy("LNS"))

    def test_lns_exception_raises_schedule_error(self):
        from concilium.application.scheduling.selector import ScheduleError, explore_schedules

        dag, pool = self._make_dag_pool()
        with (
            patch("concilium.application.scheduling.lns_scheduler.LnsScheduler", side_effect=RuntimeError("lns fail")),
            patch("concilium.domain.services.planning.matching_oracle.MatchingOracle", return_value=MagicMock()),
            pytest.raises(ScheduleError),
        ):
            explore_schedules([], dag, pool, deadline_weeks=10, strategy=self._make_strategy("LNS"))

    def test_compare_lns_infeasible_appends_error_result(self):
        from concilium.application.scheduling.selector import compare_all_algorithms

        dag, pool = self._make_dag_pool()
        sched = MagicMock(feasible=False, makespan=0)
        lns_mock = MagicMock(schedule=MagicMock(return_value=sched))
        with (
            patch("concilium.application.scheduling.lns_scheduler.LnsScheduler", return_value=lns_mock),
            patch("concilium.domain.services.planning.matching_oracle.MatchingOracle", return_value=MagicMock()),
        ):
            results = compare_all_algorithms([], dag, pool, deadline_weeks=10, algorithms=["LNS"])
        assert len(results) == 1
        assert results[0].error == "infeasible"

    def test_compare_cpsat_infeasible_appends_error_result(self):
        from concilium.application.scheduling.selector import compare_all_algorithms

        dag, pool = self._make_dag_pool()
        sched = MagicMock(feasible=False, makespan=0)
        cpsat_mock = MagicMock(schedule=MagicMock(return_value=sched))
        with patch("concilium.application.scheduling.cpsat_scheduler.CpSatScheduler", return_value=cpsat_mock):
            results = compare_all_algorithms([], dag, pool, deadline_weeks=10, algorithms=["CP-SAT"])
        assert len(results) == 1
        assert results[0].error == "infeasible"

    def test_compare_cpsat_unexpected_exception_appends_error_result(self):
        """Erro inesperado (não infeasible) do CP-SAT não derruba compare_all_algorithms."""
        from concilium.application.scheduling.selector import compare_all_algorithms

        dag, pool = self._make_dag_pool()
        cpsat_mock = MagicMock(schedule=MagicMock(side_effect=RuntimeError("solver crashed")))
        with patch("concilium.application.scheduling.cpsat_scheduler.CpSatScheduler", return_value=cpsat_mock):
            results = compare_all_algorithms([], dag, pool, deadline_weeks=10, algorithms=["CP-SAT"])
        assert len(results) == 1
        assert "solver crashed" in results[0].error

    def test_compare_lns_unexpected_exception_appends_error_result(self):
        """Erro inesperado (não infeasible) do LNS não derruba compare_all_algorithms."""
        from concilium.application.scheduling.selector import compare_all_algorithms

        dag, pool = self._make_dag_pool()
        lns_mock = MagicMock(schedule=MagicMock(side_effect=RuntimeError("lns crashed")))
        with (
            patch("concilium.application.scheduling.lns_scheduler.LnsScheduler", return_value=lns_mock),
            patch("concilium.domain.services.planning.matching_oracle.MatchingOracle", return_value=MagicMock()),
        ):
            results = compare_all_algorithms([], dag, pool, deadline_weeks=10, algorithms=["LNS"])
        assert len(results) == 1
        assert "lns crashed" in results[0].error


class TestSpanEventOtelUnavailable:
    def test_returns_early_when_otel_unavailable(self):
        """_span_event() is a no-op when _OTEL_AVAILABLE is False (SDK not installed)."""
        from concilium.application.scheduling import selector

        with patch.object(selector, "_OTEL_AVAILABLE", False):
            # Should not raise even though trace usage below would otherwise be exercised.
            selector._span_event("some.event", {"k": "v"})

    def test_returns_early_when_trace_is_none(self):
        """_span_event() is a no-op when trace module reference is None."""
        from concilium.application.scheduling import selector

        with patch.object(selector, "trace", None):
            selector._span_event("some.event", {"k": "v"})
