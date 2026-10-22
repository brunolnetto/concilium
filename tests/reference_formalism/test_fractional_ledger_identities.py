"""P11-A: algebraic, exact-rational falsifiers independent of production code.

A test oracle for the mathematical reference contract, NOT a claim that
Concilium has an authoritative allocation/BDI ledger already implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "product" / "5-specifications" / "formulario_longo"


@dataclass(frozen=True)
class Week:
    q: F
    capacity_installed: F
    capacity_exogenous: F
    contracted: F
    variable: F
    reference_quantity: F
    reference_cost: F

    @property
    def closure_fraction(self) -> F | None:
        if self.capacity_exogenous == 0:
            return None
        return self.q / self.capacity_exogenous

    @property
    def installed_utilization(self) -> F | None:
        if self.capacity_installed == 0:
            return None
        return self.q / self.capacity_installed

    @property
    def cost(self) -> F:
        return self.contracted + self.variable

    @property
    def zeta(self) -> F:
        return self.cost / self.reference_cost

    @property
    def chi(self) -> F:
        return self.q / self.reference_quantity

    @property
    def pi(self) -> F | None:
        return (
            (self.cost / self.q) / (self.reference_cost / self.reference_quantity)
            if self.q > 0
            else None
        )


def schedule(quantity: int, exogenous: tuple[int, ...]) -> list[Week]:
    """40 hours * 10 u/h; K=400 full week; V=1 R$/unit, ref=400u/800R$."""
    remaining = F(quantity)
    weeks: list[Week] = []
    for efficiency in exogenous:
        capacity = F(400 * efficiency)
        produced = min(remaining, capacity)
        weeks.append(
            Week(
                q=produced,
                capacity_installed=F(400),
                capacity_exogenous=capacity,
                contracted=F(400),
                variable=produced,
                reference_quantity=F(400),
                reference_cost=F(800),
            )
        )
        remaining -= produced
    assert remaining == 0, "test fixture must close its physical scope"
    return weeks


def aggregate(weeks: list[Week]) -> dict[str, F]:
    q = sum((w.q for w in weeks), F())
    k = sum((w.contracted for w in weeks), F())
    v = sum((w.variable for w in weeks), F())
    ref_q = sum((w.reference_quantity for w in weeks), F())
    ref_cost = sum((w.reference_cost for w in weeks), F())
    assert q > 0 and ref_q > 0 and ref_cost > 0
    cost = k + v
    return {
        "q": q,
        "K": k,
        "V": v,
        "C": cost,
        "Cref": ref_cost,
        "chi": q / ref_q,
        "zeta": cost / ref_cost,
        "pi": (cost / q) / (ref_cost / ref_q),
        "delta": v / cost,
        "Cbeta": k * F(13, 10) + v * F(26, 25),
        "beta_eq": (k * F(3, 10) + v * F(1, 25)) / cost,
    }


@pytest.mark.parametrize(
    ("quantity", "exogenous", "outputs"),
    [
        (
            100,
            (1,),
            {"q": F(100), "K": F(400), "V": F(100), "C": F(500),
             "Cref": F(800), "chi": F(1, 4), "zeta": F(5, 8), "pi": F(5, 2)},
        ),
        (
            900,
            (1, 1, 1),
            {"q": F(900), "K": F(1200), "V": F(900), "C": F(2100),
             "Cref": F(2400), "chi": F(3, 4), "zeta": F(7, 8), "pi": F(7, 6)},
        ),
        (
            900,
            (1, 0, 1, 1),
            {"q": F(900), "K": F(1600), "V": F(900), "C": F(2500),
             "Cref": F(3200), "chi": F(9, 16), "zeta": F(25, 32), "pi": F(25, 18)},
        ),
        (
            400,
            (1,),
            {"q": F(400), "K": F(400), "V": F(400), "C": F(800),
             "Cref": F(800), "chi": F(1), "zeta": F(1), "pi": F(1)},
        ),
    ],
    ids=["one-partial-week", "three-weeks-final-partial", "interior-zero-week",
         "full-week"],
)
def test_exhaustive_fractional_closure_references(
    quantity: int, exogenous: tuple[int, ...], outputs: dict[str, F]
) -> None:
    weeks = schedule(quantity, exogenous)
    summary = aggregate(weeks)
    for key, expected in outputs.items():
        assert summary[key] == expected, key
    assert summary["zeta"] == summary["chi"] * summary["pi"]
    assert sum((week.q for week in weeks), F()) == quantity
    assert summary["V"] == quantity  # only under unit-consumption premise
    assert summary["Cbeta"] == summary["C"] * (1 + summary["beta_eq"])
    assert summary["beta_eq"] == (
        (1 - summary["delta"]) * F(3, 10) + summary["delta"] * F(1, 25)
    )
    for w in weeks:
        if w.q > 0:
            assert w.pi is not None
            assert w.zeta == w.chi * w.pi


def test_partial_week_does_not_mistake_phi_for_exogenous_loss() -> None:
    (week,) = schedule(100, (1,))
    assert week.closure_fraction == F(1, 4)
    assert week.installed_utilization == F(1, 4)
    assert week.zeta == F(5, 8)
    assert week.pi == F(5, 2)
    assert week.zeta != week.pi  # exogenous efficiency = 1; old identity false
    s = aggregate([week])
    assert s["delta"] == F(1, 5)
    assert s["Cbeta"] == F(624)
    assert s["beta_eq"] == F(31, 125)


def test_zero_production_week_has_no_weekly_unit_cost_and_retains_contract() -> None:
    weeks = schedule(900, (1, 0, 1, 1))
    zero = weeks[1]
    assert zero.q == 0
    assert zero.closure_fraction is None  # NOT_EVALUATED if B=0
    assert zero.installed_utilization == 0
    assert zero.pi is None
    assert zero.contracted == 400 and zero.variable == 0
    assert zero.zeta == F(1, 2)


def test_full_utilization_is_not_a_scheduling_penalty() -> None:
    (week,) = schedule(400, (1,))
    assert week.closure_fraction == week.installed_utilization == F(1)
    assert week.zeta == week.pi == F(1)


def test_hour_based_variable_demand_breaks_invariance_under_bottleneck() -> None:
    # Same physical work Q=600 with F(m)=min(10m,15), H=40.
    # At m=2: q=600, hourly per-front fuel=2*40=80 units.
    # At m=4: q=600, hourly per-front fuel=4*40=160 units.
    # Output is identical but physical variable input doubles.
    assert min(2 * 10, 15) * 40 == min(4 * 10, 15) * 40
    assert 2 * 40 != 4 * 40


def test_fractional_contract_is_in_all_three_formalisms() -> None:
    long = (SPEC / "FORMALISMO_LONGO.md").read_text(encoding="utf-8")
    short = (SPEC / "FORMALISMO_RESUMIDO.md").read_text(encoding="utf-8")
    tex = (SPEC / "formulario_longo.tex").read_text(encoding="utf-8")
    for name, source in [("LONGO", long), ("RESUMIDO", short), ("TeX", tex)]:
        assert "FECHAMENTO_FRACIONARIO_E_RAZOES.md" in source, name
        assert "chi" in source or r"\chi" in source, name
        assert "UNKNOWN" in source or "indefinida" in source, name
    # Old unconditional identities must not reappear in the normative bodies.
    assert r"\zeta_{ij} = \varepsilon_{ij}\cdot\pi_{ij}" not in long
    assert r"\boxed{\zeta_{ij} = \varepsilon_{ij}\cdot\pi_{ij}}" not in tex
