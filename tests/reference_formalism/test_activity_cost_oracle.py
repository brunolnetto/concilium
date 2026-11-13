"""Independent goldens for exact per-activity contractual cost (P17-C basis)."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.reference_formalism.activity_cost_reference import (
    ActivityCostContractError,
    evaluate_activity_costs,
)

PATH = Path(__file__).parent / "vectors" / "activity_cost_reconciliation_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-activity-cost/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_activity_cost_goldens_are_exact(case: dict) -> None:
    assert evaluate_activity_costs(deepcopy(case)) == case["expected"]


def test_corrupted_activity_cost_golden_is_detected() -> None:
    case = deepcopy(goldens()[0])
    case["expected"]["A"]["EQ"] = "35"
    assert evaluate_activity_costs(deepcopy(case)) != case["expected"]


def test_lifecycle_cost_without_partitions_is_rejected() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["contracts"][0]["partitions"] = {"A": "0", "B": "0"}
    with pytest.raises(ActivityCostContractError, match="partitions"):
        evaluate_activity_costs(case)
