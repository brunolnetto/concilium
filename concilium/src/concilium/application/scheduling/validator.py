"""ADR-004: Schedule Validator — hard constraint checks (VAL-SCHED-01 to 05)."""

from __future__ import annotations

from .models import Activity, ResourcePool, ScheduledActivity, ScheduleOutput


class ScheduleValidator:
    """Validates a ScheduleOutput against hard constraints."""

    def validate_all_scheduled(
        self,
        scheduled: list[ScheduledActivity],
        total_activities: int,
    ) -> bool:
        """VAL-SCHED-01: Every activity must appear in the schedule."""
        assert len(scheduled) == total_activities, (
            f"VAL-SCHED-01: Expected {total_activities} activities, got {len(scheduled)}"
        )
        return True

    def validate_precedence(
        self,
        scheduled: list[ScheduledActivity],
        precedence: list[tuple[str, str]],
    ) -> bool:
        """VAL-SCHED-02: Precedence constraints must be respected (pred.end <= succ.start)."""
        schedule_map = {s.activity_id: s for s in scheduled}
        for pred_id, succ_id in precedence:
            if pred_id not in schedule_map or succ_id not in schedule_map:
                continue
            pred = schedule_map[pred_id]
            succ = schedule_map[succ_id]
            assert pred.end_week <= succ.start_week, (
                f"VAL-SCHED-02: Precedence violated: '{pred_id}' ends at week "
                f"{pred.end_week} but '{succ_id}' starts at week {succ.start_week}"
            )
        return True

    def validate_deadline(
        self,
        scheduled: list[ScheduledActivity],
        deadline_week: int,
    ) -> bool:
        """VAL-SCHED-03: All activities must finish by deadline_week."""
        for act in scheduled:
            # end_week is exclusive: last occupied week = end_week - 1
            # The last occupied week must be STRICTLY less than deadline_week
            assert act.end_week - 1 < deadline_week, (
                f"VAL-SCHED-03: Activity '{act.activity_id}' ends at week "
                f"{act.end_week - 1} but deadline is week {deadline_week} (must finish before)"
            )
        return True

    def validate_resource_capacity(
        self,
        schedule: ScheduleOutput,
        pool: ResourcePool,
    ) -> bool:
        """VAL-SCHED-04: Resource usage must not exceed pool capacity in any week."""
        makespan = schedule.makespan
        for week in range(1, makespan + 2):
            usage = schedule.get_weekly_resource_usage(week)
            for res, used in usage.items():
                capacity = pool.resources.get(res, 0)
                assert used <= capacity, (
                    f"VAL-SCHED-04: Week {week}: resource '{res}' usage {used} exceeds capacity {capacity}"
                )
        return True

    def validate_durations(
        self,
        scheduled: list[ScheduledActivity],
        activities: dict[str, Activity],
    ) -> bool:
        """VAL-SCHED-05: Scheduled duration must match declared duration."""
        for s in scheduled:
            a = activities.get(s.activity_id)
            if a is None:
                continue
            actual_duration = s.end_week - s.start_week
            assert actual_duration == a.duration_weeks, (
                f"VAL-SCHED-05: Activity '{s.activity_id}' should be "
                f"{a.duration_weeks}w but is scheduled for {actual_duration}w"
            )
        return True

    def validate_schedule(
        self,
        schedule: ScheduleOutput,
        activities: dict[str, Activity],
        pool: ResourcePool,
        precedence: list[tuple[str, str]],
        deadline_week: int,
    ) -> bool:
        """Run all five hard-constraint validations."""
        self.validate_all_scheduled(schedule.scheduled_activities, len(activities))
        self.validate_precedence(schedule.scheduled_activities, precedence)
        self.validate_deadline(schedule.scheduled_activities, deadline_week)
        self.validate_resource_capacity(schedule, pool)
        self.validate_durations(schedule.scheduled_activities, activities)
        return True
