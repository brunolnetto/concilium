"""Independent goldens for N9.1: project declaration merged over the profile's markup layers."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.project_markup_merge_reference import (
    ProjectMarkupMergeError,
    evaluate_project_markup_merge,
)

PATH = Path(__file__).parent / "vectors" / "economic_project_markup_merge_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-project-markup-merge/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_project_markup_merge_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(ProjectMarkupMergeError, match=case["expected_error"]):
            evaluate_project_markup_merge(case["case"])
    else:
        assert evaluate_project_markup_merge(case["case"]) == case["expected"]


def test_hand_checked_values_are_pinned() -> None:
    """Numbers derived by hand in the vector's hand_check, independent of the oracle code."""
    by_id = {c["case_id"]: c["expected"] for c in goldens() if "expected" in c}
    iss = by_id["iss_negotiated_from_5_to_2_percent"]
    assert iss["beta"]["MO"] == "240031/932700"
    assert iss["by_category"]["MO"]["price"] == "1172731/9327"
    assert Fraction(iss["by_category"]["MO"]["taxes"]) == Fraction("0.0673") * Fraction(1172731, 9327)
    assert iss["origin"]["MO"]["taxes"] == {
        "cofins": "profile",
        "iss": "project",
        "pis": "profile",
        "cssl": "profile",
        "ir": "profile",
    }
    indirect = by_id["profit_negotiated_and_iss_not_applicable"]
    assert indirect["rates"]["IND"]["taxes"]["iss"] == "0" and indirect["origin"]["IND"]["l"] == "project"
    assert (indirect["by_category"]["IND"]["profit"], indirect["by_category"]["IND"]["price"]) == (
        "32277/5000",
        "316622/1361",
    )
    assert by_id["supply_row_gains_taxes_declared_by_the_project"]["beta"]["MAT"] == "153/1927"
    assert by_id["no_project_declaration_is_exactly_the_profile"]["beta"]["MO"] == "270031/902700"
    assert by_id["merge_is_per_category_and_aggregates_by_addition"]["total"]["price"] == "10872811/9327"


def test_overhead_is_never_changed_by_the_project() -> None:
    for case in goldens():
        if "expected" not in case:
            continue
        for category, base in case["case"]["base"].items():
            rates, origin = case["expected"]["rates"][category], case["expected"]["origin"][category]
            for field in ("ac", "rsg", "df"):
                assert Fraction(rates[field]) == Fraction(base[field]) and origin[field] == "profile"


def test_layers_always_add_up_to_the_price() -> None:
    for case in goldens():
        if "expected" not in case:
            continue
        total = case["expected"]["total"]
        assert sum(Fraction(total[k]) for k in ("cost", "overhead", "profit", "taxes")) == Fraction(total["price"])
