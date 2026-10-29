"""P19-C: priced external stock receipts with exact physical provenance.

An externally provisioned shortage has two distinct facts: a physical receipt
that can close inventory, and a priced acquisition that belongs to V. Neither
fact is inferred from the other. This adapter is a preview, never PROJECT_GO.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Literal

from concilium.domain.units import normalize_unidade

from .contractual_cost_ledger import (
    ExclusiveCostLedger,
    PhysicalPurchase,
    attach_physical_purchases,
)
from .physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from .physical_consumption_rates import PhysicalPurchaseMeasure, convert_physical
from .physical_stock_ledger import (
    StockArrival,
    StockGood,
    StockProjection,
    project_exact_weekly_stock,
)

_PRICE_CURRENCY_SOURCE = "catalog_metadata.json"
StockCategory = Literal["MAT", "COMB"]


def _required_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} requires explicit nonempty provenance")


@dataclass(frozen=True)
class ExternalStockPurchase:
    """One independently identified, dimensioned and priced external purchase.

    A zero unit price is permitted only as an explicit exact value with source
    and reference date. Missing price is not equivalent to an explicit zero.
    The record describes planned provisioning; it is not an invoice or proof of
    an observed delivery.
    """

    source_id: str
    good_id: str
    ordered_week: str
    arrival_week: str
    quantity: Fraction
    physical_unit: str
    unit_price: Fraction | None
    price_unit: str | None
    price_source: str | None
    price_reference_date: str | None
    currency: str | None
    category: StockCategory = "MAT"

    def __post_init__(self) -> None:
        for name in ("source_id", "good_id", "ordered_week", "arrival_week"):
            _required_text(getattr(self, name), name)
        if type(self.quantity) is not Fraction or self.quantity <= 0:
            raise ValueError("external purchase quantity must be an exact positive Fraction")
        if not isinstance(self.physical_unit, str) or not self.physical_unit.strip():
            raise ValueError("external purchase physical unit is required")
        physical_unit = normalize_unidade(self.physical_unit)
        object.__setattr__(self, "physical_unit", physical_unit)
        if type(self.unit_price) is not Fraction or self.unit_price < 0:
            raise ValueError("external purchase requires an explicit exact nonnegative unit price")
        if not isinstance(self.price_unit, str) or not self.price_unit.strip():
            raise ValueError("external purchase price unit is required")
        price_unit = normalize_unidade(self.price_unit)
        convert_physical(Fraction(1), physical_unit, price_unit)
        object.__setattr__(self, "price_unit", price_unit)
        _required_text(self.price_source, "price source")
        _required_text(self.price_reference_date, "price reference date")
        try:
            parsed_date = date.fromisoformat(self.price_reference_date or "")
        except ValueError as exc:
            raise ValueError("price reference date must be canonical YYYY-MM-DD") from exc
        if parsed_date.isoformat() != self.price_reference_date:
            raise ValueError("price reference date must be canonical YYYY-MM-DD")
        if (
            not isinstance(self.currency, str)
            or len(self.currency) != 3
            or not self.currency.isalpha()
            or self.currency != self.currency.upper()
        ):
            raise ValueError("external purchase currency must be an explicit uppercase 3-letter code")
        if self.category not in ("MAT", "COMB"):
            raise ValueError("external stock acquisition must be categorized as MAT or COMB")


@dataclass(frozen=True)
class ExternalStockProvisioningJournal:
    """The priced acquisition journal and the independent physical stock proof."""

    consumption: PhysicalConsumptionJournalResult
    stock: StockProjection
    arrivals: tuple[StockArrival, ...]
    purchase_evidence: tuple[AcquisitionEvidenceLine, ...]
    currency: str
    currency_source: str
    authority: str = "EXTERNAL_STOCK_PROVISIONING_PREVIEW_NOT_PROJECT_GO"

    @property
    def external_cost(self) -> Fraction:
        return sum(
            (line.measure.exact_cost for line in self.purchase_evidence),
            start=Fraction(0),
        )


def book_external_stock_provisioning(
    base: PhysicalConsumptionJournalResult,
    goods: Mapping[str, StockGood],
    calendar_weeks: Sequence[str],
    purchases: Sequence[ExternalStockPurchase],
    *,
    financial_currency: str,
    currency_source: str,
    other_arrivals: Sequence[StockArrival] = (),
) -> ExternalStockProvisioningJournal:
    """Validate and post explicit external provisioning without fabricating stock.

    The declared currency must come from P18-C3's verified catalog metadata
    contract. Each purchase must declare that currency. Each row creates a
    unique priced MAT/COMB acquisition and a separately identified receipt.
    Stockout, incompatible units, late deliveries, duplicate identities, and
    incomplete price provenance fail closed. Evidence remains a preview.
    """
    if not isinstance(base, PhysicalConsumptionJournalResult):
        raise ValueError("typed P18 physical consumption evidence is required")
    if not isinstance(base.journal, ExclusiveCostLedger):
        raise ValueError("exclusive P17/P18 financial ledger is required")
    if (
        not isinstance(financial_currency, str)
        or len(financial_currency) != 3
        or not financial_currency.isalpha()
        or financial_currency != financial_currency.upper()
    ):
        raise ValueError("financial currency must be an explicit uppercase 3-letter code")
    if currency_source != _PRICE_CURRENCY_SOURCE:
        raise ValueError("currency must be sourced from verified catalog_metadata.json")
    if not purchases:
        raise ValueError("at least one explicit external stock purchase is required")

    existing_ids = {line.source_id for line in base.evidence}
    purchase_ids: set[str] = set()
    additional_evidence: list[AcquisitionEvidenceLine] = []
    physical_purchases: list[PhysicalPurchase] = []
    external_arrivals: list[StockArrival] = []

    for purchase in purchases:
        if not isinstance(purchase, ExternalStockPurchase):
            raise ValueError("typed external purchase evidence is required")
        if purchase.source_id in purchase_ids:
            raise ValueError("duplicate external purchase source identity")
        purchase_ids.add(purchase.source_id)
        if purchase.currency != financial_currency:
            raise ValueError("external purchase currency differs from verified financial currency")

        evidence_id = f"EXTERNAL_PROVISION:{purchase.source_id}"
        arrival_id = f"EXTERNAL_RECEIPT:{purchase.source_id}"
        if evidence_id in existing_ids or arrival_id in existing_ids:
            raise ValueError("external purchase identity collides with existing physical evidence")
        if purchase.good_id not in goods:
            raise ValueError(f"external purchase references unknown stock good: {purchase.good_id}")

        unit_price = purchase.unit_price
        price_unit = purchase.price_unit
        assert type(unit_price) is Fraction
        assert isinstance(price_unit, str)
        billable_quantity = convert_physical(
            purchase.quantity, purchase.physical_unit, price_unit
        )
        cost = billable_quantity * unit_price
        measure = PhysicalPurchaseMeasure(
            good_id=purchase.good_id,
            physical_quantity=purchase.quantity,
            physical_unit=purchase.physical_unit,
            priced_quantity=billable_quantity,
            price_unit=price_unit,
            exact_cost=cost,
        )
        activity_id = f"EXTERNAL_STOCK_PROVISION:{purchase.source_id}"
        evidence = AcquisitionEvidenceLine(
            source_id=evidence_id,
            kind="PLANNED_CLOSED_SCOPE",
            activity_id=activity_id,
            week=purchase.arrival_week,
            measure=measure,
            category=purchase.category,
            price_source=purchase.price_source,
            price_reference_date=purchase.price_reference_date,
        )
        additional_evidence.append(evidence)
        physical_purchases.append(PhysicalPurchase(
            evidence_id=evidence_id,
            activity_id=activity_id,
            good_id=purchase.good_id,
            week=purchase.arrival_week,
            quantity=billable_quantity,
            physical_unit=price_unit,
            unit_price=unit_price,
            category=purchase.category,
        ))
        external_arrivals.append(StockArrival(
            source_id=arrival_id,
            good_id=purchase.good_id,
            arrival_week=purchase.arrival_week,
            quantity=purchase.quantity,
            unit=purchase.physical_unit,
            source="EXTERNAL_DELIVERY",
            ordered_week=purchase.ordered_week,
        ))

    updated_ledger = attach_physical_purchases(base.journal, physical_purchases)
    updated_consumption = PhysicalConsumptionJournalResult(
        journal=updated_ledger,
        evidence=base.evidence + tuple(additional_evidence),
    )
    all_arrivals = tuple(other_arrivals) + tuple(external_arrivals)

    # Demand uses only the pre-existing physical evidence. Added purchase rows
    # are receipts, not a second copy of physical demand.
    stock = project_exact_weekly_stock(
        goods, calendar_weeks, base.evidence, all_arrivals,
    )
    if not stock.feasible:
        raise ValueError("external provisioning leaves an unresolved physical stockout")

    return ExternalStockProvisioningJournal(
        consumption=updated_consumption,
        stock=stock,
        arrivals=all_arrivals,
        purchase_evidence=tuple(additional_evidence),
        currency=financial_currency,
        currency_source=currency_source,
    )
