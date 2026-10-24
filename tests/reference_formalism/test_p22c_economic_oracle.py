"""P22-C independent economic goldens and adversarial physical/accounting falsifiers."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.reference_formalism.economic_reference import (
    evaluate_economic,
    verify_economic,
)
from tests.reference_formalism.protocol import ReferenceContractError

PATH = Path(__file__).parent / "vectors" / "economic_reconciliation_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-economic/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_all_economic_goldens_are_exact_and_hand_checked(case: dict) -> None:
    result = verify_economic(deepcopy(case))
    assert result["totals"]["total"] == case["expected"]["totals"]["total"]
    assert result["totals"]["direct"] == str(
        int(result["totals"]["K"]) + int(result["totals"]["V"])
    )
    assert result["pool"]["standby"] == [
        p - d for p, d in zip(result["pool"]["presence"],
                             result["pool"]["demand"], strict=True)
    ]
    assert len(result["posting_ids"]) == len(set(result["posting_ids"]))


def test_fixed_layer_pool_minimum_is_not_global_fungible_optimum() -> None:
    data = deepcopy(goldens()[3])
    result = evaluate_economic(data)
    assert result["totals"]["total"] == "92"
    assert result["pool"]["chains"] == 2
    assert result["pool"]["standby"] == [0, 1, 1, 0]
    assert int(result["totals"]["total"]) < 120


def test_counterfactual_discounted_keep_and_fullrate_split() -> None:
    base = deepcopy(goldens()[0])
    assert evaluate_economic(base)["pool"]["presence"] == [1, 1, 1, 1]
    base["inputs"]["contract"]["idle"] = "100"
    base["inputs"]["contract"]["regime"] = "FULL_RATE_STANDBY"
    assert evaluate_economic(base)["pool"]["presence"] == [1, 0, 0, 1]
    assert evaluate_economic(base)["pool"]["movement_cost"] == "160"


def test_off_hire_is_not_a_zero_price_standby_fallback() -> None:
    case = deepcopy(goldens()[2])
    case["inputs"]["contract"]["off_hire_weeks"] = []
    with pytest.raises(ReferenceContractError, match="off-hire weeks"):
        evaluate_economic(case)
    case = deepcopy(goldens()[2])
    case["inputs"]["contract"]["off_hire_weeks"] = [0]
    with pytest.raises(ReferenceContractError, match="cannot mask"):
        evaluate_economic(case)


def test_zero_idle_price_must_still_respect_max_gap() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["contract"]["idle"] = "0"
    case["inputs"]["contract"]["max_idle_gap"] = 0
    result = evaluate_economic(case)
    assert result["pool"]["chains"] == 2
    assert result["pool"]["standby"] == [0, 0, 0, 0]


def test_mutations_to_external_production_result_are_rejected() -> None:
    wrong = deepcopy(goldens()[0])
    wrong["expected"]["totals"]["K"] = "200"  # lost paid idle weeks
    with pytest.raises(ReferenceContractError, match="economic golden mismatch"):
        verify_economic(wrong)
    wrong = deepcopy(goldens()[1])
    wrong["expected"]["totals"]["quote_with_BDI"] = "300"
    with pytest.raises(ReferenceContractError, match="economic golden mismatch"):
        verify_economic(wrong)


def test_missing_measurement_or_price_provenance_rejected() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["goods"][0]["extra_source"] = None
    with pytest.raises(ReferenceContractError, match="provenance"):
        evaluate_economic(case)
    case = deepcopy(goldens()[0])
    case["inputs"]["goods"][0]["price_source"] = ""
    with pytest.raises(ReferenceContractError, match="provenance"):
        evaluate_economic(case)


def test_unit_mismatch_and_stockout_rejected() -> None:
    case = deepcopy(goldens()[1])
    case["inputs"]["goods"][0]["order_unit"] = "kg"
    with pytest.raises(ReferenceContractError, match="dimension mismatch"):
        evaluate_economic(case)
    case = deepcopy(goldens()[1])
    case["inputs"]["goods"][0]["orders_weekly"] = ["59000", "0"]
    with pytest.raises(ReferenceContractError, match="inventory stockout|unreconciled"):
        evaluate_economic(case)


def test_no_double_category_or_duplicate_physical_good() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["goods"][0]["category"] = "EQ"
    with pytest.raises(ReferenceContractError, match="cannot post K"):
        evaluate_economic(case)
    case = deepcopy(goldens()[0])
    case["inputs"]["goods"].append(deepcopy(case["inputs"]["goods"][0]))
    with pytest.raises(ReferenceContractError, match="identities"):
        evaluate_economic(case)


def test_cubic_metre_and_millilitre_purchases_have_exact_volume_parity() -> None:
    baseline = deepcopy(goldens()[1])
    alternate = deepcopy(baseline)
    # 60,000 mL = 60 L = 0.06 m3, exactly.
    alternate["inputs"]["goods"][0]["order_unit"] = "m3"
    alternate["inputs"]["goods"][0]["orders_weekly"] = ["0.06", "0"]
    assert evaluate_economic(alternate) == verify_economic(baseline)


def test_nonzero_starting_inventory_requires_valuation() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["goods"][0]["initial_stock"] = "2"
    with pytest.raises(ReferenceContractError, match="initial inventory valuation"):
        evaluate_economic(case)


def test_tiny_pool_does_not_accept_phantom_capacity() -> None:
    case = deepcopy(goldens()[3])
    case["inputs"]["contract"]["instances"] = 1
    with pytest.raises(ReferenceContractError, match="capacity below physical demand"):
        evaluate_economic(case)


def test_currency_and_markup_are_evidenced_not_guessed() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["contract"]["currency"] = "USD"
    with pytest.raises(ReferenceContractError, match="currency"):
        evaluate_economic(case)
    case = deepcopy(goldens()[0])
    del case["inputs"]["bdi"]["IND"]
    with pytest.raises(ReferenceContractError, match="missing/unknown"):
        evaluate_economic(case)


def test_negative_margin_is_reported_not_certified_as_healthy() -> None:
    case = deepcopy(goldens()[3])
    case["inputs"]["sale_price"] = "50"
    result = evaluate_economic(case)
    assert result["totals"]["margin"] == "-0.84"
    assert not result["totals"]["margin_positive"]


def test_three_week_zero_demand_is_not_a_contract() -> None:
    case = deepcopy(goldens()[2])
    case["inputs"]["demand"] = [0, 0, 0]
    case["inputs"]["contract"]["off_hire_weeks"] = [1]
    assert evaluate_economic(case)["pool"]["chains"] == 0
    assert evaluate_economic(case)["pool"]["active_cost"] == "0"
