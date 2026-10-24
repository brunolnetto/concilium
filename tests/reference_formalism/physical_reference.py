"""P22-B independent, bounded physical/calendar/scheduling reference evaluator.

No production imports. Exact Fraction max-flow, fixed-horizon ramp enumeration,
end-of-week Q-FS release and exhaustive small RCPSP schedule search.
This is not a runtime, cost, P16 pool or PROJECT_GO certificate.
"""
from __future__ import annotations

from collections import deque
from fractions import Fraction as F
from itertools import product
from typing import Any

from tests.reference_formalism.protocol import (
    ReferenceContractError,
    _finite_decimal,
    decimal_input,
)

VERSION = "formalism-physical/1"
LIMIT_ACTIVITIES = 5
LIMIT_WEEKS = 10
LIMIT_STATES = 50000


def _keys(obj: Any, required: set[str], label: str) -> dict:
    if not isinstance(obj, dict) or set(obj) != required:
        raise ReferenceContractError(f"{label}: missing or unknown keys")
    return obj


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ReferenceContractError(f"{label}: integer >= {minimum} required")
    return value


def _rate(value: Any, label: str, *, positive: bool = False) -> F:
    number = decimal_input(value, label)
    if number <= 0 if positive else number < 0:
        raise ReferenceContractError(f"{label}: invalid physical rate")
    return number


def _graph(spec: dict, count: int) -> tuple[tuple[str, ...], str, str, dict]:
    obj = _keys(spec, {"nodes", "source", "sink", "edges"}, "graph")
    nodes = obj["nodes"]
    if not isinstance(nodes, list) or not (2 <= len(nodes) <= 12):
        raise ReferenceContractError("graph nodes are missing or exceed reference bound")
    if not all(isinstance(x, str) and x for x in nodes) or len(nodes) != len(set(nodes)):
        raise ReferenceContractError("graph nodes must be unique nonempty names")
    source, sink = obj["source"], obj["sink"]
    if source not in nodes or sink not in nodes or source == sink:
        raise ReferenceContractError("invalid graph source/sink")
    edges = obj["edges"]
    if not isinstance(edges, list) or not (1 <= len(edges) <= 24):
        raise ReferenceContractError("graph edges out of bounds")
    capacities: dict[tuple[str, str], F] = {}
    for ix, edge in enumerate(edges):
        e = _keys(edge, {"from", "to", "capacity", "scaling"}, f"edge {ix}")
        u, v = e["from"], e["to"]
        if u not in nodes or v not in nodes or u == v:
            raise ReferenceContractError("invalid directed edge")
        if e["scaling"] not in ("fixed", "per_front"):
            raise ReferenceContractError("edge scaling must be fixed or per_front")
        cap = _rate(e["capacity"], "edge capacity", positive=True)
        actual = cap * count if e["scaling"] == "per_front" else cap
        capacities[u, v] = capacities.get((u, v), F(0)) + actual
    return tuple(nodes), source, sink, capacities


def _max_flow(spec: dict, count: int) -> F:
    nodes, source, sink, edges = _graph(spec, count)
    residual = {u: {v: F(0) for v in nodes} for u in nodes}
    for (u, v), cap in edges.items():
        residual[u][v] += cap
    total = F(0)
    while True:
        parent: dict[str, str | None] = {source: None}
        queue = deque([source])
        while queue and sink not in parent:
            u = queue.popleft()
            for v in sorted(nodes):
                if v not in parent and residual[u][v] > 0:
                    parent[v] = u
                    queue.append(v)
        if sink not in parent:
            return total
        curr = sink
        gain: F | None = None
        while curr != source:
            prev = parent[curr]
            assert prev is not None
            gain = residual[prev][curr] if gain is None else min(gain, residual[prev][curr])
            curr = prev
        assert gain is not None and gain > 0
        curr = sink
        while curr != source:
            prev = parent[curr]
            assert prev is not None
            residual[prev][curr] -= gain
            residual[curr][prev] += gain
            curr = prev
        total += gain


def _ramp(ramp: dict, duration: int) -> tuple[int, ...]:
    r = _keys(ramp, {"initial", "final", "maximum", "up", "down"}, "ramp")
    for key, value in r.items():
        _integer(value, "ramp." + key, 0 if key in ("up", "down") else 1)
    if r["initial"] > r["maximum"] or r["final"] > r["maximum"]:
        raise ReferenceContractError("ramp endpoints exceed maximum")
    profile = tuple(min(
        r["initial"] + r["up"] * t,
        r["maximum"],
        r["final"] + r["down"] * (duration - 1 - t),
    ) for t in range(duration))
    if min(profile) < 1:
        raise ReferenceContractError("unphysical zero team in active ramp")
    return profile


