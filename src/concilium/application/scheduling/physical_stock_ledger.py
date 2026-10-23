"""P19-A: exact weekly physical inventory ledger from P18-B evidence.

Acquisition monetary postings are NOT receipts: consumable V is priced usage,
while a receipt must have its own physical delivery/generation source. The
stock identity is explicit and cannot fabricate deliveries to mask shortages.
No production throughput is recomputed: the only demand comes from U_g,j.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from concilium.domain.units import normalize_unidade

from .physical_consumption_journal import AcquisitionEvidenceLine
from .physical_consumption_rates import convert_physical

StockSource = Literal["EXTERNAL_DELIVERY", "INTERNAL_GENERATION"]


def _nonnegative(value: Fraction, name: str) -> None:
    if type(value) is not Fraction or value < 0:
        raise ValueError(f"{name} requires an exact nonnegative Fraction")


def _identifier(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} requires a nonempty stable identity")


@dataclass(frozen=True)
class StockGood:
    good_id: str
    unit: str
    initial_quantity: Fraction
    capacity: Fraction | None = None
    lead_time_weeks: int = 0

    def __post_init__(self) -> None:
        _identifier(self.good_id, "good_id")
        unit = normalize_unidade(self.unit)
        convert_physical(Fraction(1), unit, unit)
        object.__setattr__(self, "unit", unit)
        _nonnegative(self.initial_quantity, "initial_quantity")
        if self.capacity is not None:
            _nonnegative(self.capacity, "capacity")
            if self.initial_quantity > self.capacity:
                raise ValueError("initial stock exceeds declared storage capacity")
        if type(self.lead_time_weeks) is not int or self.lead_time_weeks < 0:
            raise ValueError("lead_time_weeks requires a nonnegative integer")


@dataclass(frozen=True)
class StockArrival:
    source_id: str
    good_id: str
    arrival_week: str
    quantity: Fraction
    unit: str
    source: StockSource
    ordered_week: str | None = None

    def __post_init__(self) -> None:
        for field in ("source_id", "good_id", "arrival_week", "unit"):
            _identifier(getattr(self, field), field)
        _nonnegative(self.quantity, "arrival quantity")
        if self.source not in ("EXTERNAL_DELIVERY", "INTERNAL_GENERATION"):
            raise ValueError("stock arrival requires typed physical source")
        if self.source == "EXTERNAL_DELIVERY":
            _identifier(self.ordered_week, "ordered_week")
        elif self.ordered_week is not None:
            raise ValueError("internal generation is not a purchase order")


@dataclass(frozen=True)
class StockWeek:
    good_id: str
    week: str
    opening: Fraction
    external_receipts: Fraction
    internal_generation: Fraction
    storage_overflow: Fraction
    physical_demand: Fraction
    fulfilled: Fraction
    shortage: Fraction
    closing: Fraction

    def __post_init__(self) -> None:
        for field in (
            "opening", "external_receipts", "internal_generation",
            "storage_overflow", "physical_demand", "fulfilled", "shortage", "closing",
        ):
            _nonnegative(getattr(self, field), field)
        if self.opening + self.external_receipts + self.internal_generation != (
            self.storage_overflow + self.fulfilled + self.closing
        ):
            raise ValueError("stock mass balance is not closed")
        if self.physical_demand != self.fulfilled + self.shortage:
            raise ValueError("demand/shortage balance is not closed")


@dataclass(frozen=True)
class StockProjection:
    rows: tuple[StockWeek, ...]
    evidence_ids: tuple[str, ...]
    has_planned_demand: bool
    authority: str = "PHYSICAL_INVENTORY_PREVIEW_NOT_FINANCIAL_GO"

    @property
    def feasible(self) -> bool:
        return all(row.shortage == 0 for row in self.rows)

    @property
    def total_shortage(self) -> Fraction:
        return sum((row.shortage for row in self.rows), Fraction(0))

    @property
    def total_overflow(self) -> Fraction:
        return sum((row.storage_overflow for row in self.rows), Fraction(0))


def project_exact_weekly_stock(
    goods: Mapping[str, StockGood],
    calendar_weeks: Sequence[str],
    measured_consumption: Sequence[AcquisitionEvidenceLine],
    arrivals: Sequence[StockArrival] = (),
) -> StockProjection:
    """Project one audited ledger per good/week using exact physical quantities.

    End-of-week balance:
      S[j] = S[j-1] + external_receipts + internal_generation
             - discarded_overflow - fulfilled_demand
      requested = fulfilled + shortage.

    All arrivals are processed *before* demand and excess stock is explicitly
    discarded when a storage capacity applies, matching the base projection.
    A shortage is evidence of infeasibility (not a fictional negative stock).
    """
    weeks = tuple(calendar_weeks)
    if not weeks or any(not isinstance(w, str) or not w.strip() for w in weeks):
        raise ValueError("nonempty calendar with stable week identities required")
    if len(weeks) != len(set(weeks)):
        raise ValueError("calendar weeks cannot repeat")
    if tuple(sorted(weeks)) != weeks:
        raise ValueError("calendar weeks must be chronologically ordered")
    week_index = {week: i for i, week in enumerate(weeks)}

    if not goods:
        raise ValueError("physical inventory requires a declared good")
    for good_id, good in goods.items():
        if not isinstance(good, StockGood) or good_id != good.good_id:
            raise ValueError("stock good registry must match declared identity")

    demand: dict[tuple[str, str], Fraction] = {}
    receipts: dict[tuple[str, str], Fraction] = {}
    generation: dict[tuple[str, str], Fraction] = {}
    ids: set[str] = set()
    measured_kinds: dict[tuple[str, str, str], str] = {}
    planned = False

    def register(source_id: str, good_id: str, week: str) -> StockGood:
        _identifier(source_id, "source_id")
        if source_id in ids:
            raise ValueError(f"duplicate physical stock source: {source_id}")
        ids.add(source_id)
        if good_id not in goods or week not in week_index:
            raise ValueError("physical source refers to unknown good or calendar week")
        return goods[good_id]

    for line in measured_consumption:
        if not isinstance(line, AcquisitionEvidenceLine):
            raise ValueError("inventory demand requires P18-B physical evidence")
        good = register(line.source_id, line.measure.good_id, line.week)
        _identifier(line.activity_id, "activity_id")
        if line.kind not in ("PLANNED_CLOSED_SCOPE", "OBSERVED_OPERATION"):
            raise ValueError("consumption provenance must distinguish planned and observed")
        owner = (line.activity_id, good.good_id, line.week)
        previous_kind = measured_kinds.get(owner)
        if previous_kind is not None and previous_kind != line.kind:
            raise ValueError("planned and observed consumption cannot be double booked")
        measured_kinds[owner] = line.kind
        planned |= line.kind == "PLANNED_CLOSED_SCOPE"
        _nonnegative(line.measure.physical_quantity, "measured physical quantity")
        amount = convert_physical(
            line.measure.physical_quantity, line.measure.physical_unit, good.unit
        )
        key = (good.good_id, line.week)
        demand[key] = demand.get(key, Fraction(0)) + amount

    for arrival in arrivals:
        if not isinstance(arrival, StockArrival):
            raise ValueError("typed physical arrival required")
        good = register(arrival.source_id, arrival.good_id, arrival.arrival_week)
        amount = convert_physical(arrival.quantity, arrival.unit, good.unit)
        key = (good.good_id, arrival.arrival_week)
        if arrival.source == "EXTERNAL_DELIVERY":
            assert arrival.ordered_week is not None
            if arrival.ordered_week not in week_index:
                raise ValueError("order week outside declared horizon: use initial stock")
            if week_index[arrival.arrival_week] - week_index[arrival.ordered_week] < (
                good.lead_time_weeks
            ):
                raise ValueError("external delivery violates declared lead time")
            receipts[key] = receipts.get(key, Fraction(0)) + amount
        else:
            generation[key] = generation.get(key, Fraction(0)) + amount

    result: list[StockWeek] = []
    for good_id, good in sorted(goods.items()):
        stock = good.initial_quantity
        for week in weeks:
            key = (good_id, week)
            delivered = receipts.get(key, Fraction(0))
            generated = generation.get(key, Fraction(0))
            required = demand.get(key, Fraction(0))
            available = stock + delivered + generated
            overflow = max(Fraction(0), available - good.capacity) if (
                good.capacity is not None
            ) else Fraction(0)
            usable = available - overflow
            fulfilled = min(usable, required)
            shortage = required - fulfilled
            closing = usable - fulfilled
            result.append(StockWeek(
                good_id, week, stock, delivered, generated, overflow,
                required, fulfilled, shortage, closing,
            ))
            stock = closing

    return StockProjection(tuple(result), tuple(sorted(ids)), planned)
