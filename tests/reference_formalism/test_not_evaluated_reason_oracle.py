"""Independent goldens for N11: classification of the persisted not-evaluated cause."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.reference_formalism.not_evaluated_reason_reference import ReasonError, classify_recorded_reason

PATH = Path(__file__).parent / "vectors" / "economic_not_evaluated_reasons_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-not-evaluated-reason/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_not_evaluated_reason_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(ReasonError, match=case["expected_error"]):
            classify_recorded_reason(case["case"])
    else:
        assert classify_recorded_reason(case["case"]) == case["expected"]


def test_order_matters_first_matching_row_wins() -> None:
    both = {"recorded": "bdi_projeto_exato requires p18_consumption_preview_enabled"}
    assert classify_recorded_reason(both) == "BDI_PROJETO_NAO_EXATO"
