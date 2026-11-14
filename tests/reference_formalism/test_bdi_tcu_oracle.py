"""Independent goldens for N9: category BDI by the TCU formula."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.bdi_tcu_reference import BdiError, evaluate_bdi

PATH = Path(__file__).parent / "vectors" / "economic_bdi_tcu_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-bdi-tcu/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_bdi_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(BdiError, match=case["expected_error"]):
            evaluate_bdi(case["case"])
    else:
        assert evaluate_bdi(case["case"]) == case["expected"]


def test_corrupted_bdi_golden_is_detected() -> None:
    """The multiplicative variant (1+AC)(1+R)... is not the TCU formula."""
    case = goldens()[0]["case"]
    multiplicative = (
        (1 + Fraction(case["AC"]))
        * (1 + Fraction(case["RSG"]))
        * (1 + Fraction(case["DF"]))
        * (1 + Fraction(case["L"]))
    ) / (1 - Fraction(case["T"])) - 1
    assert Fraction(evaluate_bdi(case)) != multiplicative
