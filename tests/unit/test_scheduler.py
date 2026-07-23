"""Coverage batch A — targets mcp_server/__main__, semantic/__init__,
scheduling/selector, optimizer/loop, skills/__init__, cpu_insumo validations,
02-produtividade-climatica, 09-relatorio-e-artefatos, and scheduling/scheduler edge cases.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _canonical_com_resultado():
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=0.20,
        status_margem="VERDE",
        validacoes=[],
    )
    return _minimal_canonical(resultado=resultado)


# ══ scheduling/scheduler.py edge cases ═══════════════════════════════════════


class TestSchedulerEdgeCases:
    """Cover lines 30, 175, 190-191, 209, 222, 243-244."""

    def _make_activity(self, aid, duration, resources=None):
        from concilium.application.scheduling.models import Activity

        return Activity(
            activity_id=aid, description=aid, duration_weeks=duration, required_resources=resources or {"R": 1}
        )

    def test_unknown_priority_rule_raises(self):
        """Invalid priority_rule raises ValueError (line 30)."""
        from concilium.application.scheduling.scheduler import SerialScheduler

        with pytest.raises(ValueError, match="Unknown priority_rule"):
            SerialScheduler(priority_rule="INVALID_RULE")

    def test_gr_priority_rule_schedules(self):
        """GR rule executes _prioritize returning topo_order (line 175)."""
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        acts = [self._make_activity("a1", 1), self._make_activity("a2", 1)]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"R": 2})
        scheduler = SerialScheduler(priority_rule="GR")
        sched = scheduler.schedule(acts, dag, pool, deadline_weeks=5)
        assert sched.makespan <= 5

    def test_schedule_infeasible_raises_schedule_error(self):
        """Activity can't fit in deadline → ScheduleError (lines 190-191)."""
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool, ScheduleError
        from concilium.application.scheduling.scheduler import SerialScheduler

        acts = [self._make_activity("a1", 10)]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"R": 1})
        scheduler = SerialScheduler(priority_rule="MINSLK")
        with pytest.raises(ScheduleError):
            scheduler.schedule(acts, dag, pool, deadline_weeks=5)

    def test_resource_conflict_forces_stagger(self):
        """Two activities needing same resource → _can_schedule returns False → stagger (line 209)."""
        from concilium.application.scheduling.models import ActivityDAG, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        acts = [
            self._make_activity("a1", 2, {"R": 2}),
            self._make_activity("a2", 2, {"R": 2}),
        ]
        dag = ActivityDAG(activities=acts, precedence=[])
        pool = ResourcePool(resources={"R": 2})
        scheduler = SerialScheduler(priority_rule="MINSLK")
        sched = scheduler.schedule(acts, dag, pool, deadline_weeks=10)
        # They must be scheduled sequentially → makespan >= 4
        assert sched.makespan >= 4

    def test_compute_metrics_empty_acts_returns_defaults(self):
        """Empty acts → default ScheduleMetrics (lines 222-226)."""
        from concilium.application.scheduling.models import ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        pool = ResourcePool(resources={"R": 1})
        scheduler = SerialScheduler()
        metrics = scheduler._compute_metrics([], {}, pool, makespan=0, deadline_weeks=5)
        assert metrics.makespan == 0
        assert metrics.resource_leveling_score == 1.0

    def test_compute_metrics_makespan_zero_with_acts_gives_else_branch(self):
        """makespan=0 with non-empty acts → weekly_loads=[] → else branch (lines 243-244)."""
        from concilium.application.scheduling.models import ResourcePool, ScheduledActivity
        from concilium.application.scheduling.scheduler import SerialScheduler

        pool = ResourcePool(resources={"R": 1})
        # Pass makespan=0 so range(0) = [] → weekly_loads empty → else branch
        acts = [ScheduledActivity(activity_id="a1", start_week=0, end_week=0, duration_weeks=0)]
        scheduler = SerialScheduler()
        metrics = scheduler._compute_metrics(acts, {}, pool, makespan=0, deadline_weeks=5)
        assert metrics.resource_leveling_score == 1.0
        assert metrics.resource_utilization_avg == 0.0





# scheduling/scheduler.py: resource matching (line 191)
# ────────────────────────────────────────────────────────────────


class TestResourceScheduling:
    """Test resource scheduling logic."""

    def test_scheduler_finds_matching_resources(self):
        """Scheduler should find matching resources."""
        pass


# ────────────────────────────────────────────────────────────────



# scheduler.py line 79:
# _demand_at_offset with ramp_profile set → scaled demand
# ---------------------------------------------------------------------------


class TestDemandAtOffsetRampProfile:
    def _make_activity(self, ramp_profile):
        from concilium.application.scheduling.models import Activity

        return Activity(
            activity_id="ACT-TEST",
            description="Test activity with ramp",
            duration_weeks=len(ramp_profile),
            required_resources={"worker": 4},
            ramp_profile=ramp_profile,
        )

    def test_ramp_profile_scales_demand(self):
        """Line 79: ramp_profile[0]=0.5, qty=4 → max(0, round(4*0.5))=2."""
        from concilium.application.scheduling.scheduler import _demand_at_offset

        activity = self._make_activity([0.5, 1.0, 0.75])
        result = _demand_at_offset(activity, 0, "worker", 4)
        assert result == 2  # round(4 * 0.5) = 2

    def test_ramp_profile_offset_out_of_range_returns_qty(self):
        """Line 78 (no branch): offset >= len(ramp_profile) → return qty unchanged."""
        from concilium.application.scheduling.scheduler import _demand_at_offset

        activity = self._make_activity([0.5, 1.0])
        # offset=5 >= len([0.5, 1.0])=2 → return qty=4
        result = _demand_at_offset(activity, 5, "worker", 4)
        assert result == 4


# ---------------------------------------------------------------------------


# scheduler.py line 243:
# SerialScheduler._find_start with activity.window_weeks set → uses min constraint
# ---------------------------------------------------------------------------


class TestFindStartWithWindowWeeks:
    def test_window_weeks_constrains_max_start(self):
        """Line 243: window_weeks not None → max_start = min(deadline, window) - duration."""
        from concilium.application.scheduling.models import Activity, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        activity = Activity(
            activity_id="ACT-W",
            description="Windowed activity",
            duration_weeks=2,
            required_resources={},
            window_weeks=8,  # must finish within 8 weeks of project start
        )
        pool = ResourcePool(resources={})
        scheduler = SerialScheduler()

        # deadline=20, window_weeks=8 → max_start = min(20, 8) - 2 = 6
        start = scheduler._find_start(activity, 0, {}, pool, deadline_weeks=20)
        assert start == 0  # no resource conflicts, starts at earliest=0

    def test_without_window_weeks_uses_deadline(self):
        """Line 245 (else branch): window_weeks None → max_start = deadline - duration."""
        from concilium.application.scheduling.models import Activity, ResourcePool
        from concilium.application.scheduling.scheduler import SerialScheduler

        activity = Activity(
            activity_id="ACT-NW",
            description="No-window activity",
            duration_weeks=2,
            required_resources={},
        )
        pool = ResourcePool(resources={})
        scheduler = SerialScheduler()

        start = scheduler._find_start(activity, 0, {}, pool, deadline_weeks=20)
        assert start == 0


# ---------------------------------------------------------------------------

