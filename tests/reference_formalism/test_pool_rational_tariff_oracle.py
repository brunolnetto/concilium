"""P22-C pool oracle with exact rational tariffs (N8): goldens and fail-closed inputs."""

from __future__ import annotations

import json
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.economic_reference import _pool, evaluate_economic, verify_economic
from tests.reference_formalism.protocol import ReferenceContractError, decimal_input, rational_input

VECTORS = Path(__file__).parent / "vectors"
PATH = VECTORS / "pool_exact_rational_tariff_v1.json"
TARIFF_KEYS = ("active", "idle", "movement")


def _document() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-pool-rational-tariff/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


def goldens() -> list[dict]:
    return [case for case in _document() if "expected" in case]


def rejections() -> list[dict]:
    return [case for case in _document() if "expected_error" in case]


def _evaluate(case: dict) -> dict:
    record = _pool(tuple(case["demand"]), deepcopy(case["contract"]))
    total = record["active_cost"] + record["idle_cost"] + record["movement_cost"]
    rendered = {key: str(value) if isinstance(value, Fraction) else value for key, value in record.items()}
    return rendered | {"K": str(total)}


def _economic_case(index: int = 0) -> dict:
    doc = json.loads((VECTORS / "economic_reconciliation_v1.json").read_text(encoding="utf-8"))
    return deepcopy(doc["vectors"][index])


def test_vector_file_has_goldens_and_rejections() -> None:
    assert len(goldens()) >= 4 and len(rejections()) >= 5
    assert len(goldens()) + len(rejections()) == len(_document())


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_rational_tariff_goldens_are_exact(case: dict) -> None:
    assert case["hand_check"].strip()
    assert _evaluate(case) == case["expected"]


def test_corrupted_rational_golden_is_detected() -> None:
    """The cent rounding of the catalog tariff is not the exact K."""
    case = goldens()[0]
    rounded = deepcopy(case)
    rounded["contract"]["active"] = rounded["contract"]["idle"] = "17985.76"
    assert _evaluate(rounded)["K"] == "6798576/25"  # 271943.04
    assert _evaluate(rounded)["K"] != case["expected"]["K"]
    assert Fraction(case["expected"]["K"]) == 4 * Fraction("78205.92") / Fraction(1461, 336) + 200000


@pytest.mark.parametrize("key", TARIFF_KEYS)
@pytest.mark.parametrize("case", rejections(), ids=lambda c: c["case_id"])
def test_invalid_tariffs_fail_closed(case: dict, key: str) -> None:
    base = goldens()[1]
    contract = deepcopy(base["contract"]) | {key: case["tariff"]}
    with pytest.raises(ReferenceContractError, match=case["expected_error"]):
        _pool(tuple(base["demand"]), contract)


@pytest.mark.parametrize("bad", ["1/0", "-1/2", "1.5/2", "a/b", 0.5, 1, None, "1/-2", "/2", "", "²/3", "١/٢", "1_0/3"])
def test_rational_input_rejects_non_exact_forms(bad: object) -> None:
    with pytest.raises(ReferenceContractError):
        rational_input(bad, "tariff")


@pytest.mark.parametrize("text", ["0", "100", "0.25", "-3.5", "1e3", "2.0000000000000000000000000001"])
def test_rational_input_keeps_decimal_behaviour(text: str) -> None:
    assert rational_input(text, "x") == decimal_input(text, "x")


def test_rational_input_is_exact() -> None:
    assert rational_input("1/2", "x") == rational_input("0.5", "x") == Fraction(1, 2)
    assert rational_input("218976576/12175", "x") * Fraction(1461, 336) == Fraction("78205.92")
    assert rational_input("0/7", "x") == 0
    assert rational_input("6/4", "x") == Fraction(3, 2)


def test_decimal_input_still_rejects_rationals() -> None:
    with pytest.raises(ReferenceContractError, match="not a decimal value"):
        decimal_input("1/2", "x")


def test_economic_ledger_accepts_a_rational_tariff_with_terminating_totals() -> None:
    case = _economic_case()
    case["inputs"]["contract"] |= {"active": "200/2", "idle": "75/3", "movement": "160/2"}
    assert verify_economic(case)["totals"]["K"] == "250"


def test_economic_ledger_fails_closed_on_nonterminating_totals() -> None:
    """The decimal economic ledger never rounds: a nonterminating K is rejected there."""
    case = _economic_case()
    case["inputs"]["contract"]["active"] = "100/3"
    with pytest.raises(ReferenceContractError, match="nonterminating decimal"):
        evaluate_economic(case)


@pytest.mark.parametrize("field", ["sale_price", "indirect_weekly", "bdi", "goods.price", "goods.rate"])
def test_rationals_are_admitted_only_for_pool_tariffs(field: str) -> None:
    case = _economic_case()
    inputs = case["inputs"]
    if field == "sale_price":
        inputs["sale_price"] = "4000/2"
    elif field == "indirect_weekly":
        inputs["indirect_weekly"][0] = "1/2"
    elif field == "bdi":
        inputs["bdi"]["EQ"] = "1/4"
    else:
        inputs["goods"][0][field.split(".")[1]] = "10/2"
    with pytest.raises(ReferenceContractError, match="not a decimal value"):
        evaluate_economic(case)
