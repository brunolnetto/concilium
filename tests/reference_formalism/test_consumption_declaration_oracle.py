"""Independent goldens for N6 (activity variable cost and NENHUM declaration)."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.consumption_declaration_reference import (
    ConsumptionDeclarationError,
    evaluate_activity_consumption,
)

PATH = Path(__file__).parent / "vectors" / "consumption_declaration_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-consumption-declaration/1"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_consumption_declaration_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(ConsumptionDeclarationError, match=case["expected_error"]):
            evaluate_activity_consumption(case["activity"])
    else:
        assert Fraction(evaluate_activity_consumption(case["activity"])) == Fraction(case["expected"])


def test_corrupted_consumption_golden_is_detected() -> None:
    case = goldens()[0]
    assert Fraction(evaluate_activity_consumption(case["activity"])) != Fraction("42.805")
