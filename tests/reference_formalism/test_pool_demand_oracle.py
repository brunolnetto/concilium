"""Independent goldens for N7 pool demand (#206). Production parity lives in tests/unit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.reference_formalism.pool_demand_reference import PoolDemandError, evaluate_pool_demand

PATH = Path(__file__).parent / "vectors" / "pool_demand_from_fronts_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-pool-demand/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_pool_demand_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(PoolDemandError, match=case["expected_error"]):
            evaluate_pool_demand(case["case"])
    else:
        assert evaluate_pool_demand(case["case"]) == case["expected"]


def test_corrupted_pool_demand_golden_is_detected() -> None:
    case = goldens()[0]
    assert evaluate_pool_demand(case["case"])["EQ-USINA-SOLOS-300TH"] != [7, 7]
