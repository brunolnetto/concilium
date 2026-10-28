"""P18-B: physical Q/h evidence -> unique consumable V postings (not legacy money).

Converts the typed P18-A rate/priced-good contract into the P17-A financial
purchase boundary. A planned measurement is never silently labelled observed.
This module does not infer hours from F(m) or accept monetary proxies as U_g.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from .contractual_cost_ledger import (
    ExclusiveCostLedger,
    PhysicalPurchase,
    attach_physical_purchases,
)
from .physical_consumption_rates import (
    ConsumptionBasis,
    PhysicallyPricedGood,
    PhysicalPurchaseMeasure,
)

EvidenceKind = Literal["PLANNED_CLOSED_SCOPE", "OBSERVED_OPERATION"]


@dataclass(frozen=True)
class WeeklyConsumptionEvidence:
    evidence_id: str
    activity_id: str
    good_id: str
    week: str
    basis: ConsumptionBasis
    kind: EvidenceKind
    delivered_quantity: Fraction | None = None
    delivered_unit: str | None = None
    operating_hours: Fraction | None = None

    def __post_init__(self) -> None:
        for name in ("evidence_id", "activity_id", "good_id", "week"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}: stable physical source is required")
        if self.kind not in ("PLANNED_CLOSED_SCOPE", "OBSERVED_OPERATION"):
            raise ValueError("physical evidence kind must be explicit")
        if not isinstance(self.basis, ConsumptionBasis):
            raise ValueError("physical consumption basis must be typed")
        if self.basis == ConsumptionBasis.PER_DELIVERED_UNIT:
            if (type(self.delivered_quantity) is not Fraction
                    or self.delivered_quantity < 0 or not self.delivered_unit):
                raise ValueError("delivered Q and its physical unit are required")
            if self.operating_hours is not None:
                raise ValueError("output-scaled consumption cannot also charge operating hours")
        else:
            if type(self.operating_hours) is not Fraction or self.operating_hours < 0:
                raise ValueError("actual/declared operating hours required")
            if self.delivered_quantity is not None or self.delivered_unit is not None:
                raise ValueError("hourly consumption cannot be inferred from Q")


@dataclass(frozen=True)
class AcquisitionEvidenceLine:
    source_id: str
    kind: EvidenceKind
    activity_id: str
    week: str
    measure: PhysicalPurchaseMeasure
    # Optional only for existing external stock-evidence constructors. P20
    # reconciliation fails closed unless P18 supplies the declared category.
    category: Literal["MAT", "COMB"] | None = None


@dataclass(frozen=True)
class PhysicalConsumptionJournalResult:
    journal: ExclusiveCostLedger
    evidence: tuple[AcquisitionEvidenceLine, ...]
    authority: str = "PHYSICAL_CONSUMPTION_EVIDENCE_NOT_PROJECT_GO"

    @property
    def variable_cost(self) -> Fraction:
        return self.journal.consumable_v


def book_weekly_physical_consumption(
    base_ledger: ExclusiveCostLedger,
    goods: Mapping[str | tuple[str, str], tuple[PhysicallyPricedGood, Literal["MAT", "COMB"]]],
    evidence: Sequence[WeeklyConsumptionEvidence],
) -> PhysicalConsumptionJournalResult:
    """Apply explicit U_g,j * p_g, maintaining identical ownership in P17-A.

    Does not certify a physical schedule, acquisition invoice, or overall
    financial GO: P17-C/P20/P23 remain independent gates.
    """
    ids: set[str] = set()
    measurements: list[AcquisitionEvidenceLine] = []
    purchases: list[PhysicalPurchase] = []
    for item in evidence:
        if not isinstance(item, WeeklyConsumptionEvidence):
            raise ValueError("typed weekly physical evidence required")
        if item.evidence_id in ids:
            raise ValueError("duplicate physical evidence identity")
        ids.add(item.evidence_id)
        # Activity-specific rates are allowed for a shared catalog good:
        # the same diesel can have different L/h per CPU. Preserve the old
        # good_id-only contract for callers that already provide one shared rate.
        declaration = goods.get((item.activity_id, item.good_id))
        if declaration is None:
            declaration = goods.get(item.good_id)
        if declaration is None:
            raise ValueError(
                f"{item.activity_id}/{item.good_id}: missing priced physical good"
            )
        priced, category = declaration
        if not isinstance(priced, PhysicallyPricedGood) or category not in ("MAT", "COMB"):
            raise ValueError("physical good requires explicit MAT/COMB price category")
        if priced.rate.good_id != item.good_id or priced.rate.basis != item.basis:
            raise ValueError("physical good identity/basis is incompatible with evidence")
        if item.basis == ConsumptionBasis.PER_DELIVERED_UNIT:
            assert item.delivered_quantity is not None
            measured = priced.cost(
                delivered=item.delivered_quantity, delivered_unit=item.delivered_unit
            )
        else:
            assert item.operating_hours is not None
            measured = priced.cost(operating_hours=item.operating_hours)
        measurements.append(AcquisitionEvidenceLine(
            item.evidence_id, item.kind, item.activity_id, item.week, measured,
            category,
        ))
        if measured.priced_quantity > 0:
            purchases.append(PhysicalPurchase(
                evidence_id=item.evidence_id,
                activity_id=item.activity_id,
                good_id=item.good_id,
                week=item.week,
                quantity=measured.priced_quantity,
                physical_unit=measured.price_unit,
                unit_price=priced.price_per_unit,
                category=category,
            ))
    journal = attach_physical_purchases(base_ledger, purchases)
    return PhysicalConsumptionJournalResult(journal=journal, evidence=tuple(measurements))
