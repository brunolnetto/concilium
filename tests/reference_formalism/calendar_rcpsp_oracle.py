"""Independent small-horizon Q-FS schedule feasibility oracle (P12-B).

Never imports Concilium's scheduler. Uses exact Fraction arithmetic and bounded
exhaustive enumeration. It verifies the semantics from
CALENDARIO_E_LIBERACAO_FISICA.md, not production RCPSP equivalence.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from fractions import Fraction


@dataclass(frozen=True)
class Release:
    predecessor: str
    theta: Fraction
    lag: int = 0


@dataclass(frozen=True)
class Task:
    name: str
    scope: Fraction
    nominal_weekly_capacity: Fraction
    demand: tuple[tuple[str, int], ...] = ()
    predecessors: tuple[Release, ...] = ()


@dataclass(frozen=True)
class Placement:
    start: int
    end: int
    output: tuple[tuple[int, Fraction], ...]


@dataclass(frozen=True)
class SmallScenario:
    tasks: tuple[Task, ...]
    practicability: tuple[Fraction, ...]
    calendar: tuple[Fraction, ...]
    pool: Mapping[str, tuple[int, ...]]
    journey: Fraction = Fraction(1)


def _validate(scenario: SmallScenario) -> None:
    horizon = len(scenario.practicability)
    if not 1 <= horizon <= 12 or len(scenario.calendar) != horizon:
        raise ValueError("bounded calendar must have aligned weeks (1..12)")
    if not 1 <= len(scenario.tasks) <= 7:
        raise ValueError("bounded oracle accepts 1..7 tasks")
    if not isinstance(scenario.journey, Fraction) or not 0 <= scenario.journey <= 1:
        raise ValueError("journey availability must be an exact rational in [0,1]")
    for group in (scenario.practicability, scenario.calendar):
        if any(not isinstance(v, Fraction) or not 0 <= v <= 1 for v in group):
            raise ValueError("calendar factors must be exact rational values in [0,1]")
    if len(set(t.name for t in scenario.tasks)) != len(scenario.tasks):
        raise ValueError("task names must be unique")
    names = {t.name for t in scenario.tasks}
    for key, weekly in scenario.pool.items():
        if not key or len(weekly) != horizon or any(
            not isinstance(x, int) or x < 0 for x in weekly
        ):
            raise ValueError("pool must declare nonnegative integer counts for every week")
    for task in scenario.tasks:
        if not task.name or not isinstance(task.scope, Fraction) or task.scope <= 0:
            raise ValueError("task scope must be positive exact rational")
        if (not isinstance(task.nominal_weekly_capacity, Fraction)
                or task.nominal_weekly_capacity <= 0):
            raise ValueError("one installed weekly capacity must be positive")
        types: set[str] = set()
        for resource, count in task.demand:
            if resource not in scenario.pool or resource in types or count < 0:
                raise ValueError("invalid, duplicated or undeclared physical resource demand")
            types.add(resource)
        for edge in task.predecessors:
            if (edge.predecessor not in names or edge.predecessor == task.name
                    or not isinstance(edge.theta, Fraction)
                    or not 0 < edge.theta <= 1
                    or not isinstance(edge.lag, int) or edge.lag < 0):
                raise ValueError("invalid Q-FS release contract")


def _order(tasks: tuple[Task, ...]) -> tuple[Task, ...]:
    by_name = {task.name: task for task in tasks}
    remaining = set(by_name)
    sequence = []
    visited: set[str] = set()
    while remaining:
        options = [
            by_name[name] for name in sorted(remaining)
            if all(edge.predecessor in visited for edge in by_name[name].predecessors)
        ]
        if not options:
            raise ValueError("cyclic physical precedence graph")
        selected = options[0]
        sequence.append(selected)
        visited.add(selected.name)
        remaining.remove(selected.name)
    return tuple(sequence)


def _release(placement: Placement, scope: Fraction, theta: Fraction, lag: int) -> int:
    cumulative = Fraction(0)
    for week, output in placement.output:
        cumulative += output
        if cumulative >= scope * theta:
            return week + 1 + lag
    raise ValueError("previous task does not reach declared physical threshold")


def _simulate(task: Task, start: int, scenario: SmallScenario) -> Placement | None:
    horizon = len(scenario.practicability)
    remaining = task.scope
    output = []
    for week in range(start, horizon + 1):
        physical = (
            task.nominal_weekly_capacity
            * scenario.practicability[week - 1]
            * scenario.calendar[week - 1]
            * scenario.journey
        )
        delivered = min(remaining, physical)
        output.append((week, delivered))
        remaining -= delivered
        if remaining == 0:
            return Placement(start=start, end=week, output=tuple(output))
    return None


def _has_pool_capacity(
    candidate: Placement,
    task: Task,
    schedule: Mapping[str, Placement],
    by_name: Mapping[str, Task],
    scenario: SmallScenario,
) -> bool:
    for resource, amount in task.demand:
        for week in range(candidate.start, candidate.end + 1):
            used = amount
            for name, placed in schedule.items():
                if placed.start <= week <= placed.end:
                    used += dict(by_name[name].demand).get(resource, 0)
            if used > scenario.pool[resource][week - 1]:
                return False
    return True


def feasible_schedule(scenario: SmallScenario) -> dict[str, Placement] | None:
    """Return first verified feasible solution, or None after exhaustive search.

    Finite small-horizon exact oracle, not a scalable scheduler, optimality
    claim or certificated operational GO. Search exhausts all eligible starts
    with physical releases and rechecks shared resource capacities.
    """
    _validate(scenario)
    ordered = _order(scenario.tasks)
    by_name = {t.name: t for t in ordered}
    horizon = len(scenario.practicability)

    def visit(index: int, scheduled: dict[str, Placement]) -> dict[str, Placement] | None:
        if index == len(ordered):
            return dict(scheduled)
        task = ordered[index]
        earliest = 1
        for edge in task.predecessors:
            predecessor = by_name[edge.predecessor]
            earliest = max(
                earliest,
                _release(
                    scheduled[edge.predecessor], predecessor.scope, edge.theta, edge.lag
                ),
            )
        for start in range(earliest, horizon + 1):
            candidate = _simulate(task, start, scenario)
            if candidate is None or not _has_pool_capacity(
                candidate, task, scheduled, by_name, scenario
            ):
                continue
            scheduled[task.name] = candidate
            result = visit(index + 1, scheduled)
            if result is not None:
                return result
            del scheduled[task.name]
        return None

    return visit(0, {})
