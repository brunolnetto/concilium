"""Independent oracle: exact contractual (K) cost per activity from P16 contracts.

FORMALISMO_LONGO Parts IX–X / P17-C: each contract charges its active-week
tariff in every week an instance is active, owned by exactly one activity;
its non-active cost (standby + MOB/DEMOB) is allocated to activities in
proportion to the persisted item partitions. Costs are kept per BDI category
(MO, EQ) so that C_i^K = Σ_contracts (owned active weeks · tariff + share of
non-active cost). Stdlib only; written from the rule, not from production code.
"""

from __future__ import annotations

from fractions import Fraction as F
from typing import Any

VERSION = "formalism-activity-cost/1"


class ActivityCostContractError(ValueError):
    pass


def evaluate_activity_costs(case: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, F]] = {}
    for contract in case["inputs"]["contracts"]:
        category = contract["category"]
        if category not in ("MO", "EQ"):
            raise ActivityCostContractError("contract category must be MO or EQ")
        tariff = F(contract["active_week"])
        for owner in contract["active_week_owner"].values():
            row = result.setdefault(owner, {"MO": F(0), "EQ": F(0)})
            row[category] += tariff
        nonactive = F(contract["standby"]) + F(contract["mobility"])
        weights = {k: F(v) for k, v in contract["partitions"].items()}
        total = sum(weights.values(), F(0))
        if nonactive and total <= 0:
            raise ActivityCostContractError("non-active cost needs positive partitions")
        for owner, weight in weights.items():
            if nonactive and weight > 0:
                row = result.setdefault(owner, {"MO": F(0), "EQ": F(0)})
                row[category] += nonactive * weight / total
    return {k: {c: str(v) for c, v in sorted(row.items())} for k, row in sorted(result.items())}
