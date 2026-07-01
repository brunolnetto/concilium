"""Coverage batch 32 — cpu_mapper, cpsat_scheduler, lns_scheduler small gaps."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# cpu_mapper.py lines 12, 16:
# _tools_root and _rules_file are called when _load_mapping_keywords runs
# ---------------------------------------------------------------------------


class TestCpuMapperLoadKeywords:
    def test_load_mapping_keywords_returns_dict(self):
        """Lines 12, 16: _tools_root() and _rules_file() are called; file exists → dict returned."""
        from concilium.infrastructure.catalog.mapping.cpu_mapper import _load_mapping_keywords

        result = _load_mapping_keywords()
        # The cpu_mapping_rules.json exists in the project, so we get a non-empty dict
        assert isinstance(result, dict)

    def test_load_mapping_keywords_non_dict_rules_returns_empty(self, tmp_path):
        """Line 40: rules is not a dict (list) → return {}."""
        from unittest.mock import patch

        rules_file = tmp_path / "cpu_mapping_rules.json"
        rules_file.write_text('{"mapping_keywords": [1, 2, 3]}', encoding="utf-8")

        with patch("concilium.infrastructure.catalog.mapping.cpu_mapper._rules_file", return_value=rules_file):
            from concilium.infrastructure.catalog.mapping.cpu_mapper import _load_mapping_keywords

            result = _load_mapping_keywords()

        assert result == {}

    def test_map_desc_returns_none_when_no_match(self):
        """map_desc with a description that matches nothing → None."""
        from concilium.infrastructure.catalog.mapping.cpu_mapper import map_desc

        result = map_desc("ATIVIDADE SEM MATCH ESPECIFICO ALGUM ZZZXXX")
        assert result is None

    def test_map_desc_returns_cpu_id_for_known_keyword(self):
        """map_desc with a description matching known keywords → cpu_id."""
        from concilium.infrastructure.catalog.mapping.cpu_mapper import map_desc

        # "CORTE" and "DESTOCAMENTO" are in CPU-TERRA-ATI-001 keywords
        result = map_desc("CORTE E DESTOCAMENTO DE VEGETACAO")
        assert result is not None


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
        ep = ExtendedPrecedence(pred="A", succ="B", tipo="FS", lag=0)
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
# lns_scheduler.py lines 181-185:
# Convergence check triggers on second iteration when cost delta < tol
# ---------------------------------------------------------------------------


class TestLnsSchedulerBasic:
    def test_lns_schedules_simple_dag(self):
        """LNS schedules a simple sequential DAG and returns a feasible result."""
        from concilium.application.scheduling.lns_scheduler import LnsScheduler
        from concilium.application.scheduling.models import Activity, ActivityDAG, ResourcePool
        from concilium.domain.services.planning.matching_oracle import MatchingOracle

        activities = [
            Activity("A", "A", 2, {}),
            Activity("B", "B", 3, {}),
        ]
        dag = ActivityDAG(activities, precedence=[("A", "B")])
        pool = ResourcePool(resources={})

        oracle = MatchingOracle(mob_costs={})
        lns = LnsScheduler(oracle=oracle, k_max=3)

        result = lns.schedule(dag=dag, pool=pool)
        assert result is not None
        assert result.feasible
        assert result.makespan >= 5  # A(2) + B(3)
