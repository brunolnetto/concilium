"""Independent goldens for N10: declared site indirects (FORMALISMO_LONGO Part XII)."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from tests.reference_formalism.site_indirects_reference import (
    SiteIndirectsError,
    evaluate_site_indirects,
    evaluate_site_indirects_scope,
)

PATH = Path(__file__).parent / "vectors" / "economic_site_indirects_v1.json"


def scope_goldens() -> list[dict]:
    return json.loads(PATH.read_text(encoding="utf-8"))["scope_vectors"]


@pytest.mark.parametrize("case", scope_goldens(), ids=lambda c: c["case_id"])
def test_site_indirects_scope_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(SiteIndirectsError, match=case["expected_error"]):
            evaluate_site_indirects_scope(case["declaration"])
    else:
        assert evaluate_site_indirects_scope(case["declaration"]) == case["expected"]


def test_scope_hand_checked_values_are_pinned() -> None:
    by_id = {c["case_id"]: c for c in scope_goldens()}
    assert by_id["declared_scope_with_lines"]["expected"] == {"status": "DECLARED", "site_indirects_cost": "57792"}
    assert by_id["no_site_indirects_is_explicit"]["expected"] == {
        "status": "NO_SITE_INDIRECTS",
        "site_indirects_cost": None,
    }
    # Every other scope case is a refusal: absence or inconsistency is never evaluated.
    assert sum("expected_error" in c for c in by_id.values()) == len(by_id) - 2 == 7


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-site-indirects/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_site_indirects_goldens(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(SiteIndirectsError, match=case["expected_error"]):
            evaluate_site_indirects(case["case"])
    else:
        assert evaluate_site_indirects(case["case"]) == case["expected"]


def test_hand_checked_values_are_pinned() -> None:
    """Numbers derived by hand in the vector's hand_check, independent of the oracle code."""
    by_id = {c["case_id"]: c["expected"] for c in goldens() if "expected" in c}
    perm = by_id["perm_four_weeks_by_subcategory"]
    assert perm["by_category"] == {"COMB": "1344", "EQ": "13440", "IND": "2688", "MO": "40320"}
    assert set(perm["by_week"].values()) == {"14448"} and perm["cost"] == "57792"
    assert by_id["weekly_rate_stays_rational"]["by_week"]["2026-W20"] == "1120000/487"
    assert by_id["weekly_rate_stays_rational"]["cost"] == "3360000/487"
    assert by_id["onetime_first_and_last_week"]["by_week"] == {"2026-W19": "80000", "2026-W22": "30000"}
    assert by_id["onetime_single_week_adds_up"]["by_week"] == {"2026-W19": "110000"}
    assert by_id["window_crosses_a_53_week_year"]["weeks"] == ["2026-W52", "2026-W53", "2027-W01", "2027-W02"]
    priced = by_id["price_applies_each_category_markup"]
    assert (priced["cost"], priced["price"]) == ("167792", "1185192/5")
    assert by_id["declared_zero_posts_nothing"]["postings"] == {}


def test_totals_are_three_views_of_the_same_postings() -> None:
    for case in goldens():
        if "expected" not in case:
            continue
        expected = case["expected"]
        cost = Fraction(expected["cost"])
        assert sum(Fraction(row[2]) for row in expected["postings"].values()) == cost
        assert sum(Fraction(v) for v in expected["by_category"].values()) == cost
        assert sum(Fraction(v) for v in expected["by_week"].values()) == cost
        assert sum(Fraction(v) for line in expected["by_line"].values() for v in line.values()) == cost
