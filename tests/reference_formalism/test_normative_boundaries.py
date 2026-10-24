"""P09-B: executable normative boundaries and cross-document consistency.

No imports from Concilium production modules; only standard-library exact
rationals and the published LONGO/RESUMIDO/TeX normative representations.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs" / "product" / "5-specifications"
DOCS /= "formulario_longo"
FILES = {
    "LONGO": DOCS / "FORMALISMO_LONGO.md",
    "RESUMIDO": DOCS / "FORMALISMO_RESUMIDO.md",
    "TEX": DOCS / "formulario_longo.tex",
}


@dataclass(frozen=True)
class Dim:
    """Exponents of physical Q, operating hours, BRL, physical g and fronts."""

    q: int = 0
    h: int = 0
    brl: int = 0
    g: int = 0
    fronts: int = 0

    def __mul__(self, other: Dim) -> Dim:
        return Dim(*(x + y for x, y in zip(self.__dict__.values(), other.__dict__.values(), strict=True)))

    def __truediv__(self, other: Dim) -> Dim:
        return Dim(*(x - y for x, y in zip(self.__dict__.values(), other.__dict__.values(), strict=True)))


Q = Dim(q=1)
H = Dim(h=1)
BRL = Dim(brl=1)
G = Dim(g=1)
M = Dim(fronts=1)


def test_dimensions_distinguish_front_rate_and_installed_capacity() -> None:
    per_front = Q / (H * M)
    installed = per_front * M
    assert installed == Q / H
    assert installed * H == Q
    assert installed * M * H != Q  # double team multiplication is invalid


def test_consumption_rate_dimensions_do_not_mix_hour_with_output() -> None:
    per_produced_unit = G / Q
    per_operating_hour = G / H
    assert per_produced_unit * Q == G
    assert per_operating_hour * H == G
    assert per_operating_hour * Q != G
    assert (BRL / G) * G == BRL


def ramp(m0: int, up: int, m1: int, down: int, maximum: int, weeks: int) -> list[int]:
    if min(m0, m1, maximum, weeks) <= 0 or min(up, down) < 0:
        raise ValueError("invalid ramp domain")
    if max(m0, m1) > maximum:
        raise ValueError("endpoints exceed team maximum")
    return [
        min(m0 + up * t, maximum, m1 + down * (weeks - 1 - t))
        for t in range(weeks)
    ]


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        ((2, 0, 2, 0, 2, 4), [2, 2, 2, 2]),
        ((1, 0, 1, 0, 4, 3), [1, 1, 1]),
        ((1, 1, 1, 1, 3, 5), [1, 2, 3, 2, 1]),
    ],
)
def test_ramp_boundaries(parameters: tuple[int, ...], expected: list[int]) -> None:
    assert ramp(*parameters) == expected


@pytest.mark.parametrize("parameters", [(0, 1, 1, 1, 4, 3), (1, -1, 1, 0, 4, 3)])
def test_invalid_ramp_rejected(parameters: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        ramp(*parameters)


@pytest.mark.parametrize(
    ("first", "second", "gap"),
    [
        ((1, 2), (3, 5), 0),
        ((1, 2), (4, 5), 1),
        ((2, 2), (5, 5), 2),
    ],
)
def test_inclusive_week_gap_is_half_open_gap(
    first: tuple[int, int], second: tuple[int, int], gap: int
) -> None:
    a, b = first
    c, d = second
    assert a <= b < c <= d
    assert max(0, c - b - 1) == gap
    assert max(0, c - (b + 1)) == gap


@pytest.mark.parametrize(
    ("gap", "idle", "restart", "max_gap", "keep"),
    [
        (0, 100, 0, 0, True),
        (1, 100, 100, 1, True),  # economic tie: fewer transitions
        (1, 100, 99, 1, False),
        (1, 100, 160, 1, True),
        (1, 100, 160, 0, False),  # financially better but infeasible
    ],
)
def test_exact_standby_economics_and_feasibility(
    gap: int, idle: int, restart: int, max_gap: int, keep: bool
) -> None:
    assert (gap <= max_gap and Fraction(gap * idle) <= Fraction(restart)) is keep


def test_partial_last_week_has_full_contractual_but_physical_variable_cost() -> None:
    capacity, scope, contractual_week, rate_per_unit = (
        Fraction(400), Fraction(100), Fraction(80), Fraction(3, 5)
    )
    phi = scope / capacity
    assert phi == Fraction(1, 4)
    assert contractual_week == 80  # not contractual_week * phi
    assert scope * rate_per_unit == 60
    assert capacity * rate_per_unit != 60


def test_zero_denominators_never_certify_go() -> None:
    for denominator in (Fraction(0),):
        with pytest.raises(ZeroDivisionError):
            Fraction(100) / denominator


def _source_documents() -> dict[str, str]:
    return {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}


def _assert_capacity_resource_contract(docs: dict[str, str]) -> None:
    for name, source in docs.items():
        assert "F_i(m)" in source, name
        assert "F_i(m_{ij})" in source, name
        assert "eta_s" in source or r"\eta_s" in source or "η_s" in source, name
        assert r"\eta_{p,j}" in source and r"\eta_{w,j}" in source, name
        assert "C_pool" in source or r"C^{pool}" in source, name
        assert "C_MOBDEMOB" in source or r"C^{MOB" in source, name

    # No executable production update is allowed to reintroduce rho*eta_s*m.
    forbidden = ("q_ij ← ρ_i · ε", "prod ← Σ_τ ρ_i · ε", "η_{s,ij} ←")
    for name, source in docs.items():
        assert not any(token in source for token in forbidden), name


def test_three_formalisms_share_physical_and_cost_contract() -> None:
    _assert_capacity_resource_contract(_source_documents())


def test_specification_mutation_fails_deterministically() -> None:
    original = _source_documents()
    changed = dict(original)
    changed["RESUMIDO"] = changed["RESUMIDO"].replace("F_i(m_{ij})", "wrong_capacity", 999)
    with pytest.raises(AssertionError):
        _assert_capacity_resource_contract(changed)


def test_normative_appendix_keeps_symbol_provenance_and_week_intervals() -> None:
    source = (DOCS / "CONVENCOES_NORMATIVAS.md").read_text(encoding="utf-8")
    for token in (
        "rho_i^front",
        "rho_i^peak",
        "F_i(m)",
        "mu_i^+",
        "mu_i^-",
        "[j_i^0, j_i^0+N_i)",
        "UNKNOWN",
        "NOT_EVALUATED",
        "gap=0",
    ):
        assert token in source, token


def test_rectangular_ramp_requires_zero_slopes_and_maximum_endpoints() -> None:
    """Reject an implication present in the historical LONGO/TeX but false."""
    long = FILES["LONGO"].read_text(encoding="utf-8")
    tex = FILES["TEX"].read_text(encoding="utf-8")
    summarized = FILES["RESUMIDO"].read_text(encoding="utf-8")

    condition = r"\\bigl(\\mu_i^+=\\mu_i^-=0\\bigr)\\land\\bigl(m_i^0=m_i^1=m_i^{\\max}\\bigr)"
    invalid = r"\\mu_i^+ = \\mu_i^- = 0 \\implies m_i(\\tau) = m_i^{\\max}"
    for name, document in (("LONGO", long), ("TEX", tex)):
        assert condition in document, name
        assert invalid not in document, name

    assert "m_i^0=m_i^1=m_i^{max}" in summarized
    assert ramp(1, 0, 1, 0, 4, 3) == [1, 1, 1]
    assert ramp(4, 0, 4, 0, 4, 3) == [4, 4, 4]
