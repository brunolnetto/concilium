"""Coverage boost tests for milp.py and fuel.py.

These tests target the remaining missing lines in:
- concilium/scheduling/milp.py (lines 34-35, 71, 181)
- concilium/clients/fuel.py (lines 181-189, the __main__ block)
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.scheduling.milp import MILPScheduler
from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduleError,
)

# ═══════════════════════════════════════════════════════════════════════════════
# milp.py — missing lines 34-35, 71, 181
# ═══════════════════════════════════════════════════════════════════════════════


class TestMILPMissingLines:
    """Cover the remaining lines in milp.py."""

    def test_milp_no_pulp_raises_import_error(self):
        """schedule() raises ImportError when _HAS_PULP is False (line 71)."""
        import concilium.application.scheduling.milp as milp_mod

        acts = [Activity(activity_id="A", description="A", duration_weeks=1)]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={})

        with patch.object(milp_mod, "_HAS_PULP", False):
            scheduler = MILPScheduler()
            with pytest.raises(ImportError, match="PuLP is required"):
                scheduler.schedule(acts, dag, pool, deadline_weeks=5)

    def test_milp_module_reload_without_pulp_sets_has_pulp_false(self):
        """Covers lines 34-35 (except ImportError: _HAS_PULP = False) by blocking pulp import."""
        import concilium.application.scheduling.milp as milp_mod

        original_pulp = sys.modules.get("pulp")
        # Block pulp so the except ImportError branch executes on reload
        sys.modules["pulp"] = None  # type: ignore[assignment]
        try:
            importlib.reload(milp_mod)
            assert milp_mod._HAS_PULP is False
        finally:
            # Restore pulp module
            if original_pulp is not None:
                sys.modules["pulp"] = original_pulp
            elif "pulp" in sys.modules:
                del sys.modules["pulp"]
            # Reload back to working state
            importlib.reload(milp_mod)
            assert milp_mod._HAS_PULP is True

    def test_milp_resource_infeasible_raises_schedule_error(self):
        """MILP solver returns infeasible when resource constraints are violated (line 181).

        Two activities each needing 5 workers with a pool of 5 and deadline=3
        means they MUST overlap (3 weeks total, each 2 weeks, sequential requires 4)
        but cannot overlap due to resources.
        """
        acts = [
            Activity(
                activity_id="A",
                description="Task A",
                duration_weeks=2,
                required_resources={"workers": 5},
            ),
            Activity(
                activity_id="B",
                description="Task B",
                duration_weeks=2,
                required_resources={"workers": 5},
            ),
        ]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"workers": 5})
        scheduler = MILPScheduler(timeout_seconds=30)
        # Both activities must overlap at some week (deadline=3, each dur=2)
        # but they can't (pool = 5 = max one at a time)
        with pytest.raises(ScheduleError):
            scheduler.schedule(acts, dag, pool, deadline_weeks=3)


# ═══════════════════════════════════════════════════════════════════════════════
# fuel.py — lines 181-189 (__main__ block)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFuelMainBlock:
    """Cover the if __name__ == '__main__' block in fuel.py (lines 181-189)."""

    @staticmethod
    def _make_api_response() -> dict:
        return {
            "data_coleta": "2024-01-15 00:00:00",
            "fonte": "ANP",
            "moeda": "BRL",
            "precos": {
                "gasolina": {
                    "GO": "5.50",
                    "SP": "6.64",
                    "RJ": "6.20",
                },
                "diesel": {
                    "GO": "6.25",
                    "SP": "6.80",
                    "RJ": "6.55",
                },
                "diesel_s10": {
                    "GO": "6.35",
                    "SP": "6.90",
                    "RJ": "6.65",
                },
                "etanol": {
                    "GO": "3.75",
                    "SP": "4.10",
                    "RJ": "4.50",
                },
            },
            "error": None,
        }

    @patch("requests.get")
    def test_fuel_main_block_execution(self, mock_get):
        """Running fuel module as __main__ executes the usage examples (lines 181-189)."""
        import runpy

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = self._make_api_response()
        mock_get.return_value = mock_response

        # This runs the __main__ block, covering lines 181-189
        runpy.run_module("concilium.infrastructure.clients.fuel", run_name="__main__", alter_sys=False)