def _validate(payload: dict) -> tuple[dict, list[dict], list[str]]:
    _keys(payload, {"protocol", "case_id", "inputs", "expected"}, "vector")
    if payload["protocol"] != VERSION or not isinstance(payload["case_id"], str):
        raise ReferenceContractError("unsupported physical reference version")
    data = _keys(
        payload["inputs"],
        {"horizon_weeks", "weather", "performance", "graphs", "resource_caps", "activities"},
        "physical inputs",
    )
    horizon = _integer(data["horizon_weeks"], "horizon_weeks", 1)
    if horizon > LIMIT_WEEKS:
        raise ReferenceContractError("physical reference horizon bound exceeded")
    for key in ("weather", "performance"):
        values = data[key]
        if not isinstance(values, list) or len(values) != horizon:
            raise ReferenceContractError(f"{key}: one exact factor per absolute week required")
        data[key] = tuple(_rate(x, key) for x in values)
        if any(v > 1 for v in data[key]):
            raise ReferenceContractError(f"{key}: factor must be <= 1")
    graphs = data["graphs"]
    if not isinstance(graphs, dict) or not graphs:
        raise ReferenceContractError("graphs must be supplied")
    for name, graph in graphs.items():
        if not isinstance(name, str) or not name:
            raise ReferenceContractError("graph name must be nonempty")
        _graph(graph, 1)
    caps = data["resource_caps"]
    if not isinstance(caps, dict):
        raise ReferenceContractError("resource_caps must be an object")
    data["resource_caps"] = {
        key: _integer(cap, "resource cap", 1) for key, cap in caps.items()
        if isinstance(key, str) and key
    }
    if len(data["resource_caps"]) != len(caps):
        raise ReferenceContractError("invalid resource name")
    activities = data["activities"]
    if not isinstance(activities, list) or not (1 <= len(activities) <= LIMIT_ACTIVITIES):
        raise ReferenceContractError("activities out of bounded domain")
    entries = {}
    for raw in activities:
        a = _keys(raw, {
            "id", "graph", "scope_total", "hours_per_week", "earliest_start",
            "ramp", "predecessors", "resource_units",
        }, "activity")
        name = a["id"]
        if not isinstance(name, str) or not name or name in entries:
            raise ReferenceContractError("activity IDs must be unique")
        if a["graph"] not in graphs:
            raise ReferenceContractError("activity references missing graph")
        a["scope_total"] = _rate(a["scope_total"], "scope_total", positive=True)
        a["hours_per_week"] = _rate(a["hours_per_week"], "hours_per_week", positive=True)
        a["earliest_start"] = _integer(a["earliest_start"], "earliest_start")
        _ramp(a["ramp"], 1)
        if not isinstance(a["predecessors"], list):
            raise ReferenceContractError("predecessors must be an array")
        deps = []
        seen = set()
        for raw_dep in a["predecessors"]:
            dep = _keys(raw_dep, {"id", "threshold", "lag_weeks"}, "predecessor")
            name_dep = dep["id"]
            if not isinstance(name_dep, str) or not name_dep or name_dep == name or name_dep in seen:
                raise ReferenceContractError("invalid or duplicate predecessor")
            seen.add(name_dep)
            threshold = _rate(dep["threshold"], "threshold", positive=True)
            if threshold > 1:
                raise ReferenceContractError("Q-FS threshold must not exceed 1")
            deps.append((name_dep, threshold, _integer(dep["lag_weeks"], "lag_weeks")))
        a["predecessors"] = tuple(deps)
        units = a["resource_units"]
        if not isinstance(units, dict) or not all(
            key in data["resource_caps"] for key in units
        ):
            raise ReferenceContractError("unknown physical resource")
        a["resource_units"] = {k: _integer(v, "resource units", 1) for k, v in units.items()}
        if any(v > data["resource_caps"][k] for k, v in a["resource_units"].items()):
            raise ReferenceContractError("activity exceeds resource capacity")
        entries[name] = a
    ordering = []
    pending = set(entries)
    while pending:
        ready = sorted(x for x in pending if all(d in ordering for d, _, _ in entries[x]["predecessors"]))
        if not ready:
            raise ReferenceContractError("unknown predecessor or precedence cycle")
        ordering.append(ready[0])
        pending.remove(ready[0])
    return data, [entries[n] for n in ordering], ordering


