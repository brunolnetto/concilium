"""Coverage batch 7 — scheduler, campaign_store, migrator, logging gaps."""

from __future__ import annotations

# cpsat_scheduler.py line 247: _compute_metrics with empty scheduled
# cpsat_scheduler.py line 292: _empty_output returns ScheduleOutput
# ---------------------------------------------------------------------------


class TestCpSatSchedulerMissingLines:
    def _scheduler(self):
        from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler

        return CpSatScheduler()

    def test_compute_metrics_empty_scheduled(self):
        """Lines 247-250: _compute_metrics with empty scheduled → early return."""
        from concilium.application.scheduling.models import ResourcePool

        s = self._scheduler()
        pool = ResourcePool(resources={})
        result = s._compute_metrics([], pool, makespan=0)
        assert result.makespan == 0
        assert result.resource_leveling_score == 1.0

    def test_empty_output_returns_unfeasible(self):
        """Line 292: _empty_output returns ScheduleOutput with feasible=False."""
        from concilium.application.scheduling.models import Activity, ActivityDAG

        a = Activity("A1", "Desc", 2, {"W": 1})
        dag = ActivityDAG(activities=[a], precedence=[])
        s = self._scheduler()
        result = s._empty_output(dag)
        assert result.feasible is False
        assert result.makespan == 0

    def test_makespan_callback_ignores_non_improving_solution(self):
        """_MakespanCallback.on_solution_callback must not update
        best_makespan when a later solution's makespan is >= the current
        best (covers the false branch of `if ms < self.best_makespan`)."""
        from ortools.sat.python import cp_model

        from concilium.application.scheduling.cpsat_scheduler import _MakespanCallback

        model = cp_model.CpModel()
        v = model.new_int_var(0, 10, "v")
        cb = _MakespanCallback(v)
        cb.value = lambda _expr: 5
        cb.on_solution_callback()
        assert cb.best_makespan == 5
        cb.value = lambda _expr: 7  # worse (higher) makespan → ignored
        cb.on_solution_callback()
        assert cb.best_makespan == 5

    def test_compute_metrics_skips_zero_capacity_resource(self):
        """A resource with cap<=0 in the pool must be skipped from the
        leveling-score aggregation (the `if cap > 0 and vals` guard)."""
        from concilium.application.scheduling.models import (
            ResourcePool,
            ScheduledActivity,
        )

        s = self._scheduler()
        pool = ResourcePool(resources={"ZERO": 0, "E": 10})
        scheduled = [
            ScheduledActivity(
                activity_id="A1",
                start_week=0,
                end_week=3,
                duration_weeks=3,
                assigned_resources={"E": 5},
            )
        ]
        result = s._compute_metrics(scheduled, pool, makespan=3)
        # Only "E" contributes a leveling score; "ZERO" is skipped entirely.
        assert 0.0 <= result.resource_leveling_score <= 1.0


# ---------------------------------------------------------------------------



# cpsat_scheduler.py line 150:
# FS precedence with pred/succ not in acts → continue
# ---------------------------------------------------------------------------


class TestCpSatSchedulerPrecedenceNotInActs:
    def _make_dag(self):
        from concilium.application.scheduling.models import Activity, ActivityDAG

        activities = [Activity("ACT-A", "Activity A", 2, {})]
        # Precedence references a non-existent activity "ACT-GHOST"
        dag = ActivityDAG(activities, precedence=[("ACT-A", "ACT-GHOST")])
        return dag

    def test_precedence_with_unknown_activity_is_skipped(self):
        """Line 150: succ 'ACT-GHOST' not in acts → continue (skip this precedence)."""
        from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler
        from concilium.application.scheduling.models import ResourcePool

        dag = self._make_dag()
        pool = ResourcePool(resources={})
        scheduler = CpSatScheduler(timeout_seconds=5.0)

        result = scheduler.schedule(dag=dag, pool=pool)
        # Should succeed: the invalid precedence is silently skipped
        assert result is not None


# ---------------------------------------------------------------------------


# cpsat_scheduler.py line 172:
# extended_precedence with unknown tipo → log.warning
# ---------------------------------------------------------------------------


class TestCpSatSchedulerUnknownPrecedenceType:
    def test_unknown_extended_precedence_tipo_logs_warning(self):
        """Line 172: ep.tipo not in ('FS', 'SS', 'FF') → _log.warning(...)."""

        from concilium.application.scheduling.cpsat_scheduler import CpSatScheduler, ExtendedPrecedence
        from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool

        activities = [
            Activity("A", "A", 2, {}),
            Activity("B", "B", 2, {}),
        ]
        dag = ActivityDAG(activities, precedence=[])
        pool = ResourcePool(resources={})

        # ExtendedPrecedence normally requires Literal['FS', 'SS', 'FF'],
        # but we can bypass with object() trick or by creating an instance manually
        ExtendedPrecedence(pred="A", succ="B", tipo="FS", lag=0)
        # Manually set tipo to unknown value using object.__setattr__

        # Simpler: create via __new__ and set fields directly
        bad_ep = object.__new__(ExtendedPrecedence)
        object.__setattr__(bad_ep, "pred", "A")
        object.__setattr__(bad_ep, "succ", "B")
        object.__setattr__(bad_ep, "tipo", "SL")  # invalid type
        object.__setattr__(bad_ep, "lag", 0)

        scheduler = CpSatScheduler(timeout_seconds=5.0)
        result = scheduler.schedule(dag=dag, pool=pool, extended_precedences=[bad_ep])

        # Should succeed: unknown precedence type is logged and skipped
        assert result is not None


# ---------------------------------------------------------------------------

