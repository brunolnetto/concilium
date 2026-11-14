"""Independent goldens for N8.1: per-resource rcpsp_spec derived from project data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.reference_formalism.pool_spec_reference import PoolSpecError, evaluate_pool_spec

PATH = Path(__file__).parent / "vectors" / "pool_spec_from_project_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-pool-spec/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_pool_spec_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(PoolSpecError, match=case["expected_error"]):
            evaluate_pool_spec(case["case"])
    else:
        assert evaluate_pool_spec(case["case"]) == case["expected"]


def test_corrupted_pool_spec_golden_is_detected() -> None:
    case = goldens()[0]
    assert evaluate_pool_spec(case["case"])["activities"]["eap-01"]["duration_weeks"] != 13
