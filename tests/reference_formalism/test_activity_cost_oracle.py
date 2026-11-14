"""Independent goldens for exact per-activity contractual cost (N4, P17-C basis)."""

from __future__ import annotations

import json
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.activity_cost_reference import (
    ActivityCostContractError,
    evaluate_activity_costs,
)

PATH = Path(__file__).parent / "vectors" / "activity_cost_reconciliation_v2.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-activity-cost/2"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_activity_cost_goldens_are_exact(case: dict) -> None:
    assert evaluate_activity_costs(deepcopy(case)) == case["expected"]


def test_corrupted_activity_cost_golden_is_detected() -> None:
    case = deepcopy(goldens()[0])
    case["expected"]["A"]["EQ"] = "35"
    assert evaluate_activity_costs(deepcopy(case)) != case["expected"]


def test_activity_totals_conserve_the_pool_cost() -> None:
    """Allocation moves money between activities, never creates or drops it."""
    for case in goldens():
        total = sum(Fraction(v) for row in case["expected"].values() for v in row.values())
        pool = Fraction(0)
        for contract in case["inputs"]["contracts"]:
            weeks = sum(len(chain["active_week_owner"]) for chain in contract["chains"])
            pool += (
                Fraction(contract["active_week"]) * weeks
                + Fraction(contract["standby"])
                + Fraction(contract["mobility"])
            )
        assert total == pool, case["case_id"]


def test_chains_that_do_not_reproduce_the_witness_are_rejected() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["contracts"][0]["standby"] = "3"
    with pytest.raises(ActivityCostContractError, match="reproduce"):
        evaluate_activity_costs(case)


def test_chain_without_active_weeks_is_rejected() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["contracts"][0]["chains"].append({"active_week_owner": {}, "idle_weeks": 0})
    with pytest.raises(ActivityCostContractError, match="without active weeks"):
        evaluate_activity_costs(case)