def evaluate_physical(vector: dict[str, Any]) -> dict[str, Any]:
    """Exact bounded search; minimum makespan, then lexicographic start/duration."""
    data, activities, order = _validate(vector)
    horizon = data["horizon_weeks"]
    caps = data["resource_caps"]
    occupancy = {key: [0] * horizon for key in caps}
    solved: dict[str, dict] = {}
    best: tuple[tuple, dict] | None = None
    states = 0

    def search(index: int) -> None:
        nonlocal best, states
        states += 1
        if states > LIMIT_STATES:
            raise ReferenceContractError("physical search budget exceeded; not INFEASIBLE")
        if index == len(activities):
            makespan = max(out["end_week"] + 1 for out in solved.values())
            rank = (makespan, tuple((solved[name]["start_week"], solved[name]["duration_weeks"]) for name in order))
            if best is None or rank < best[0]:
                best = rank, {key: dict(value) for key, value in solved.items()}
            return
        activity = activities[index]
        release = activity["earliest_start"]
        for pred, threshold, lag in activity["predecessors"]:
            if pred not in solved:
                raise ReferenceContractError("predecessor missing from topological order")
            prior = solved[pred]
            total = F(0)
            first: int | None = None
            for week, qty in zip(range(prior["start_week"], prior["end_week"] + 1),
                                 prior["_amounts"], strict=True):
                total += qty
                if total >= threshold * prior["_scope"]:
                    first = week
                    break
            if first is None:
                raise ReferenceContractError("Q-FS threshold never reached")
            release = max(release, first + 1 + lag)
        for start in range(release, horizon):
            for duration in range(1, horizon - start + 1):
                fronts = _ramp(activity["ramp"], duration)
                capacities = tuple(
                    _max_flow(data["graphs"][activity["graph"]], count)
                    * activity["hours_per_week"]
                    * data["weather"][start + ix]
                    * data["performance"][start + ix]
                    for ix, count in enumerate(fronts)
                )
                if sum(capacities) < activity["scope_total"]:
                    continue
                remaining = activity["scope_total"]
                amounts = []
                for cap in capacities:
                    qty = min(remaining, cap)
                    amounts.append(qty)
                    remaining -= qty
                if remaining != 0 or not amounts[-1] or not capacities[-1]:
                    continue  # Reject phantom extra contracted weeks.
                if any(any(
                    occupancy[key][week] + count > caps[key]
                    for week in range(start, start + duration)
                ) for key, count in activity["resource_units"].items()):
                    continue
                for key, count in activity["resource_units"].items():
                    for week in range(start, start + duration):
                        occupancy[key][week] += count
                solved[activity["id"]] = {
                    "start_week": start,
                    "end_week": start + duration - 1,
                    "duration_weeks": duration,
                    "fronts": fronts,
                    "_capacities": capacities,
                    "_amounts": tuple(amounts),
                    "_scope": activity["scope_total"],
                    "front_weeks": sum(fronts),
                    "_fraction": amounts[-1] / capacities[-1],
                }
                search(index + 1)
                del solved[activity["id"]]
                for key, count in activity["resource_units"].items():
                    for week in range(start, start + duration):
                        occupancy[key][week] -= count
    search(0)
    if best is None:
        raise ReferenceContractError("INFEASIBLE within bounded reference horizon")
    result = {}
    for name in sorted(best[1]):
        a = best[1][name]
        result[name] = {
            "start_week": a["start_week"], "end_week": a["end_week"],
            "duration_weeks": a["duration_weeks"], "front_weeks": a["front_weeks"],
            "fronts": list(a["fronts"]),
            "capacity": [_finite_decimal(v, "capacity") for v in a["_capacities"]],
            "quantity": [_finite_decimal(v, "quantity") for v in a["_amounts"]],
            "final_week_fraction": _finite_decimal(a["_fraction"], "final_week_fraction"),
        }
    return {"makespan_weeks": best[0][0], "activities": result}


def verify_physical(vector: dict[str, Any]) -> dict[str, Any]:
    actual = evaluate_physical(vector)
    if actual != vector["expected"]:
        raise ReferenceContractError(
            f"{vector.get('case_id', 'unknown')}: physical golden mismatch "
            f"(actual={actual}, expected={vector['expected']})"
        )
    return actual
