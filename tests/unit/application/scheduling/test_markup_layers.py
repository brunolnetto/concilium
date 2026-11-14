"""N9 (#206): exact markup layers and the profit-layer criterion."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from concilium.application.scheduling.markup_layers import (
    LayeredAmount,
    decompose_by_category,
    parse_layer_rates,
    parse_markup_layers,
)

ROOT = Path(__file__).resolve().parents[4]
VECTORS = json.loads(
    (ROOT / "tests/reference_formalism/vectors/economic_markup_layers_v1.json").read_text(encoding="utf-8")
)["vectors"]
LABOUR = {
    "ac": "0.05",
    "rsg": "0.01",
    "df": "0.015",
    "l": "0.09",
    "taxes": {"iss": "0.05", "cssl": "0.0199", "ir": "0.0274"},
}
SUPPLY = {"ac": "0", "rsg": "0", "df": "0", "l": "0.04", "taxes": {}}


@pytest.mark.parametrize("case", [c for c in VECTORS if "expected" in c], ids=lambda c: c["case_id"])
def test_production_layers_match_the_oracle_vector(case: dict) -> None:
    rates = {category: parse_layer_rates(raw, category) for category, raw in case["case"]["rates"].items()}
    by_category, total = decompose_by_category(
        ((category, Fraction(cost)) for category, cost in case["case"]["costs"].items()), rates
    )
    for category, expected in case["expected"]["by_category"].items():
        amount = by_category[category]
        observed = {
            "cost": amount.cost,
            "overhead": amount.overhead,
            "profit": amount.profit,
            "taxes": amount.tax_total,
            "price": amount.price,
        }
        assert {k: str(v) for k, v in observed.items()} == expected
    assert str(total.profit / total.price) == case["expected"]["profit_layer_share"]


def test_layers_are_linear_so_instance_and_aggregate_agree() -> None:
    """Decomposing each posting and adding equals decomposing the summed cost."""
    rates = parse_layer_rates(LABOUR, "MO")
    postings = [Fraction(n, 7) for n in (3, 11, 250, 1)]
    summed = LayeredAmount()
    for cost in postings:
        summed = summed + rates.decompose(cost)
    assert summed == rates.decompose(sum(postings, Fraction(0)))
    assert summed.price == sum(postings, Fraction(0)) * (1 + rates.beta)


def test_category_markup_is_the_layers_own_consequence() -> None:
    assert parse_layer_rates(LABOUR, "MO").beta == Fraction(270031, 902700)
    assert parse_layer_rates(SUPPLY, "MAT").beta == Fraction(1, 25)


@pytest.mark.parametrize(
    "raw",
    [
        {**LABOUR, "ac": 0.05},
        {**LABOUR, "taxes": {"iss": "1"}},
        {k: v for k, v in LABOUR.items() if k != "df"},
        {**LABOUR, "extra": "0"},
        {**LABOUR, "l": "-0.01"},
    ],
)
def test_inexact_or_incomplete_layers_are_rejected(raw: dict) -> None:
    with pytest.raises(ValueError):
        parse_layer_rates(raw, "MO")


def test_all_five_categories_must_declare_layers() -> None:
    with pytest.raises(ValueError, match="exactly MO, EQ, MAT, COMB and IND"):
        parse_markup_layers({"MO": LABOUR})
    with pytest.raises(ValueError, match="no declared markup layers"):
        decompose_by_category([("EQ", Fraction(1))], {"MO": parse_layer_rates(LABOUR, "MO")})
