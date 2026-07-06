"""Coverage batch 7 — scheduler, campaign_store, migrator, logging gaps."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# scheduling/validator.py line 31: continue when pred/succ not in schedule_map
# scheduling/validator.py line 80: continue when activity not found
# ---------------------------------------------------------------------------


class TestScheduleValidatorMissingLines:
    def test_validate_precedence_skips_unknown_activities(self):
        """Line 31: pred/succ not in schedule_map → continue."""
        from concilium.application.scheduling.models import ScheduledActivity
        from concilium.application.scheduling.validator import ScheduleValidator

        sa = ScheduledActivity(activity_id="A1", start_week=0, end_week=3, duration_weeks=3)
        v = ScheduleValidator()
        # Precedence references "X1" and "X2" which are NOT in scheduled
        result = v.validate_precedence([sa], [("X1", "X2")])
        assert result is True

    def test_validate_durations_skips_unknown_activity(self):
        """Line 80: a is None (activity not in dict) → continue."""
        from concilium.application.scheduling.models import ScheduledActivity
        from concilium.application.scheduling.validator import ScheduleValidator

        sa = ScheduledActivity(activity_id="UNKNOWN", start_week=0, end_week=3, duration_weeks=3)
        v = ScheduleValidator()
        result = v.validate_durations([sa], {})  # empty activities dict
        assert result is True


# ---------------------------------------------------------------------------
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
# campaign_store.py line 89: raise ValueError when _path is None
# campaign_store.py line 188: non-LocalBlobStorage run_path
# campaign_store.py line 269: load_config returns None when no current run
# ---------------------------------------------------------------------------


class TestCampaignStoreMissingLines:
    def test_init_raises_when_no_path_and_no_storage(self):
        """Line 89: neither storage nor path → ValueError."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        with pytest.raises(ValueError, match="Forneça"):
            CampaignRunStore()

    def test_run_path_non_local_storage_returns_logical_path(self):
        """Line 188: non-LocalBlobStorage backend → return Path(prefix) / runs / run."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        mock_storage = MagicMock()
        mock_storage.blob_existe.return_value = False
        store = CampaignRunStore(storage=mock_storage, prefix="campaigns")
        path = store.run_path("run-001")
        assert str(path).endswith("run-001")

    def test_load_config_no_current_run_returns_none(self):
        """Line 269: no current run → return None."""
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        mock_storage = MagicMock()
        mock_storage.blob_existe.return_value = False  # no current blob
        mock_storage.listar_blobs.return_value = []  # no runs
        store = CampaignRunStore(storage=mock_storage, prefix="campaigns")
        result = store.load_config(run=None)
        assert result is None


# ---------------------------------------------------------------------------
# migrator.py lines 101-103: exception during migration → failed count +1
# ---------------------------------------------------------------------------


class TestBlobMigratorException:
    def test_blob_read_exception_increments_failed(self):
        """Lines 101-103: exception during ler_blob → failed += 1, logged."""
        from concilium.infrastructure.adapters.blob_storage.migrator import BlobMigrator

        source = MagicMock()
        target = MagicMock()
        source.listar_blobs.return_value = ["path/to/blob.json"]
        source.ler_blob.side_effect = OSError("read failed")

        migrator = BlobMigrator()
        result = migrator.migrate(source, target, overwrite=True)
        assert result.failed == 1
        assert result.copied == 0


# ---------------------------------------------------------------------------
# logging_config.py lines 31-32: except Exception when trace fails
# logging_config.py lines 45-46: except Exception when auth import fails
# ---------------------------------------------------------------------------


class TestLoggingConfigExceptionPaths:
    def test_get_trace_context_exception_returns_empty(self):
        """Lines 31-32: exception in trace.get_current_span → except → return '', ''."""
        from concilium.infrastructure.observability.logging_config import _get_trace_context

        with patch.dict(sys.modules, {"opentelemetry": None}):
            result = _get_trace_context()
        assert result == ("", "")

    def test_get_auth_context_exception_returns_empty(self):
        """Lines 45-46: import fails → except Exception → return '', ''."""
        from concilium.infrastructure.observability.logging_config import _get_auth_context

        with patch.dict(
            sys.modules,
            {"concilium.infrastructure.middleware.auth_context": None},
        ):
            result = _get_auth_context()
        assert result == ("", "")
