"""Independent oracle: P16 pool demand from fronts and team composition (N7).

d_gj = sum_i m_ij * a_ig^front: every resource type g scales with the
activity's fronts m_ij by its own per-front units. The heterogeneous sum
sum_g a_ig^front is never a front count. Stdlib only; written from the rule
(CAPACIDADE_E_RECURSOS, P23 supplement N7), not from production code.
"""

from __future__ import annotations

from typing import Any

VERSION = "formalism-pool-demand/1"


class PoolDemandError(ValueError):
    pass


def evaluate_pool_demand(case: dict[str, Any]) -> dict[str, list[int]]:
    horizon = case["horizon_weeks"]
    if not isinstance(horizon, int) or horizon <= 0:
        raise PoolDemandError("horizon must be a positive integer")
    demand: dict[str, list[int]] = {}
    for activity in case["activities"]:
        fronts = activity["fronts"]
        if len(fronts) != horizon or any(not isinstance(m, int) or m < 0 for m in fronts):
            raise PoolDemandError(f"{activity['id']}: fronts must be one nonnegative integer per week")
        composition = activity["composition"]
        if not composition or any(not isinstance(a, int) or a <= 0 for a in composition.values()):
            raise PoolDemandError(f"{activity['id']}: per-front composition must be positive integers")
        for resource, per_front in composition.items():
            series = demand.setdefault(resource, [0] * horizon)
            for week, m in enumerate(fronts):
                series[week] += m * per_front
    return demand
