"""Markup layers of the sale price: overhead, profit and taxes per category (N9, #206).

The sale price of a cost ``C`` in one category follows the TCU structure
(Acórdão 2622/2013-Plenário):

    P = C (1 + (AC + R+S+G)) (1 + DF) (1 + L) / (1 - T)

and decomposes exactly, layer by layer, in the order the formula builds it:

    overhead_ac  = C * AC
    overhead_rsg = C * (R+S+G)
    overhead_df  = C (1 + AC + R+S+G) * DF
    profit       = C (1 + AC + R+S+G) (1 + DF) * L
    tax_x        = t_x * P                      (taxes are a share of the price)

so that ``C + overhead + profit + taxes = P`` identically. Every amount is
linear in ``C``: the same rates decompose one ledger posting (instance level)
or any aggregate of postings (contract, activity, week, category, project).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from fractions import Fraction

CATEGORIES = ("MO", "EQ", "MAT", "COMB", "IND")
FORMULA = "TCU_ACORDAO_2622_2013"


def _rate(value: object, label: str) -> Fraction:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an exact decimal or rational string")
    try:
        rate = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{label} must be an exact decimal or rational string") from exc
    if rate < 0:
        raise ValueError(f"{label} must be nonnegative")
    return rate


@dataclass(frozen=True)
class LayeredAmount:
    """One cost split into its price layers; additive across postings."""

    cost: Fraction = Fraction(0)
    overhead_ac: Fraction = Fraction(0)
    overhead_rsg: Fraction = Fraction(0)
    overhead_df: Fraction = Fraction(0)
    profit: Fraction = Fraction(0)
    taxes: tuple[tuple[str, Fraction], ...] = ()

    @property
    def overhead(self) -> Fraction:
        return self.overhead_ac + self.overhead_rsg + self.overhead_df

    @property
    def tax_total(self) -> Fraction:
        return sum((amount for _name, amount in self.taxes), Fraction(0))

    @property
    def price(self) -> Fraction:
        return self.cost + self.overhead + self.profit + self.tax_total

    def __add__(self, other: LayeredAmount) -> LayeredAmount:
        merged: dict[str, Fraction] = dict(self.taxes)
        for name, amount in other.taxes:
            merged[name] = merged.get(name, Fraction(0)) + amount
        return LayeredAmount(
            self.cost + other.cost,
            self.overhead_ac + other.overhead_ac,
            self.overhead_rsg + other.overhead_rsg,
            self.overhead_df + other.overhead_df,
            self.profit + other.profit,
            tuple(sorted(merged.items())),
        )

    def as_json(self) -> dict[str, object]:
        return {
            "cost": str(self.cost),
            "overhead_ac": str(self.overhead_ac),
            "overhead_rsg": str(self.overhead_rsg),
            "overhead_df": str(self.overhead_df),
            "overhead": str(self.overhead),
            "profit": str(self.profit),
            "taxes": {name: str(amount) for name, amount in self.taxes},
            "tax_total": str(self.tax_total),
            "price": str(self.price),
        }


@dataclass(frozen=True)
class LayerRates:
    """Declared layer rates of one cost category."""

    ac: Fraction
    rsg: Fraction
    df: Fraction
    profit: Fraction
    taxes: tuple[tuple[str, Fraction], ...] = field(default=())

    def __post_init__(self) -> None:
        rates = (self.ac, self.rsg, self.df, self.profit, *(rate for _name, rate in self.taxes))
        if any(type(rate) is not Fraction or rate < 0 for rate in rates):
            raise ValueError("markup layer rates must be exact nonnegative fractions")
        if len({name for name, _rate in self.taxes}) != len(self.taxes):
            raise ValueError("markup layer taxes must have unique names")
        if self.tax_total >= 1:
            raise ValueError("taxes on the sale price must be below 100%")

    @property
    def tax_total(self) -> Fraction:
        return sum((rate for _name, rate in self.taxes), Fraction(0))

    @property
    def beta(self) -> Fraction:
        """Category markup over cost: P / C - 1."""
        return (1 + self.ac + self.rsg) * (1 + self.df) * (1 + self.profit) / (1 - self.tax_total) - 1

    def decompose(self, cost: Fraction) -> LayeredAmount:
        base = cost * (1 + self.ac + self.rsg)
        with_df = base * (1 + self.df)
        net = with_df * (1 + self.profit)
        price = net / (1 - self.tax_total)
        return LayeredAmount(
            cost=cost,
            overhead_ac=cost * self.ac,
            overhead_rsg=cost * self.rsg,
            overhead_df=base * self.df,
            profit=with_df * self.profit,
            taxes=tuple(sorted((name, rate * price) for name, rate in self.taxes)),
        )

    def as_json(self) -> dict[str, object]:
        return {
            "ac": str(self.ac),
            "rsg": str(self.rsg),
            "df": str(self.df),
            "l": str(self.profit),
            "taxes": {name: str(rate) for name, rate in self.taxes},
        }


def parse_layer_rates(raw: object, label: str) -> LayerRates:
    """``{"ac", "rsg", "df", "l", "taxes": {name: rate}}`` with exact strings."""
    if not isinstance(raw, Mapping) or set(raw) != {"ac", "rsg", "df", "l", "taxes"}:
        raise ValueError(f"{label} must declare exactly ac, rsg, df, l and taxes")
    taxes = raw["taxes"]
    if not isinstance(taxes, Mapping) or any(not isinstance(name, str) or not name for name in taxes):
        raise ValueError(f"{label}.taxes must map tax names to exact rates")
    return LayerRates(
        ac=_rate(raw["ac"], f"{label}.ac"),
        rsg=_rate(raw["rsg"], f"{label}.rsg"),
        df=_rate(raw["df"], f"{label}.df"),
        profit=_rate(raw["l"], f"{label}.l"),
        taxes=tuple(sorted((name, _rate(rate, f"{label}.taxes.{name}")) for name, rate in taxes.items())),
    )


def parse_markup_layers(raw: object) -> dict[str, LayerRates]:
    if not isinstance(raw, Mapping) or set(raw) != set(CATEGORIES):
        raise ValueError("markup_layers must declare exactly MO, EQ, MAT, COMB and IND")
    return {category: parse_layer_rates(raw[category], f"markup_layers.{category}") for category in CATEGORIES}


def decompose_by_category(
    costs: Iterable[tuple[str, Fraction]], layers: Mapping[str, LayerRates]
) -> tuple[dict[str, LayeredAmount], LayeredAmount]:
    """Layered amounts per category and in total for ``(category, cost)`` postings."""
    by_category = {category: LayeredAmount() for category in CATEGORIES}
    for category, cost in costs:
        if category not in layers:
            raise ValueError(f"posting category {category!r} has no declared markup layers")
        by_category[category] = by_category[category] + layers[category].decompose(cost)
    total = LayeredAmount()
    for amount in by_category.values():
        total = total + amount
    return by_category, total
