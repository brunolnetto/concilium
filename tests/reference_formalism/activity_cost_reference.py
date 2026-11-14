"""Independent oracle: exact contractual (K) cost per activity from P16 chains (N4).

Each chain is one hire of one unit of a contract. It charges the active-week
tariff in every week it works, each week owned by exactly one activity; its
lifecycle cost (idle weeks x idle tariff + MOB + DEMOB) is allocated to the
activities the chain served, pro rata to the active weeks it worked for each.
Costs stay per BDI category (MO, EQ). When the witness totals are given, the
chains must reproduce them exactly. Stdlib only; written from the rule
(P23 supplement N4, #206), not from production code.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-activity-cost/2"


class ActivityCostContractError(ValueError):
    pass


def evaluate_activity_costs(case: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, F]] = {}

    def add(owner: str, category: str, amount: F) -> None:
        row = result.setdefault(owner, {"MO": F(0), "EQ": F(0)})
        row[category] += amount

    for contract in case["inputs"]["contracts"]:
        category = contract["category"]
        if category not in ("MO", "EQ"):
            raise ActivityCostContractError("contract category must be MO or EQ")
        active = F(contract["active_week"])
        idle = F(contract["idle_week"])
        movement = F(contract["mobilize"]) + F(contract["demobilize"])
        standby_total = mobility_total = F(0)
        for chain in contract["chains"]:
            owners = chain["active_week_owner"]
            idle_weeks = chain["idle_weeks"]
            if not owners:
                raise ActivityCostContractError("chain without active weeks cannot own lifecycle cost")
            if not isinstance(idle_weeks, int) or idle_weeks < 0:
                raise ActivityCostContractError("chain idle weeks must be a nonnegative integer")
            worked: dict[str, int] = {}
            for owner in owners.values():
                add(owner, category, active)
                worked[owner] = worked.get(owner, 0) + 1
            lifecycle = idle * idle_weeks + movement
            standby_total += idle * idle_weeks
            mobility_total += movement
            for owner, weeks in worked.items():
                add(owner, category, lifecycle * weeks / len(owners))
        if ("standby" in contract and F(contract["standby"]) != standby_total) or (
            "mobility" in contract and F(contract["mobility"]) != mobility_total
        ):
            raise ActivityCostContractError("chains do not reproduce the witness standby/mobility totals")
    return {k: {c: str(v) for c, v in sorted(row.items())} for k, row in sorted(result.items())}
