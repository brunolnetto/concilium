"""ADR-075 Phase 2 — Matching Oracle using OR-Tools SimpleMinCostFlow.

Problem formulation (per resource r) using a single "waste" node W:

  Supply nodes (i):  boundary_supply_i[r]  → available for perpetuation/dismiss
  Demand nodes (j):  boundary_demand_j[r]  → need units via perpetuation/hire
  W (waste/exchange): net = -Σ supply_i + Σ demand_j  (handles imbalance)

  Arcs:
    supply_i → demand_j : cap=min(supply, demand), unit_cost=0  (perpetuate)
      — eligible iff f_i <= s_j AND s_j - f_i <= delta_max
    supply_i → W        : cap=supply_i, unit_cost=c_demob        (dismiss)
    W → demand_j        : cap=demand_j, unit_cost=c_mob          (fresh hire)

  This formulation allows any combination of perpetuation, hiring, and dismissal
  without forcing all demand to be freshly hired.  The solver minimises total
  cost by preferring the zero-cost perpetuation arcs first.

Costs are converted to integer centavos (×100) internally and divided back.

Concurrent pairs:
  (i, j, r) in concurrent_pairs_lost if:
    - f_i > s_j  (overlap → perpetuation blocked in current schedule)
    - f_i - s_j <= delta_max  (gap if serialized would be within threshold)
    - boundary_supply_i[r] > 0 AND boundary_demand_j[r] > 0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ortools.graph.python import min_cost_flow

from concilium.domain.models.optimization import (
    ActivityPlan,
    PerpetuationSolution,
    RampProfile,
)

_log = logging.getLogger(__name__)

# Scaling factor: R$ → integer centavos for OR-Tools integer cost API
_COST_SCALE = 100


@dataclass
class MatchingOracle:
    """Min-cost flow oracle for perpetuation chain optimisation (ADR-075 §4.2).

    Args:
        mob_costs:  {resource_id: (c_mob_per_unit, c_demob_per_unit)} in R$.
        delta_max:  Maximum gap in weeks between end of i and start of j for
                    perpetuation to be eligible (default 2 weeks per ADR-075).
    """

    mob_costs: dict[str, tuple[float, float]]
    delta_max: int = 2

    # ── public API ────────────────────────────────────────────────────────────

    def solve(
        self,
        plans: list[ActivityPlan],
        profiles: dict[str, RampProfile],
    ) -> PerpetuationSolution:
        """Compute optimal perpetuation assignment for a given schedule."""
        if not plans:
            return PerpetuationSolution()

        all_edges: list[tuple[str, str, str, int]] = []
        total_cost_scaled = 0
        mob_events: dict[str, int] = {}
        concurrent_lost: list[tuple[str, str, str]] = []

        resource_ids = {res for rp in profiles.values() for res in rp.resources_per_team}

        for res in resource_ids:
            if res not in self.mob_costs:
                continue
            c_mob, c_demob = self.mob_costs[res]
            edges_r, cost_r, events_r, conc_r = self._solve_resource(res, plans, profiles, c_mob, c_demob)
            all_edges.extend(edges_r)
            total_cost_scaled += cost_r
            mob_events[res] = events_r
            concurrent_lost.extend(conc_r)

        return PerpetuationSolution(
            edges=all_edges,
            mob_cost_actual=total_cost_scaled / _COST_SCALE,
            mob_events_by_resource=mob_events,
            concurrent_pairs_lost=concurrent_lost,
        )

    # ── per-resource solver ───────────────────────────────────────────────────

    def _solve_resource(
        self,
        res: str,
        plans: list[ActivityPlan],
        profiles: dict[str, RampProfile],
        c_mob: float,
        c_demob: float,
    ) -> tuple[list[tuple[str, str, str, int]], int, int, list[tuple[str, str, str]]]:
        """Solve perpetuation for a single resource type using W-node formulation."""
        supply: dict[str, int] = {}
        demand: dict[str, int] = {}

        for plan in plans:
            rp = profiles.get(plan.activity_id)
            if rp is None:
                continue
            s_val = rp.boundary_supply.get(res, 0)
            d_val = rp.boundary_demand.get(res, 0)
            if s_val > 0:
                supply[plan.activity_id] = s_val
            if d_val > 0:
                demand[plan.activity_id] = d_val

        if not supply and not demand:
            return [], 0, 0, []

        window: dict[str, tuple[int, int]] = {p.activity_id: p.window for p in plans}

        # Eligible perpetuation pairs: f_i <= s_j AND gap <= delta_max
        eligible: list[tuple[str, str]] = []
        for aid_i in supply:
            f_i = window[aid_i][1]
            for aid_j in demand:
                if aid_i == aid_j:
                    continue
                s_j = window[aid_j][0]
                if f_i <= s_j and s_j - f_i <= self.delta_max:
                    eligible.append((aid_i, aid_j))

        # Concurrent pairs: f_i > s_j (overlap) AND overlap <= delta_max
        concurrent_lost: list[tuple[str, str, str]] = []
        for aid_i in supply:
            f_i = window[aid_i][1]
            for aid_j in demand:
                if aid_i == aid_j:
                    continue
                s_j = window[aid_j][0]
                if f_i > s_j and f_i - s_j <= self.delta_max:
                    concurrent_lost.append((aid_i, aid_j, res))

        # ── W-node min-cost flow formulation ─────────────────────────────
        # Node layout:
        #   supply_i → node index 0..n_s-1
        #   demand_j → node index n_s..n_s+n_d-1
        #   W (waste/exchange) → node index n_s+n_d
        supply_ids = list(supply.keys())
        demand_ids = list(demand.keys())
        n_s = len(supply_ids)
        n_d = len(demand_ids)

        node_supply_idx = {aid: i for i, aid in enumerate(supply_ids)}
        node_demand_idx = {aid: n_s + i for i, aid in enumerate(demand_ids)}
        node_W = n_s + n_d  # waste/exchange node

        sum_supply = sum(supply.values())
        sum_demand = sum(demand.values())
        # W net supply: absorbs excess supply, provides deficit demand
        W_net = sum_demand - sum_supply

        c_mob_int = round(c_mob * _COST_SCALE)
        c_demob_int = round(c_demob * _COST_SCALE)

        smcf = min_cost_flow.SimpleMinCostFlow()

        # Set node supplies
        for aid, qty in supply.items():
            smcf.set_node_supply(node_supply_idx[aid], qty)
        for aid, qty in demand.items():
            smcf.set_node_supply(node_demand_idx[aid], -qty)
        smcf.set_node_supply(node_W, W_net)

        # Arcs: supply_i → W (dismissal)
        arc_dismiss: dict[str, int] = {}
        for aid_i, qty_s in supply.items():
            arc_idx = smcf.add_arc_with_capacity_and_unit_cost(node_supply_idx[aid_i], node_W, qty_s, c_demob_int)
            arc_dismiss[aid_i] = arc_idx

        # Arcs: W → demand_j (fresh hire)
        arc_hire: dict[str, int] = {}
        for aid_j, qty_d in demand.items():
            arc_idx = smcf.add_arc_with_capacity_and_unit_cost(node_W, node_demand_idx[aid_j], qty_d, c_mob_int)
            arc_hire[aid_j] = arc_idx

        # Arcs: supply_i → demand_j (perpetuate, cost=0)
        arc_perp: dict[tuple[str, str], int] = {}
        for aid_i, aid_j in eligible:
            cap = min(supply[aid_i], demand[aid_j])
            arc_idx = smcf.add_arc_with_capacity_and_unit_cost(node_supply_idx[aid_i], node_demand_idx[aid_j], cap, 0)
            arc_perp[(aid_i, aid_j)] = arc_idx

        # Solve
        status = smcf.solve()
        if status != smcf.OPTIMAL:
            _log.warning(
                "MatchingOracle: min-cost flow not OPTIMAL for resource %s (status=%s)",
                res,
                status,
            )
            naive_cost = sum_demand * c_mob_int + sum_supply * c_demob_int
            return [], naive_cost, sum_demand, concurrent_lost

        # Extract perpetuation edges
        edges: list[tuple[str, str, str, int]] = []
        for (aid_i, aid_j), arc_idx in arc_perp.items():
            flow = smcf.flow(arc_idx)
            if flow > 0:
                edges.append((aid_i, aid_j, res, flow))

        # Count mob events: dismissals + fresh hires
        dismissals = sum(smcf.flow(arc_dismiss[aid_i]) for aid_i in supply)
        fresh_hires = sum(smcf.flow(arc_hire[aid_j]) for aid_j in demand)
        mob_event_count = dismissals + fresh_hires

        return edges, smcf.optimal_cost(), mob_event_count, concurrent_lost
