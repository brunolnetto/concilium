"""
ADR-004: Activity Scheduling Algorithm Selection Strategy — TDD Test Suite

Tests for:
- SerialScheduler with multiple heuristics (MINSLK, LPT, MAXRES, ES, GR)
- ScheduleMetrics and quality scoring
- select_scheduling_algorithm() decision logic
- explore_schedules() multi-heuristic exploration
- ScheduleValidator for hard constraints (VAL-SCHED-01 to 05)
- ScheduleOutput model and ranking
"""

import pytest

from concilium.application.scheduling.models import (
    Activity,
    ActivityDAG,
    ResourcePool,
    ScheduledActivity,
    ScheduleError,
    ScheduleMetrics,
    ScheduleOutput,
)
from concilium.application.scheduling.scheduler import SerialScheduler
from concilium.application.scheduling.selector import explore_schedules, select_scheduling_algorithm
from concilium.application.scheduling.validator import ScheduleValidator


class TestActivityDAGAndModels:
    """Test basic activity and DAG models."""

    def test_activity_creation(self):
        """Test Activity model creation and validation."""
        act = Activity(
            activity_id="ACT-001",
            description="Escavação",
            duration_weeks=2,
            required_resources={"ESCAVADEIRA": 1},
        )
        assert act.activity_id == "ACT-001"
        assert act.duration_weeks == 2
        assert act.required_resources["ESCAVADEIRA"] == 1

    def test_activity_dag_creation(self):
        """Test DAG creation with activities and precedence."""
        acts = [
            Activity("A", "Escavação", 2, {"ESCAVADEIRA": 1}),
            Activity("B", "Carga", 1, {"CAMINHAO": 2}),
            Activity("C", "Nivelamento", 1, {"MOTONIVELADORA": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B"), ("B", "C")])

        assert len(dag.activities) == 3
        assert ("A", "B") in dag.precedence
        assert ("B", "C") in dag.precedence
        assert dag.get_activity("A").duration_weeks == 2

    def test_resource_pool_creation(self):
        """Test resource pool with capacity constraints."""
        pool = ResourcePool(
            resources={
                "ESCAVADEIRA": 2,
                "CAMINHAO": 5,
                "MOTONIVELADORA": 1,
            }
        )
        assert pool.resources["ESCAVADEIRA"] == 2
        assert pool.resources["CAMINHAO"] == 5

    def test_scheduled_activity_creation(self):
        """Test ScheduledActivity with start/end weeks."""
        scheduled = ScheduledActivity(
            activity_id="ACT-001",
            start_week=1,
            end_week=3,
            duration_weeks=2,
            assigned_resources={"ESCAVADEIRA": 1},
        )
        assert scheduled.start_week == 1
        assert scheduled.end_week == 3


class TestScheduleMetrics:
    """Test ScheduleMetrics calculation."""

    def test_metrics_creation(self):
        """Test ScheduleMetrics model creation."""
        metrics = ScheduleMetrics(
            makespan=12,
            resource_leveling_score=0.85,
            idle_time=2,
            activity_fragmentation=0,
            critical_path_slack_min=1.5,
            resource_utilization_avg=0.78,
        )
        assert metrics.makespan == 12
        assert metrics.resource_leveling_score == 0.85

    def test_quality_score_calculation(self):
        """Test composite quality score calculation."""
        metrics = ScheduleMetrics(
            makespan=12,
            resource_leveling_score=0.85,
            idle_time=1,
            activity_fragmentation=0,
            critical_path_slack_min=2.0,
            resource_utilization_avg=0.82,
        )

        # Quality score should be between 0 and 1
        score = metrics.quality_score(
            weight_makespan=0.5,
            weight_leveling=0.2,
            weight_idle=0.15,
            weight_utilization=0.15,
            deadline_weeks=14,
        )
        assert 0 <= score <= 1
        assert score > 0.5  # Should be decent since metrics are good

    def test_quality_score_with_bad_metrics(self):
        """Test quality score with poor metrics."""
        metrics = ScheduleMetrics(
            makespan=24,  # Very long
            resource_leveling_score=0.2,  # Very uneven
            idle_time=8,  # Lots of gaps
            activity_fragmentation=12,
            critical_path_slack_min=0.0,  # No slack
            resource_utilization_avg=0.3,
        )

        score = metrics.quality_score(
            deadline_weeks=20,
        )
        assert 0 <= score <= 1
        assert score < 0.5  # Should be poor


class TestSerialScheduler:
    """Test SerialScheduler with different heuristics."""

    @pytest.fixture
    def simple_dag(self):
        """Create a simple 3-activity DAG for testing."""
        acts = [
            Activity("A", "Escavação", 2, {"ESCAVADEIRA": 1}),
            Activity("B", "Carga", 1, {"CAMINHAO": 2}),
            Activity("C", "Nivelamento", 1, {"MOTONIVELADORA": 1}),
        ]
        return ActivityDAG(activities=acts, precedence=[("A", "B"), ("B", "C")])

    @pytest.fixture
    def resource_pool(self):
        """Create resource pool."""
        return ResourcePool(
            resources={
                "ESCAVADEIRA": 1,
                "CAMINHAO": 2,
                "MOTONIVELADORA": 1,
            }
        )

    def test_scheduler_creation_minslk(self, simple_dag, resource_pool):
        """Test SerialScheduler creation with MINSLK heuristic."""
        scheduler = SerialScheduler(priority_rule="MINSLK")
        assert scheduler.priority_rule == "MINSLK"

    def test_scheduler_minslk_basic(self, simple_dag, resource_pool):
        """Test MINSLK scheduling of simple DAG."""
        scheduler = SerialScheduler(priority_rule="MINSLK")

        schedule = scheduler.schedule(
            activities=simple_dag.activities,
            dag=simple_dag,
            pool=resource_pool,
            deadline_weeks=10,
        )

        # All activities should be scheduled
        assert len(schedule.scheduled_activities) == 3

        # Schedule should respect deadline
        max_end = max(a.end_week for a in schedule.scheduled_activities)
        assert max_end <= 10

        # Precedence should be respected
        act_a = next(a for a in schedule.scheduled_activities if a.activity_id == "A")
        act_b = next(a for a in schedule.scheduled_activities if a.activity_id == "B")
        assert act_a.end_week <= act_b.start_week

    def test_scheduler_diamond_dag_waits_for_all_predecessors(self):
        """C depende de A e B (diamante): quando A termina, in_degree[C] fica 1
        (não 0), exercitando o ramo em que a atividade NÃO entra na ready list
        imediatamente após decrementar in_degree de um único predecessor."""
        acts = [
            Activity("A", "Escavação", 1, {"ESCAVADEIRA": 1}),
            Activity("B", "Carga", 2, {"CAMINHAO": 1}),
            Activity("C", "Nivelamento", 1, {"MOTONIVELADORA": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "C"), ("B", "C")])
        pool = ResourcePool(resources={"ESCAVADEIRA": 1, "CAMINHAO": 1, "MOTONIVELADORA": 1})
        scheduler = SerialScheduler(priority_rule="MINSLK")

        schedule = scheduler.schedule(
            activities=acts,
            dag=dag,
            pool=pool,
            deadline_weeks=10,
        )

        assert len(schedule.scheduled_activities) == 3
        act_a = next(a for a in schedule.scheduled_activities if a.activity_id == "A")
        act_b = next(a for a in schedule.scheduled_activities if a.activity_id == "B")
        act_c = next(a for a in schedule.scheduled_activities if a.activity_id == "C")
        assert act_c.start_week >= act_a.end_week
        assert act_c.start_week >= act_b.end_week

    def test_scheduler_lpt_heuristic(self, simple_dag, resource_pool):
        """Test LPT (Longest Processing Time) heuristic."""
        scheduler = SerialScheduler(priority_rule="LPT")

        schedule = scheduler.schedule(
            activities=simple_dag.activities,
            dag=simple_dag,
            pool=resource_pool,
            deadline_weeks=10,
        )

        assert len(schedule.scheduled_activities) == 3

    def test_scheduler_maxres_heuristic(self, simple_dag, resource_pool):
        """Test MAXRES (Max Resource First) heuristic."""
        scheduler = SerialScheduler(priority_rule="MAXRES")

        schedule = scheduler.schedule(
            activities=simple_dag.activities,
            dag=simple_dag,
            pool=resource_pool,
            deadline_weeks=10,
        )

        assert len(schedule.scheduled_activities) == 3

    def test_scheduler_es_heuristic(self, simple_dag, resource_pool):
        """Test ES (Earliest Start) heuristic."""
        scheduler = SerialScheduler(priority_rule="ES")

        schedule = scheduler.schedule(
            activities=simple_dag.activities,
            dag=simple_dag,
            pool=resource_pool,
            deadline_weeks=10,
        )

        assert len(schedule.scheduled_activities) == 3

    def test_scheduler_infeasible_deadline(self, simple_dag, resource_pool):
        """Test scheduler behavior with infeasible deadline."""
        scheduler = SerialScheduler(priority_rule="MINSLK")

        # Deadline is too short: even without constraints, A(2) + B(1) + C(1) = 4 min
        with pytest.raises(ScheduleError):
            scheduler.schedule(
                activities=simple_dag.activities,
                dag=simple_dag,
                pool=resource_pool,
                deadline_weeks=2,
            )

    def test_scheduler_respects_resource_constraints(self, simple_dag, resource_pool):
        """Test that scheduler respects resource availability."""
        # Activity B needs 2 CAMINHAO; pool has exactly 2
        # So B cannot run in parallel with anything else using CAMINHAO

        scheduler = SerialScheduler(priority_rule="MINSLK")
        schedule = scheduler.schedule(
            activities=simple_dag.activities,
            dag=simple_dag,
            pool=resource_pool,
            deadline_weeks=10,
        )

        # Check no week exceeds resource capacity
        for week in range(1, 11):
            usage = schedule.get_weekly_resource_usage(week)
            for res, used in usage.items():
                assert used <= resource_pool.resources[res], (
                    f"Week {week}: {res} usage {used} exceeds capacity {resource_pool.resources[res]}"
                )


class TestScheduleValidator:
    """Test ScheduleValidator with hard constraints."""

    @pytest.fixture
    def valid_schedule(self):
        """Create a valid schedule for testing."""
        scheduled_acts = [
            ScheduledActivity("A", start_week=1, end_week=3, duration_weeks=2, assigned_resources={"ESCAVADEIRA": 1}),
            ScheduledActivity("B", start_week=4, end_week=5, duration_weeks=1, assigned_resources={"CAMINHAO": 2}),
            ScheduledActivity(
                "C", start_week=6, end_week=7, duration_weeks=1, assigned_resources={"MOTONIVELADORA": 1}
            ),
        ]
        return ScheduleOutput(
            scheduled_activities=scheduled_acts,
            makespan=7,
            feasible=True,
            metrics=ScheduleMetrics(
                makespan=7,
                resource_leveling_score=0.8,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=1.0,
                resource_utilization_avg=0.7,
            ),
        )

    def test_validator_creation(self):
        """Test ScheduleValidator creation."""
        validator = ScheduleValidator()
        assert validator is not None

    def test_val_sched_01_all_activities_scheduled(self, valid_schedule):
        """VAL-SCHED-01: All activities must be scheduled."""
        validator = ScheduleValidator()

        # Valid schedule has all activities
        result = validator.validate_all_scheduled(
            valid_schedule.scheduled_activities,
            total_activities=3,
        )
        assert result is True

        # Invalid: missing one activity
        with pytest.raises(AssertionError):
            validator.validate_all_scheduled(
                valid_schedule.scheduled_activities[:2],
                total_activities=3,
            )

    def test_val_sched_02_precedence_respected(self):
        """VAL-SCHED-02: Precedence constraints must be respected."""
        scheduled_acts = [
            ScheduledActivity("A", start_week=1, end_week=3, duration_weeks=2, assigned_resources={}),
            ScheduledActivity("B", start_week=4, end_week=5, duration_weeks=1, assigned_resources={}),
            ScheduledActivity("C", start_week=6, end_week=7, duration_weeks=1, assigned_resources={}),
        ]
        schedule = ScheduleOutput(
            scheduled_activities=scheduled_acts,
            makespan=7,
            feasible=True,
            metrics=ScheduleMetrics(
                makespan=7,
                resource_leveling_score=0.8,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=1.0,
                resource_utilization_avg=0.7,
            ),
        )

        validator = ScheduleValidator()
        precedence = [("A", "B"), ("B", "C")]

        # Valid precedence
        assert validator.validate_precedence(schedule.scheduled_activities, precedence) is True

        # Invalid: B starts before A ends
        bad_acts = [
            ScheduledActivity("A", start_week=1, end_week=3, duration_weeks=2, assigned_resources={}),
            ScheduledActivity("B", start_week=2, end_week=3, duration_weeks=1, assigned_resources={}),
        ]
        with pytest.raises(AssertionError):
            validator.validate_precedence(bad_acts, [("A", "B")])

    def test_val_sched_03_deadline_met(self):
        """VAL-SCHED-03: Schedule must meet deadline."""
        scheduled_acts = [
            ScheduledActivity("A", start_week=1, end_week=5, duration_weeks=4, assigned_resources={}),
        ]
        schedule = ScheduleOutput(
            scheduled_activities=scheduled_acts,
            makespan=5,
            feasible=True,
            metrics=ScheduleMetrics(
                makespan=5,
                resource_leveling_score=1.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=1.0,
            ),
        )

        validator = ScheduleValidator()

        # Deadline is week 10 — should pass
        assert validator.validate_deadline(schedule.scheduled_activities, deadline_week=10) is True

        # Deadline is week 4 — should fail
        with pytest.raises(AssertionError):
            validator.validate_deadline(schedule.scheduled_activities, deadline_week=4)

    def test_val_sched_04_resource_capacity(self):
        """VAL-SCHED-04: Resource capacity must not be exceeded."""
        scheduled_acts = [
            ScheduledActivity("A", start_week=1, end_week=2, duration_weeks=1, assigned_resources={"ESCAVADEIRA": 1}),
            ScheduledActivity("B", start_week=1, end_week=2, duration_weeks=1, assigned_resources={"ESCAVADEIRA": 1}),
        ]
        schedule = ScheduleOutput(
            scheduled_activities=scheduled_acts,
            makespan=2,
            feasible=True,
            metrics=ScheduleMetrics(
                makespan=2,
                resource_leveling_score=0.9,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=1.0,
            ),
        )

        validator = ScheduleValidator()
        pool = ResourcePool(resources={"ESCAVADEIRA": 2})

        # Pool has 2, usage is 2 — OK
        assert validator.validate_resource_capacity(schedule, pool) is True

        # Pool has 1, usage is 2 — FAIL
        pool_small = ResourcePool(resources={"ESCAVADEIRA": 1})
        with pytest.raises(AssertionError):
            validator.validate_resource_capacity(schedule, pool_small)

    def test_val_sched_05_durations_respected(self):
        """VAL-SCHED-05: Activity durations must be respected."""
        scheduled_acts = [
            ScheduledActivity("A", start_week=1, end_week=3, duration_weeks=2, assigned_resources={}),
        ]
        schedule = ScheduleOutput(
            scheduled_activities=scheduled_acts,
            makespan=3,
            feasible=True,
            metrics=ScheduleMetrics(
                makespan=3,
                resource_leveling_score=1.0,
                idle_time=0,
                activity_fragmentation=0,
                critical_path_slack_min=0.0,
                resource_utilization_avg=1.0,
            ),
        )

        validator = ScheduleValidator()
        activities = {"A": Activity("A", "Escav", 2, {})}

        # Duration is 2, scheduled for 3-1 = 2 weeks (1,2) — OK
        assert validator.validate_durations(schedule.scheduled_activities, activities) is True

    def test_full_schedule_validation(self, valid_schedule):
        """Test full validation with all constraints."""
        validator = ScheduleValidator()

        activities = {
            "A": Activity("A", "Escav", 2, {}),
            "B": Activity("B", "Carga", 1, {}),
            "C": Activity("C", "Nivel", 1, {}),
        }
        pool = ResourcePool(resources={"ESCAVADEIRA": 1, "CAMINHAO": 2, "MOTONIVELADORA": 1})
        precedence = [("A", "B"), ("B", "C")]

        # Should pass all validations
        result = validator.validate_schedule(
            schedule=valid_schedule,
            activities=activities,
            pool=pool,
            precedence=precedence,
            deadline_week=10,
        )
        assert result is True


class TestScheduleSelection:
    """Test select_scheduling_algorithm() decision logic (ADR-075 thresholds)."""

    def test_small_uses_cpsat(self):
        """n ≤ 200, any criticality → CP-SAT (ADR-075 Mode A)."""
        strategy = select_scheduling_algorithm(
            num_activities=30,
            num_resource_types=3,
            contract_duration_weeks=20,
            deadline_margin_pct=0.3,
            criticality="high",
        )
        assert strategy.algorithm == "CP-SAT"
        assert strategy.timeout_seconds == 60

    def test_medium_uses_cpsat(self):
        """n ≤ 200, medium criticality → CP-SAT (ADR-075 Mode A)."""
        strategy = select_scheduling_algorithm(
            num_activities=100,
            num_resource_types=4,
            contract_duration_weeks=20,
            deadline_margin_pct=0.2,
            criticality="medium",
        )
        assert strategy.algorithm == "CP-SAT"

    def test_boundary_200_uses_cpsat(self):
        """n = 200 (boundary) → CP-SAT (ADR-075 Mode A)."""
        strategy = select_scheduling_algorithm(
            num_activities=200,
            num_resource_types=5,
            contract_duration_weeks=30,
            deadline_margin_pct=0.1,
            criticality="low",
        )
        assert strategy.algorithm == "CP-SAT"
        assert strategy.leveling_pass is False

    def test_large_uses_lns(self):
        """n > 200 → LNS (ADR-075 Mode B)."""
        strategy = select_scheduling_algorithm(
            num_activities=201,
            num_resource_types=5,
            contract_duration_weeks=30,
            deadline_margin_pct=0.1,
            criticality="low",
        )
        assert strategy.algorithm == "LNS"

    def test_default_medium_uses_cpsat(self):
        """Default for medium-sized problem is CP-SAT."""
        strategy = select_scheduling_algorithm(
            num_activities=75,
            num_resource_types=3,
            contract_duration_weeks=15,
            deadline_margin_pct=0.25,
            criticality="medium",
        )
        assert strategy.algorithm == "CP-SAT"


class TestExploreSchedules:
    """Test explore_schedules() multi-heuristic exploration."""

    @pytest.fixture
    def medium_dag(self):
        """Create a medium-sized DAG (5 activities)."""
        acts = [Activity(f"A{i}", f"Task{i}", 2 if i % 2 == 0 else 1, {f"RES{i}": 1}) for i in range(5)]
        precedence = [(f"A{i}", f"A{i + 1}") for i in range(4)]
        return ActivityDAG(activities=acts, precedence=precedence)

    @pytest.fixture
    def medium_pool(self):
        """Create resource pool for medium DAG."""
        return ResourcePool(resources={f"RES{i}": 1 for i in range(5)})

    def test_explore_returns_top_3(self, medium_dag, medium_pool):
        """explore_schedules() should return top 3 ranked schedules."""
        results = explore_schedules(
            activities=medium_dag.activities,
            dag=medium_dag,
            pool=medium_pool,
            deadline_weeks=20,
            heuristics=["MINSLK", "LPT", "MAXRES", "ES"],
        )

        assert len(results) <= 3
        assert len(results) > 0

    def test_explore_returns_ranked_schedules(self, medium_dag, medium_pool):
        """Results should be ranked by quality score (best first)."""
        results = explore_schedules(
            activities=medium_dag.activities,
            dag=medium_dag,
            pool=medium_pool,
            deadline_weeks=20,
            heuristics=["MINSLK", "LPT", "MAXRES"],
        )

        if len(results) > 1:
            # First should have better or equal makespan than second
            assert results[0].schedule.makespan <= results[1].schedule.makespan

    def test_explore_includes_metrics(self, medium_dag, medium_pool):
        """Each result should include metrics."""
        results = explore_schedules(
            activities=medium_dag.activities,
            dag=medium_dag,
            pool=medium_pool,
            deadline_weeks=20,
            heuristics=["MINSLK", "LPT"],
        )

        for result in results:
            assert result.schedule.metrics is not None
            assert result.schedule.metrics.makespan > 0
            assert 0 <= result.schedule.metrics.resource_leveling_score <= 1


class TestScheduleOutput:
    """Test ScheduleOutput model and ranking."""

    def test_schedule_output_creation(self):
        """Test ScheduleOutput creation with complete data."""
        acts = [
            ScheduledActivity("A", 1, 2, 1, {}),
            ScheduledActivity("B", 3, 4, 1, {}),
        ]
        metrics = ScheduleMetrics(
            makespan=4,
            resource_leveling_score=0.9,
            idle_time=0,
            activity_fragmentation=0,
            critical_path_slack_min=1.0,
            resource_utilization_avg=0.8,
        )

        schedule = ScheduleOutput(
            scheduled_activities=acts,
            makespan=4,
            feasible=True,
            metrics=metrics,
        )

        assert schedule.makespan == 4
        assert len(schedule.scheduled_activities) == 2
        assert schedule.feasible is True


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_end_to_end_small_project(self):
        """End-to-end test: small project → CP-SAT strategy → schedule."""
        acts = [
            Activity("A", "Escav", 1, {"ESCAV": 1}),
            Activity("B", "Carga", 1, {"CAMINHAO": 1}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[("A", "B")])
        pool = ResourcePool(resources={"ESCAV": 1, "CAMINHAO": 1})

        # Select algorithm
        strategy = select_scheduling_algorithm(
            num_activities=2,
            num_resource_types=2,
            contract_duration_weeks=10,
            deadline_margin_pct=0.5,
            criticality="high",
        )
        assert strategy.algorithm == "CP-SAT"

        # Schedule
        scheduler = SerialScheduler(priority_rule="MINSLK")
        schedule = scheduler.schedule(
            activities=acts,
            dag=dag,
            pool=pool,
            deadline_weeks=10,
        )

        # Validate
        validator = ScheduleValidator()
        assert (
            validator.validate_schedule(
                schedule=schedule,
                activities={a.activity_id: a for a in acts},
                pool=pool,
                precedence=[("A", "B")],
                deadline_week=10,
            )
            is True
        )

    def test_no_regression_on_existing_behavior(self):
        """Ensure new implementation doesn't break existing functionality."""
        # This test ensures backward compatibility
        acts = [Activity(f"ACT{i}", f"Task{i}", 1, {}) for i in range(3)]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={})

        scheduler = SerialScheduler(priority_rule="MINSLK")
        schedule = scheduler.schedule(
            activities=acts,
            dag=dag,
            pool=pool,
            deadline_weeks=10,
        )

        assert len(schedule.scheduled_activities) == 3
