"""P11-A independent exact-reference oracle for q, K/V, zeta/pi and BDI.

No production/runtime imports; no floating-point rounding; no invented GO.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/product/5-specifications/formulario_longo/P11A_EFICIENCIA_REAL_IDENTIDADES.md"
F = Fraction


@dataclass(frozen=True)
class Week:
    reference_output: Fraction
    nominal_efficiency: Fraction
    actual_output: Fraction
    contractual_k: Fraction
    variable_per_output: Fraction

    def __post_init__(self) -> None:
        assert self.reference_output >= 0
        assert F(0) <= self.nominal_efficiency <= F(1)
        assert self.actual_output >= 0
        assert self.actual_output <= (
            self.reference_output * self.nominal_efficiency
        )
        assert self.contractual_k >= 0
        assert self.variable_per_output >= 0

    @property
    def nominal_available_output(self) -> Fraction:
        return self.nominal_efficiency * self.reference_output

    @property
    def realized_efficiency(self) -> Fraction | None:
        return (
            self.actual_output / self.reference_output
            if self.reference_output > 0 else None
        )

    @property
    def closure_fraction(self) -> Fraction | None:
        return (
            self.actual_output / self.nominal_available_output
            if self.nominal_available_output > 0 else None
        )

    @property
    def variable_v(self) -> Fraction:
        # Conditional regime: verified, output-proportional consumption.
        return self.actual_output * self.variable_per_output

    @property
    def actual_cost(self) -> Fraction:
        return self.contractual_k + self.variable_v

    @property
    def reference_cost(self) -> Fraction:
        return (
            self.contractual_k
            + self.variable_per_output * self.reference_output
        )

    @property
    def zeta(self) -> Fraction | None:
        return (
            self.actual_cost / self.reference_cost
            if self.reference_cost > 0 else None
        )

    @property
    def pi(self) -> Fraction | None:
        if self.reference_cost <= 0 or self.actual_output <= 0:
            return None
        if self.reference_output <= 0:
            return None
        return (
            (self.actual_cost / self.actual_output)
            / (self.reference_cost / self.reference_output)
        )


def combine(weeks: tuple[Week, ...]) -> dict[str, Fraction | None]:
    assert weeks
    output = sum((w.actual_output for w in weeks), F(0))
    reference_output = sum((w.reference_output for w in weeks), F(0))
    k = sum((w.contractual_k for w in weeks), F(0))
    v = sum((w.variable_v for w in weeks), F(0))
    total = k + v
    reference_cost = sum((w.reference_cost for w in weeks), F(0))
    return {
        "Q": output,
        "reference_output": reference_output,
        "eff_real": output / reference_output if reference_output > 0 else None,
        "K": k,
        "V": v,
        "cost": total,
        "cost_ref": reference_cost,
        "delta": v / total if total > 0 else None,
        "zeta": total / reference_cost if reference_cost > 0 else None,
        "pi": (
            (total / output) / (reference_cost / reference_output)
            if output > 0 and reference_output > 0 and reference_cost > 0
            else None
        ),
    }


def price_with_bdi_once(
    categories: tuple[tuple[str, Fraction, Fraction], ...],
) -> tuple[Fraction, Fraction | None]:
    assert len({name for name, _, _ in categories}) == len(categories)
    assert all(cost >= 0 and rate >= 0 for _, cost, rate in categories)
    total = sum((cost for _, cost, _ in categories), F(0))
    priced = sum((cost * (1 + rate) for _, cost, rate in categories), F(0))
    return priced, (priced / total - 1 if total > 0 else None)


def test_one_partial_week_falsifies_nominal_efficiency_identity() -> None:
    week = Week(F(400), F(1), F(100), F(400), F(1))
    assert week.closure_fraction == F(1, 4)
    assert week.realized_efficiency == F(1, 4)
    assert week.actual_cost == F(500)
    assert week.reference_cost == F(800)
    assert week.zeta == F(5, 8)
    assert week.pi == F(5, 2)
    assert week.realized_efficiency * week.pi == week.zeta
    assert week.nominal_efficiency * week.pi != week.zeta
    assert week.contractual_k == F(400)
    assert week.contractual_k * week.closure_fraction != week.contractual_k
    assert combine((week,))["delta"] == F(1, 5)

    price, beta = price_with_bdi_once((
        ("K", week.contractual_k, F(3, 10)),
        ("V", week.variable_v, F(1, 10)),
    ))
    assert price == F(630)
    assert beta == F(13, 50)


def test_three_week_weighted_efficiency_and_financial_reconciliation() -> None:
    weeks = (
        Week(F(400), F(1), F(400), F(400), F(1)),
        Week(F(400), F(1), F(400), F(400), F(1)),
        Week(F(400), F(1), F(100), F(400), F(1)),
    )
    c = combine(weeks)
    assert c["Q"] == F(900)
    assert c["reference_output"] == F(1200)
    assert c["eff_real"] == F(3, 4)
    assert c["K"] == F(1200)
    assert c["V"] == F(900)
    assert c["cost"] == F(2100)
    assert c["cost_ref"] == F(2400)
    assert c["zeta"] == F(7, 8)
    assert c["pi"] == F(7, 6)
    assert c["delta"] == F(3, 7)
    assert c["zeta"] == c["eff_real"] * c["pi"]
    assert c["K"] + c["V"] == sum((w.actual_cost for w in weeks), F(0))
    price, rate = price_with_bdi_once((
        ("K", c["K"], F(3, 10)),
        ("V", c["V"], F(1, 10)),
    ))
    assert price == F(2550)
    assert rate == F(3, 14)


def test_zero_production_interior_week_still_bills_k_without_fake_pi() -> None:
    week = Week(F(400), F(0), F(0), F(400), F(1))
    assert week.realized_efficiency == 0
    assert week.closure_fraction is None  # 0/0 exogenous capacity
    assert week.actual_cost == F(400)
    assert week.variable_v == 0
    assert week.zeta == F(1, 2)
    assert week.pi is None


def test_fully_delivered_week_has_identity_reference() -> None:
    week = Week(F(400), F(1), F(400), F(400), F(1))
    assert week.realized_efficiency == 1
    assert week.closure_fraction == 1
    assert week.zeta == 1
    assert week.pi == 1


def test_exogenous_efficiency_and_partial_closure_multiply() -> None:
    week = Week(F(400), F(1, 2), F(100), F(400), F(1))
    assert week.nominal_available_output == F(200)
    assert week.closure_fraction == F(1, 2)
    assert week.realized_efficiency == F(1, 4)
    assert week.nominal_efficiency * week.closure_fraction == F(1, 4)
    assert week.realized_efficiency * week.pi == week.zeta


def test_zero_bases_and_missing_prices_never_gain_favorable_ratio() -> None:
    week = Week(F(0), F(0), F(0), F(0), F(0))
    assert week.realized_efficiency is None
    assert week.closure_fraction is None
    assert week.zeta is None
    assert week.pi is None
    assert combine((week,))["delta"] is None
    priced, rate = price_with_bdi_once((("K", F(0), F(0)),))
    assert priced == 0 and rate is None
    with pytest.raises(AssertionError):
        Week(F(400), F(1, 2), F(401), F(400), F(1))


def test_output_invariance_requires_verified_quantity_consumption() -> None:
    output = F(100)
    price_per_good = F(2)
    good_per_output = F(3)
    weekly_splits = ((F(100),), (F(50), F(25), F(25)))
    costs = [sum((q * good_per_output * price_per_good for q in qs), F(0))
             for qs in weekly_splits]
    assert costs == [F(600), F(600)]
    # A shared bottleneck can hold F(m) at 10 output/hour while the
    # per-hour good burn doubles for m=2; V(Q) is then NOT invariant.
    f1, f2, burn1, burn2 = F(10), F(10), F(3), F(6)
    assert f1 == f2 and (burn1 / f1) != (burn2 / f2)
    assert output * burn1 / f1 != output * burn2 / f2


def test_unreconciled_or_duplicate_categories_cannot_be_priced() -> None:
    with pytest.raises(AssertionError):
        price_with_bdi_once((
            ("K", F(10), F(3, 10)),
            ("K", F(10), F(3, 10)),
        ))


def test_normative_derivation_declares_all_guards_and_conditional_costs() -> None:
    doc = DOC.read_text(encoding="utf-8")
    for phrase in (
        r"\varepsilon",
        "UNDEFINED",
        "UNKNOWN",
        "não",
        "uma",
        r"\Delta w_j",
        r"\zeta",
        r"\pi",
        "BDI",
        "F(m)",
    ):
        assert phrase in doc, phrase
