"""P09-C: exhaustive *inventory* guard and independent dimensional falsifiers.

This does not certify expressions marked conditional, nor claim that a registry
entry alone constitutes proof of its mathematics.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/product/5-specifications/formulario_longo"
INVENTORY = DOCS / "EQUATION_INVENTORY_P09C.json"
LONG = DOCS / "FORMALISMO_LONGO.md"


def read_inventory() -> dict:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def test_every_long_formalism_display_equation_is_accounted_for_exactly_once() -> None:
    source = LONG.read_text(encoding="utf-8")
    observed = [match.strip() for match in re.findall(r"\$\$([\s\S]*?)\$\$", source)]
    spec = read_inventory()
    rows = spec["rows"]
    assert spec["schema"] == "concilium.formalism.equation_inventory.v1"
    assert spec["equation_count"] == len(rows) == len(observed) == 93
    assert [row["id"] for row in rows] == [
        f"FL-{n:03d}" for n in range(1, 94)
    ]
    assert [row["expression"] for row in rows] == observed
    assert len(set(observed)) == len(observed)


def test_inventory_requires_explicit_provenance_dimension_and_uncertainty() -> None:
    for row in read_inventory()["rows"]:
        for field in (
            "id",
            "section",
            "expected_result_dimension",
            "input_provenance",
            "output_projection",
            "downstream_consumer",
            "classification",
            "dimensional_proof",
            "blocked_by_issues",
        ):
            assert field in row and row[field] is not None, (row["id"], field)
        assert row["expected_result_dimension"] not in ("", "unknown"), row["id"]
        assert row["input_provenance"] != "unclassified", row["id"]
        assert row["classification"] in (
            "NORMATIVE_CANDIDATE",
            "CONDITIONAL_OR_UNCERTIFIED",
        )
        if row["blocked_by_issues"]:
            assert row["classification"] == "CONDITIONAL_OR_UNCERTIFIED"
        # No automatic "all 93 dimensionally certified" claim from a syntax audit.
        assert row["dimensional_proof"] == "REQUIRES_INDEPENDENT_VERIFICATION"


def test_finance_and_pricing_relations_are_not_promoted_out_of_dependencies() -> None:
    rows = {int(x["id"][-3:]): x for x in read_inventory()["rows"]}
    for number in (26, 34, 37, 38, 39, 40, 53, 54):
        assert 11 in rows[number]["blocked_by_issues"]
    for number in (59, 60, 61, 62, 63, 64):
        assert 13 in rows[number]["blocked_by_issues"]
    for number in (91, 92, 93):
        assert 21 in rows[number]["blocked_by_issues"]


@dataclass(frozen=True)
class Dimension:
    physical_output: int = 0
    physical_good: int = 0
    operating_hour: int = 0
    money: int = 0
    week: int = 0
    front: int = 0

    def __mul__(self, other: Dimension) -> Dimension:
        return Dimension(*(a + b for a, b in zip(
            tuple(self.__dict__.values()), tuple(other.__dict__.values()), strict=True
        )))

    def __truediv__(self, other: Dimension) -> Dimension:
        return Dimension(*(a - b for a, b in zip(
            tuple(self.__dict__.values()), tuple(other.__dict__.values()), strict=True
        )))


Q = Dimension(physical_output=1)
G = Dimension(physical_good=1)
H = Dimension(operating_hour=1)
BRL = Dimension(money=1)
W = Dimension(week=1)
M = Dimension(front=1)
SCALAR = Dimension()


def test_independent_physical_and_financial_dimensional_contracts() -> None:
    front_productivity = Q / (H * M)
    assert front_productivity * M == Q / H
    assert front_productivity * M * H == Q
    assert front_productivity * M * M * H != Q  # bogus eta_s * m
    assert (Q / H) * H == Q  # weekly physical capacity
    assert (G / H) * (BRL / G) == BRL / H  # kappa times priced physical unit
    assert (G / Q) * Q * (BRL / G) == BRL  # output-proportional purchase
    assert (BRL / H) * H == BRL  # contractual operational cost
    assert (BRL / (G * W)) * G * W == BRL  # holding by stock-week
    assert (BRL / W) * W == BRL  # contracted standby
    assert BRL / Q != BRL / H  # quote per activity unit != hourly rate
    assert BRL / BRL == SCALAR
    assert Q / Q == SCALAR


def test_week_boundary_and_tie_economics_have_independent_counterexamples() -> None:
    # Consecutive occupied inclusive intervals [1,2],[3,5] have no idle week.
    assert max(0, 3 - 2 - 1) == 0
    # Baseline full K charges a whole week even when final production is 1/4.
    q, capacity, weekly_k, per_output_v = (
        Fraction(100), Fraction(400), Fraction(80), Fraction(3, 5)
    )
    phi = q / capacity
    assert phi == Fraction(1, 4)
    assert weekly_k == 80
    assert per_output_v * q == 60
    assert weekly_k * phi != weekly_k
    # With a positive, feasible gap and exact economic tie, keeping reduces trips.
    idle_week_cost = Fraction(100)
    remobilize_cost = Fraction(100)
    assert idle_week_cost <= remobilize_cost
    # In a non-priceable regime, zero denominator must never be a good margin.
    with pytest.raises(ZeroDivisionError):
        _ = BRL.money / 0


def test_legacy_consumable_proxy_never_forges_physical_rate_or_price() -> None:
    sources = {
        file: (DOCS / file).read_text(encoding="utf-8")
        for file in ("FORMALISMO_LONGO.md", "FORMALISMO_RESUMIDO.md", "formulario_longo.tex")
    }
    for name, content in sources.items():
        assert "UNVERIFIED" in content, name
        assert "dimensionalmente inválido" in content, name
        assert "κ_r = 1" not in content, name
        assert "kappa_r = 1" not in content, name
        assert r"\kappa_r = 1" not in content, name
    # Bad fictional kappa [good/hour] times price [BRL/hour]
    # gives BRL*good/hour^2, not an hourly monetary price.
    assert (G / H) * (BRL / H) != BRL / H
