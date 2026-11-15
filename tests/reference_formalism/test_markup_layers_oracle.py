"""Independent goldens for N9: markup layers of the sale price."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.markup_layers_reference import MarkupLayersError, evaluate_markup_layers

PATH = Path(__file__).parent / "vectors" / "economic_markup_layers_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-markup-layers/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_markup_layers_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(MarkupLayersError, match=case["expected_error"]):
            evaluate_markup_layers(case["case"])
    else:
        assert evaluate_markup_layers(case["case"]) == case["expected"]


def test_hand_checked_values_are_pinned() -> None:
    """Numbers derived by hand in the vector's hand_check, independent of the oracle code."""
    by_id = {c["case_id"]: c["expected"] for c in goldens() if "expected" in c}
    labour = by_id["labour_layers_of_100"]["by_category"]["MO"]
    assert (labour["overhead"], labour["profit"], labour["price"]) == ("759/100", "96831/10000", "1172731/9027")
    assert Fraction(labour["taxes"]) == Fraction("0.0973") * Fraction(1172731, 9027)
    assert by_id["supply_layer_is_profit_only"]["profit_layer_share"] == "1/26"
    assert by_id["aggregate_adds_layers_and_weights_the_floor"]["aggregate_floor"] == "239/2000"
    # Golden fixture layer set: (1 + 1/10)(1 + 2/11) = 13/10; profit 1/5 of cost, 2/13 of the price.
    fixture = by_id["golden_fixture_layers_markup_three_tenths"]
    assert fixture["total"] == {"cost": "660", "overhead": "66", "profit": "132", "taxes": "0", "price": "858"}
    assert Fraction(fixture["total"]["price"]) / Fraction(fixture["total"]["cost"]) - 1 == Fraction(3, 10)
    assert fixture["profit_layer_share"] == "2/13"
    # Same markup 3/10, different layers: the profit share is what the minimum sees.
    thin = by_id["same_markup_thin_profit_fails_only_the_profit_criterion"]
    assert (thin["total"]["price"], thin["profit_layer_share"]) == ("130", "1/26")
    assert Fraction(thin["profit_layer_share"]) < Fraction(1, 20) < Fraction(3, 13)
    assert by_id["profit_only_markup_one_tenth"]["profit_layer_share"] == "1/11"


def test_oracle_is_stdlib_only() -> None:
    source = (Path(__file__).parent / "markup_layers_reference.py").read_text(encoding="utf-8")
    assert "concilium" not in source


def test_layers_always_add_up_to_the_price() -> None:
    for case in goldens():
        if "expected" not in case:
            continue
        total = case["expected"]["total"]
        assert sum(Fraction(total[k]) for k in ("cost", "overhead", "profit", "taxes")) == Fraction(total["price"])
