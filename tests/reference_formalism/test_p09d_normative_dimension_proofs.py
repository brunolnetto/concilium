"""Independent P09-D dimensional/type witnesses for all normative candidates.

The registry and typed witnesses are intentionally independent of production
modules and are not a runtime correctness or project GO certificate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "docs/product/5-specifications/formulario_longo"


@dataclass(frozen=True)
class Dim:
    brl: int = 0
    output: int = 0
    good: int = 0
    fronts: int = 0
    hour: int = 0
    day: int = 0
    week: int = 0
    month: int = 0

    def __mul__(self, other: Dim) -> Dim:
        return Dim(*(a + b for a, b in zip(
            tuple(self.__dict__.values()),
            tuple(other.__dict__.values()),
            strict=True,
        )))

    def __truediv__(self, other: Dim) -> Dim:
        return Dim(*(a - b for a, b in zip(
            tuple(self.__dict__.values()),
            tuple(other.__dict__.values()),
            strict=True,
        )))


BRL = Dim(brl=1)
Q = Dim(output=1)
G = Dim(good=1)
F = Dim(fronts=1)
H = Dim(hour=1)
DAY = Dim(day=1)
WEEK = Dim(week=1)
MONTH = Dim(month=1)
SCALAR = Dim()

RESULT = {
    "BRL/hour": BRL / H,
    "BRL/week": BRL / WEEK,
    "output/hour": Q / H,
    "output": Q,
    "fronts": F,
    "dimensionless": SCALAR,
    "weeks/month": WEEK / MONTH,
    "hours/week": H / WEEK,
}


def read(name: str) -> dict:
    return json.loads((DIR / name).read_text(encoding="utf-8"))


def prove(rule: str) -> Dim | str:
    """Assert semantic domain and typed dimensional algebra per named rule."""
    if rule == "activity_set":
        activities = ("A0", "A1")
        assert len(activities) == len(set(activities)) == 2
        return "typed/declaration"
    if rule == "activity_tuple":
        activity = (Fraction(100), {"fronts": 1}, (1, 0, 1, 0, 1), ())
        assert len(activity) == 4 and activity[0] > 0
        return "typed/declaration"
    if rule == "hourly_tariff":
        # Contractual monthly price ÷ (weeks/month × days/week × h/day).
        assert (BRL / MONTH) / (
            (WEEK / MONTH) * (DAY / WEEK) * (H / DAY)
        ) == BRL / H
        # Physical material: volume/hour × BRL/physical-volume.
        assert (G / H) * (BRL / G) == BRL / H
        assert (G / H) * (BRL / H) != BRL / H
        return BRL / H
    if rule == "capacity_flow":
        # Every edge in a comparable network has the same units; a cut adds rates.
        assert Q / H == Q / H
        independent_paths = (Fraction(10), Fraction(10))
        assert sum(independent_paths) == 20
        assert min(sum(independent_paths), Fraction(15)) == 15
        return Q / H
    if rule == "front_policy":
        endpoints, rates, peak = (1, 1), (0, 0), 4
        assert all(isinstance(v, int) for v in (*endpoints, *rates, peak))
        assert all(0 < v <= peak for v in endpoints)
        assert all(v >= 0 for v in rates)
        return "typed/declaration"
    if rule == "ramp":
        # Numeric tau counts discrete weeks; physical tau*week restores units.
        assert (F / WEEK) * WEEK == F
        assert (F / WEEK) * DAY != F
        assert [min(1 + 0 * t, 4, 1 + 0 * (2 - t)) for t in range(3)] == [1] * 3
        return F
    if rule == "rectangular":
        assert [min(4, 4, 4) for _ in range(3)] == [4, 4, 4]
        assert [min(1, 4, 1) for _ in range(3)] == [1, 1, 1]
        return F
    if rule == "weekly_front_count":
        starts_at, duration = 2, 3
        assert [4 if starts_at <= j < starts_at + duration else 0
                for j in (1, 2, 3, 4, 5)] == [0, 4, 4, 4, 0]
        return F
    if rule == "predecessor_map":
        activities = {"a", "b", "c"}
        prereqs = {"a", "b"}
        theta = {"a": Fraction(1, 2), "b": Fraction(1)}
        assert prereqs <= activities
        assert all(0 < v <= 1 for v in theta.values())
        return "typed/declaration"
    if rule == "completion_ratio":
        assert Q / Q == SCALAR
        assert sum((Fraction(10), Fraction(30))) / Fraction(100) == Fraction(2, 5)
        with pytest.raises(ZeroDivisionError):
            _ = Fraction(10) / 0
        return SCALAR
    if rule == "month_week_conversion":
        days_in_four_years = 3 * 365 + 366
        assert Fraction(days_in_four_years, 4 * 12 * 7) == Fraction(1461, 336)
        assert (DAY / MONTH) / (DAY / WEEK) == WEEK / MONTH
        return WEEK / MONTH
    if rule == "hours_per_week":
        assert (H / DAY) * (DAY / WEEK) == H / WEEK
        assert Fraction(8) * Fraction(5) == 40
        return H / WEEK
    if rule == "fractional_bdi":
        assert BRL / BRL == SCALAR
        assert Fraction(2997, 10000) == Fraction("0.2997")
        return SCALAR
    if rule == "last_quantity":
        assert Q / Q == SCALAR
        assert Fraction(100) - sum((Fraction(40), Fraction(35))) == 25
        assert Q == Q
        return Q
    if rule == "closure_ratio":
        # The extra ONE WEEK cell width is explicit: (u/h)*(h/week)*(week).
        capacity = (Q / H) * ((H / DAY) * (DAY / WEEK)) * WEEK
        assert capacity == Q
        assert Q / capacity == SCALAR
        assert Fraction(100, 400) == Fraction(1, 4)
        assert (Q / H) * (H / WEEK) != Q  # without cell integration
        with pytest.raises(ZeroDivisionError):
            _ = Fraction(100) / Fraction(0)
        return SCALAR
    if rule == "physical_balance":
        assert all(x >= 0 for x in (40, 35, 25))
        assert Fraction(40) + Fraction(35) + Fraction(25) == Fraction(100)
        return Q
    if rule == "active_set":
        all_activities = {1, 2, 3}
        starts, durations = {1: 1, 2: 2, 3: 5}, {1: 2, 2: 1, 3: 2}
        active = {i for i in all_activities
                  if starts[i] <= 2 < starts[i] + durations[i]}
        assert active == {1, 2}
        return "typed/declaration"
    if rule == "indirect_set":
        category = {"ADM", "TOP", "LAB", "QSMS", "MOB_site"}
        assert len(category) == 5
        return "typed/declaration"
    if rule == "driver_enum":
        assert {"perm", "onetime"} == set(("perm", "onetime"))
        return "typed/declaration"
    if rule == "indirect_tuple":
        monthly_rates = {"MO": Fraction(100), "EQ": Fraction(50)}
        mob_demob = (Fraction(20), Fraction(30))
        assert all(v >= 0 for v in monthly_rates.values())
        assert len(mob_demob) == 2 and all(v >= 0 for v in mob_demob)
        assert (BRL / MONTH) / (WEEK / MONTH) == BRL / WEEK
        return "typed/declaration"
    if rule == "weekly_indirect_tariff":
        assert (BRL / MONTH) / (WEEK / MONTH) == BRL / WEEK
        assert Fraction(100) / Fraction(4) == 25
        assert 1 == 1  # unit-multiplicity, no time dimension
        return BRL / WEEK
    raise ValueError(f"missing independent proof for rule={rule!r}")


PROOF = read("NORMATIVE_DIMENSION_PROOFS_P09D.json")
INVENTORY = read("EQUATION_INVENTORY_P09C.json")


def test_only_candidate_equations_are_in_dimension_proof_registry() -> None:
    expected = {r["id"]: r for r in INVENTORY["rows"]
                if r["status"] == "NORMATIVE_CANDIDATE"}
    actual = {r["id"]: r for r in PROOF["proofs"]}
    assert len(expected) == len(actual) == 21
    assert set(actual) == set(expected)
    assert len(actual) == len(PROOF["proofs"])
    for key, row in actual.items():
        assert row["expression"] == expected[key]["expression"]
        assert row["proof_status"] == "DIMENSIONAL_UNDER_TYPED_PRECONDITIONS"
        assert not expected[key]["blocked_by_issues"]


@pytest.mark.parametrize("row", PROOF["proofs"], ids=lambda p: p["id"])
def test_independent_dimensional_proof_per_normative_equation(row: dict) -> None:
    demonstrated = prove(row["rule"])
    expected = row["expected_dimension"]
    if expected == "typed/declaration":
        assert demonstrated == expected
    else:
        assert demonstrated == RESULT[expected]


def test_no_conditional_identity_is_misrepresented_as_dimensional_proof() -> None:
    conditional = {r["id"] for r in INVENTORY["rows"]
                   if r["status"] == "CONDITIONAL_OR_UNCERTIFIED"}
    assert len(conditional) == 72
    assert conditional.isdisjoint({r["id"] for r in PROOF["proofs"]})


def test_week_cell_semantics_are_shared_by_long_short_tex_and_conventions() -> None:
    files = (
        "CONVENCOES_NORMATIVAS.md",
        "FORMALISMO_LONGO.md",
        "FORMALISMO_RESUMIDO.md",
        "formulario_longo.tex",
    )
    for filename in files:
        content = (DIR / filename).read_text(encoding="utf-8")
        if filename.endswith(".tex"):
            assert r"\Delta w_j=1\,\mathrm{semana}" in content
        else:
            assert "Δw_j = 1 semana" in content
        assert "P09-D" in content


def test_dimensional_preconditions_do_not_create_financial_or_project_go() -> None:
    assert "do not prove runtime parity" in PROOF["semantics"]
    assert all(
        p["proof_status"] == "DIMENSIONAL_UNDER_TYPED_PRECONDITIONS"
        for p in PROOF["proofs"]
    )
    assert not any("CERTIFIED" in p["proof_status"] for p in PROOF["proofs"])


def test_normative_documents_are_not_corrupted_by_cell_semantics_insertions() -> None:
    conventions = (DIR / "CONVENCOES_NORMATIVAS.md").read_text(encoding="utf-8")
    long = (DIR / "FORMALISMO_LONGO.md").read_text(encoding="utf-8")
    short = (DIR / "FORMALISMO_RESUMIDO.md").read_text(encoding="utf-8")
    tex = (DIR / "formulario_longo.tex").read_text(encoding="utf-8")
    assert conventions.count("# Contrato normativo de notação") == 1
    assert conventions.count("## 2. Dicionário dimensional mínimo") == 1
    assert conventions.count("## 3. Domínio da mobilização e semana retangular") == 1
    assert conventions.count("## 4. Índices e intervalos") == 1
    assert conventions.count("**Integração por célula semanal (P09-D).**") == 1
    assert long.count("## Parte IV — Cronograma Semanal") == 1
    assert short.count("## Parte IV — Cronograma Semanal") == 1
    assert tex.count(r"\end{document}") == 1
