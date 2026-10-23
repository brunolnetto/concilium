"""P19-B: weekly inventory holding is an INDIRECT cost, never acquisition V.

Post monetary ownership from the exact P19-A physical stock ledger. A holding
tariff has an explicit unit and END_OF_WEEK base; no monetary fallback,
no implicit stock reconstruction, and no financial GO certification.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from concilium.domain.units import normalize_unidade

from .contractual_cost_ledger import CostPosting, ExclusiveCostLedger, PostingNature
from .physical_consumption_rates import convert_physical
from .physical_stock_ledger import StockGood, StockProjection

HoldingBasis = Literal["END_OF_WEEK"]


@dataclass(frozen=True)
class HoldingTariff:
    good_id: str
    amount_per_unit_week: Fraction
    physical_unit: str
    basis: HoldingBasis = "END_OF_WEEK"

    def __post_init__(self) -> None:
        if not isinstance(self.good_id, str) or not self.good_id.strip():
            raise ValueError("holding tariff needs stable good identity")
        if type(self.amount_per_unit_week) is not Fraction or self.amount_per_unit_week < 0:
            raise ValueError("holding tariff requires exact nonnegative R$/unit/week")
        if self.basis != "END_OF_WEEK":
            raise ValueError("holding basis must be explicit END_OF_WEEK")
        if not isinstance(self.physical_unit, str):
            raise ValueError("holding tariff requires physical unit")
        object.__setattr__(self, "physical_unit", normalize_unidade(self.physical_unit))


@dataclass(frozen=True)
class HoldingWeekCharge:
    good_id: str
    week: str
    closing_in_stock_unit: Fraction
    billable_stock: Fraction
    billable_unit: str
    holding_cost: Fraction


@dataclass(frozen=True)
class HoldingJournal:
    ledger: ExclusiveCostLedger
    charges: tuple[HoldingWeekCharge, ...]
    authority: str = "HOLDING_PREVIEW_NOT_PROJECT_GO"

    @property
    def holding_cost(self) -> Fraction:
        return sum((charge.holding_cost for charge in self.charges), Fraction(0))


def post_exact_weekly_holding(
    base: ExclusiveCostLedger,
    stock: StockProjection,
    goods: Mapping[str, StockGood],
    tariffs: Mapping[str, HoldingTariff],
) -> HoldingJournal:
    """Post C_inv = sum(rate[g] * S[g,j,END]) once as INDIRECT (not V).

    Requires a shortage-free physical projection and an explicit tariff for
    every projected good. A provenance-limited preview remains a preview.
    """
    if not isinstance(base, ExclusiveCostLedger) or not isinstance(stock, StockProjection):
        raise ValueError("exact base ledger and physical stock evidence are required")
    if not stock.feasible:
        raise ValueError("holding cannot be certified against physical inventory shortage")
    physical_types = {row.good_id for row in stock.rows}
    if not physical_types or set(goods) != physical_types or set(tariffs) != physical_types:
        raise ValueError("each physical stock good requires exactly one holding tariff")

    for good_id, good in goods.items():
        tariff = tariffs[good_id]
        if not isinstance(good, StockGood) or good.good_id != good_id:
            raise ValueError("physical stock metadata does not match good identity")
        if not isinstance(tariff, HoldingTariff) or tariff.good_id != good_id:
            raise ValueError("holding tariff identity does not match physical stock")
        # Fail before posting if the tariff dimension is not convertible.
        convert_physical(Fraction(1), good.unit, tariff.physical_unit)

    seen: set[tuple[str, str]] = set()
    charges: list[HoldingWeekCharge] = []
    postings = list(base.postings)
    for row in stock.rows:
        if row.unit != goods[row.good_id].unit:
            raise ValueError("stock row unit differs from its physical good registry")
        key = (row.good_id, row.week)
        if key in seen:
            raise ValueError("duplicate stock week would double charge holding")
        seen.add(key)
        good = goods[row.good_id]
        rate = tariffs[row.good_id]
        priced_quantity = convert_physical(row.closing, good.unit, rate.physical_unit)
        amount = priced_quantity * rate.amount_per_unit_week
        charges.append(HoldingWeekCharge(
            row.good_id, row.week, row.closing, priced_quantity,
            rate.physical_unit, amount,
        ))
        if amount > 0:
            postings.append(CostPosting(
                ("STOCK_HOLDING", row.good_id, row.week),
                PostingNature.HOLDING,
                "IND",
                amount,
                f"PHYSICAL_STOCK:{row.good_id}",
                row.week,
            ))
    new_ledger = ExclusiveCostLedger(tuple(postings), contract_scope=base.contract_scope)
    if new_ledger.direct != base.direct or new_ledger.indirect != (
        base.indirect + sum((x.holding_cost for x in charges), Fraction(0))
    ):
        raise ValueError("inventory holding postings did not reconcile to exclusive ledger")
    return HoldingJournal(new_ledger, tuple(charges))
