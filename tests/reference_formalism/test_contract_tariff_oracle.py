"""Independent goldens for N8: weekly pool tariff from catalog price + declared terms."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.contract_tariff_reference import ContractTariffError, evaluate_contract_tariff

PATH = Path(__file__).parent / "vectors" / "pool_contract_tariff_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-contract-tariff/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_contract_tariff_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(ContractTariffError, match=case["expected_error"]):
            evaluate_contract_tariff(case["case"])
    else:
        assert evaluate_contract_tariff(case["case"]) == case["expected"]


def test_corrupted_tariff_golden_is_detected() -> None:
    """The cent-rounded value is not the exact tariff."""
    case = goldens()[0]
    assert Fraction(evaluate_contract_tariff(case["case"])["active_week"]) != Fraction("17985.76")
