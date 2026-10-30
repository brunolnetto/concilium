"""P18-A: physically dimensioned consumables and exact unit-price arithmetic.

Uses the single canonical unit registry in concilium.domain.units. A currency
rate per hour is NOT a material quantity per hour and can never be upgraded
to a measured stock unit by assuming kappa=1.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from concilium.domain.units import normalize_unidade

# Conversion factors into a base unit for each physical dimension.
# Counts, bags and lump-sum goods are intentionally different dimensions.
_DIMENSION: dict[str, tuple[str, Fraction]] = {
    "kg": ("mass", Fraction(1)),
    "t": ("mass", Fraction(1000)),
    "l": ("volume", Fraction(1)),
    "m³": ("volume", Fraction(1000)),
    "m": ("length", Fraction(1)),
    "km": ("length", Fraction(1000)),
    "m²": ("area", Fraction(1)),
    "h": ("time_hour", Fraction(1)),
    "mes": ("time_month", Fraction(1)),
    "unid": ("count", Fraction(1)),
    "sc": ("bag", Fraction(1)),
    "vb": ("lump_sum", Fraction(1)),
}


def _normalize_physical_unit(unit: str) -> str:
    """Normalize and validate a unit at every public model boundary."""
    if not isinstance(unit, str):
        raise ValueError("physical units must be explicitly declared")
    try:
        normalized = normalize_unidade(unit)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unsupported physical unit: {unit}") from exc
    if normalized not in _DIMENSION:
        raise ValueError(f"unsupported physical unit: {unit}")
    return normalized


def convert_physical(quantity: Fraction, from_unit: str, to_unit: str) -> Fraction:
    """Convert matching engineering dimensions, never mass↔volume by guess."""
    if type(quantity) is not Fraction:
        raise ValueError("physical quantity must be an exact Fraction")
    source = _normalize_physical_unit(from_unit)
    target = _normalize_physical_unit(to_unit)
    dim1, scale1 = _DIMENSION[source]
    dim2, scale2 = _DIMENSION[target]
    if dim1 != dim2:
        raise ValueError(f"incompatible physical dimensions: {source} vs {target}")
    return quantity * scale1 / scale2


class ConsumptionBasis(StrEnum):
    PER_DELIVERED_UNIT = "PER_DELIVERED_UNIT"
    PER_OPERATING_HOUR = "PER_OPERATING_HOUR"


@dataclass(frozen=True)
class PhysicalConsumptionRate:
    """Measured units of a good per one unit of delivered activity or hour."""

    good_id: str
    physical_rate: Fraction
    good_unit: str
    basis: ConsumptionBasis
    activity_unit: str | None = None

    def __post_init__(self) -> None:
        if not self.good_id.strip():
            raise ValueError("physical good identity is required")
        if type(self.physical_rate) is not Fraction or self.physical_rate < 0:
            raise ValueError("physical rate must be a nonnegative exact Fraction")
        unit = _normalize_physical_unit(self.good_unit)
        object.__setattr__(self, "good_unit", unit)
        if not isinstance(self.basis, ConsumptionBasis):
            raise ValueError("consumption basis must be explicit")
        if self.basis == ConsumptionBasis.PER_DELIVERED_UNIT:
            if not self.activity_unit:
                raise ValueError("delivered activity unit must be declared")
            activity_unit = _normalize_physical_unit(self.activity_unit)
            if activity_unit in {"h", "mes"}:
                raise ValueError("hourly rates require PER_OPERATING_HOUR")
            object.__setattr__(self, "activity_unit", activity_unit)
        elif self.activity_unit is not None:
            raise ValueError("hourly consumption must not invent an activity unit")


@dataclass(frozen=True)
class PhysicallyPricedGood:
    rate: PhysicalConsumptionRate
    price_per_unit: Fraction
    price_unit: str
    # Catalog adapters carry provenance into the acquisition evidence; pure
    # mathematical callers may omit it, but certification gates may not.
    price_source: str | None = None
    price_reference_date: str | None = None

    def __post_init__(self) -> None:
        if type(self.price_per_unit) is not Fraction or self.price_per_unit < 0:
            raise ValueError("price per physical unit must be an exact nonnegative Fraction")
        unit = _normalize_physical_unit(self.price_unit)
        convert_physical(Fraction(1), self.rate.good_unit, unit)
        if self.price_source is not None and (
            not isinstance(self.price_source, str) or not self.price_source.strip()
        ):
            raise ValueError("price source must be nonempty text when provided")
        if self.price_reference_date is not None and (
            not isinstance(self.price_reference_date, str) or not self.price_reference_date.strip()
        ):
            raise ValueError("price reference date must be nonempty text when provided")
        object.__setattr__(self, "price_unit", unit)

    def cost(
        self,
        *,
        delivered: Fraction | None = None,
        delivered_unit: str | None = None,
        operating_hours: Fraction | None = None,
    ) -> PhysicalPurchaseMeasure:
        """Calculate real U and price, without inferring hours from F(m) or Q."""
        basis = self.rate.basis
        if basis == ConsumptionBasis.PER_DELIVERED_UNIT:
            if type(delivered) is not Fraction or delivered < 0 or not delivered_unit:
                raise ValueError("delivered physical quantity and unit required")
            if operating_hours is not None:
                raise ValueError("hourly consumption must be a separate declaration")
            quantity_of_basis = convert_physical(
                delivered, delivered_unit, self.rate.activity_unit or ""
            )
        else:
            if type(operating_hours) is not Fraction or operating_hours < 0:
                raise ValueError("actual operating hours required for hourly consumption")
            if delivered is not None or delivered_unit is not None:
                raise ValueError("hourly consumption is not inferred from delivered output")
            quantity_of_basis = operating_hours

        physical_quantity = quantity_of_basis * self.rate.physical_rate
        billable_quantity = convert_physical(
            physical_quantity, self.rate.good_unit, self.price_unit
        )
        return PhysicalPurchaseMeasure(
            good_id=self.rate.good_id,
            physical_quantity=physical_quantity,
            physical_unit=self.rate.good_unit,
            priced_quantity=billable_quantity,
            price_unit=self.price_unit,
            exact_cost=billable_quantity * self.price_per_unit,
        )


@dataclass(frozen=True)
class PhysicalPurchaseMeasure:
    good_id: str
    physical_quantity: Fraction
    physical_unit: str
    priced_quantity: Fraction
    price_unit: str
    exact_cost: Fraction


@dataclass(frozen=True)
class LegacyHourlyMoneyProxy:
    """Unverified legacy R$/h signal, never a physical purchase record."""

    good_id: str
    currency_per_hour: Fraction
    evidence_status: str = "UNVERIFIED_LEGACY_MONETARY_PROXY"

    def __post_init__(self) -> None:
        if not isinstance(self.good_id, str) or not self.good_id.strip():
            raise ValueError("legacy proxy needs identity")
        if type(self.currency_per_hour) is not Fraction or self.currency_per_hour < 0:
            raise ValueError("legacy hourly money must be a nonnegative exact Fraction")
