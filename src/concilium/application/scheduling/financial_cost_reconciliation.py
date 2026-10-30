"""P20-A: reconcile exclusive P17/P18/P19 snapshots without reposting costs.

A later snapshot must be the unchanged earlier ledger plus precisely the
events justified by physical consumption, external-stock purchase, and holding evidence.
This is not the Skill 06 financial authority, a BDI engine or a GO decision.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING, Literal

from .contractual_cost_ledger import CostPosting, ExclusiveCostLedger, PostingNature
from .physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from .physical_consumption_rates import PhysicalPurchaseMeasure, convert_physical
from .physical_stock_holding import HoldingJournal
from .physical_stock_ledger import StockArrival, project_exact_weekly_stock
from .physical_stock_provisioning import (
    ExternalStockProvisioningJournal,
    ExternalStockPurchase,
)

if TYPE_CHECKING:
    from concilium.domain.models.canonical import DistribuicaoSemanal

    from .realized_financial_metrics import RealizedFinancialProjection

EventId = tuple[str, ...]
_POOL_NATURES = frozenset({
    PostingNature.ACTIVE, PostingNature.IDLE,
    PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION,
})


@dataclass(frozen=True)
class WeekFinancialBalance:
    week: str
    contractual_k: Fraction
    consumable_v: Fraction
    indirect: Fraction

    @property
    def direct(self) -> Fraction:
        return self.contractual_k + self.consumable_v

    @property
    def total(self) -> Fraction:
        return self.direct + self.indirect


@dataclass(frozen=True)
class FinancialEventAttribution:
    """One existing posting with explicit ownership scope; never a new cost."""

    event_id: EventId
    nature: PostingNature
    category: str
    amount: Fraction
    source: str
    week: str
    owner_scope: Literal["ACTIVITY", "INSTANCE", "GOOD", "SOURCE"]
    owner_id: tuple[str, ...]
    activity_id: str | None = None


@dataclass(frozen=True)
class WeeklyCategoryBalance:
    """Exact pre-BDI project cost by ISO week and exclusive ledger category."""

    week: str
    category: str
    amount: Fraction


@dataclass(frozen=True)
class ActivityAttributableConsumableCost:
    """Only P18 consumables with explicit activity evidence; never allocated K."""

    activity_id: str
    week: str
    category: str
    amount: Fraction


@dataclass(frozen=True)
class ExactFinancialReconciliation:
    """Immutable projection of one authoritative event set, never new costs."""

    ledger: ExclusiveCostLedger
    weeks: tuple[WeekFinancialBalance, ...]
    holding_evidence_present: bool
    authority: str = "FINANCIAL_SOURCES_RECONCILED_PREVIEW_NOT_PROJECT_GO"
    event_attribution: tuple[FinancialEventAttribution, ...] = ()
    category_balances: tuple[WeeklyCategoryBalance, ...] = ()
    activity_attributable_consumables: tuple[ActivityAttributableConsumableCost, ...] = ()

    @property
    def direct(self) -> Fraction:
        return self.ledger.direct

    @property
    def indirect(self) -> Fraction:
        return self.ledger.indirect

    @property
    def total(self) -> Fraction:
        return self.ledger.total

    def project_skill04_realization(
        self,
        *,
        distributions_by_activity: Mapping[str, Mapping[str, DistribuicaoSemanal]],
        scopes_by_activity: Mapping[str, int | float | str | Fraction],
        bdi_by_category: Mapping[str, Fraction],
        independent_variable_unit_rate: Fraction | None = None,
    ) -> RealizedFinancialProjection:
        """Attach P11-B read-only metrics to the *real* P20 ledger snapshot.

        No new monetary rows are created. A post-hoc or forged weekly P20
        balance cannot silently disagree with source event identities. This
        operation does not issue GO or attribute shared K to individual items.
        """
        from .realized_financial_metrics import project_realized_financials

        result = project_realized_financials(
            distributions_by_activity=distributions_by_activity,
            scopes_by_activity=scopes_by_activity,
            ledger=self.ledger,
            bdi_by_category=bdi_by_category,
            independent_variable_unit_rate=independent_variable_unit_rate,
        )
        projected = {week.week: week for week in result.weeks}
        existing = {week.week: week for week in self.weeks}
        if len(existing) != len(self.weeks) or not set(existing).issubset(projected):
            raise ValueError("P20 week provenance must match physical/financial projection")
        if any(
            week not in existing and (
                row.contractual_k or row.physically_purchased_v or row.indirect
            )
            for week, row in projected.items()
        ):
            raise ValueError("unattributed financial events in physical-only week")
        if any(
            (
                source.contractual_k,
                source.consumable_v,
                source.indirect,
            ) != (
                projected[week].contractual_k,
                projected[week].physically_purchased_v,
                projected[week].indirect,
            )
            for week, source in existing.items()
        ):
            raise ValueError("P20 weekly financial balance does not reconcile")
        return result


def _events(lines: Iterable[CostPosting]) -> dict[EventId, CostPosting]:
    indexed: dict[EventId, CostPosting] = {}
    for line in lines:
        if not isinstance(line, CostPosting):
            raise ValueError("financial reconciliation requires typed cost postings")
        if line.event_id in indexed:
            raise ValueError("duplicate financial ownership")
        indexed[line.event_id] = line
    return indexed


def _delta(
    before: ExclusiveCostLedger,
    after: ExclusiveCostLedger,
    expected: dict[EventId, CostPosting],
    stage: str,
) -> None:
    """Compare event identities and *whole* immutable rows, not only sums."""
    if before.contract_scope != after.contract_scope:
        raise ValueError(f"{stage}: contractual source scope changed")
    previous = _events(before.postings)
    actual = _events(after.postings)
    if any(actual.get(event_id) != row for event_id, row in previous.items()):
        raise ValueError(f"{stage}: prior financial posting removed or modified")
    additions = {event_id: row for event_id, row in actual.items() if event_id not in previous}
    if additions != expected:
        raise ValueError(f"{stage}: missing, forged or modified physical-cost evidence")


def _acquisition_expectations(
    result: PhysicalConsumptionJournalResult,
) -> dict[EventId, CostPosting]:
    expected: dict[EventId, CostPosting] = {}
    # Build the authoritative index once; O(events + evidence), not a linear
    # scan of all journal rows for every physical consumption measurement.
    postings = _events(result.journal.postings)
    seen: set[str] = set()
    kinds: dict[tuple[str, str, str], str] = {}
    for evidence in result.evidence:
        if not isinstance(evidence.source_id, str) or not evidence.source_id.strip():
            raise ValueError("stable acquisition evidence identity required")
        if evidence.source_id in seen:
            raise ValueError("duplicate acquisition evidence")
        seen.add(evidence.source_id)
        if evidence.kind not in ("PLANNED_CLOSED_SCOPE", "OBSERVED_OPERATION"):
            raise ValueError("physical consumption evidence kind must be explicit")
        owner = (evidence.activity_id, evidence.measure.good_id, evidence.week)
        previous_kind = kinds.get(owner)
        if previous_kind is not None and previous_kind != evidence.kind:
            raise ValueError("planned and observed physical cost cannot both be booked")
        kinds[owner] = evidence.kind
        measure = evidence.measure
        if evidence.category not in ("MAT", "COMB"):
            raise ValueError("acquisition evidence lacks declared MAT/COMB category")
        if (type(measure.priced_quantity) is not Fraction or measure.priced_quantity < 0
                or type(measure.exact_cost) is not Fraction or measure.exact_cost < 0):
            raise ValueError("physical acquisition requires exact nonnegative evidence")
        if measure.priced_quantity == 0 and measure.exact_cost != 0:
            raise ValueError("zero physical purchase cannot incur a fabricated cost")
        event_id = ("CONSUMABLE", evidence.source_id)
        if event_id in expected:
            raise ValueError("duplicate acquisition evidence")
        if measure.priced_quantity == 0:
            continue
        # The P18 source carries the declared classification. Never learn the
        # expected category from the financial row under audit.
        actual = postings.get(event_id)
        if (actual is None or actual.nature != PostingNature.ACQUISITION
                or actual.category != evidence.category
                or actual.source != measure.good_id or actual.week != evidence.week
                or actual.amount != measure.exact_cost):
            raise ValueError("acquisition posting differs from measured physical cost")
        expected[event_id] = actual
    return expected


def _holding_expectations(result: HoldingJournal) -> dict[EventId, CostPosting]:
    expected: dict[EventId, CostPosting] = {}
    for charge in result.charges:
        if type(charge.holding_cost) is not Fraction or charge.holding_cost < 0:
            raise ValueError("stock holding requires exact nonnegative financial evidence")
        event_id = ("STOCK_HOLDING", charge.good_id, charge.week)
        if event_id in expected:
            raise ValueError("duplicate stock holding evidence")
        if charge.holding_cost == 0:
            continue
        expected[event_id] = CostPosting(
            event_id, PostingNature.HOLDING, "IND", charge.holding_cost,
            f"PHYSICAL_STOCK:{charge.good_id}", charge.week,
        )
    return expected


def _external_stock_expectations(
    provisioning: ExternalStockProvisioningJournal,
    consumption: PhysicalConsumptionJournalResult,
) -> dict[EventId, CostPosting]:
    """Rebuild P19 acquisition expectations and independently replay its stock proof."""
    if provisioning.base_consumption != consumption:
        raise ValueError("P19 external provisioning base differs from P18 consumption evidence")
    if provisioning.currency_source != "catalog_metadata.json":
        raise ValueError("P19 external provisioning currency source is not catalog metadata")
    if (
        not isinstance(provisioning.currency, str)
        or len(provisioning.currency) != 3
        or not provisioning.currency.isalpha()
        or not provisioning.currency.isascii()
        or provisioning.currency != provisioning.currency.upper()
    ):
        raise ValueError("P19 external provisioning currency is invalid")

    goods = dict(provisioning.goods)
    if len(goods) != len(provisioning.goods):
        raise ValueError("P19 stock-good registry contains duplicate identities")
    if len(provisioning.purchases) != len(provisioning.purchase_evidence):
        raise ValueError("P19 purchase and price-evidence counts differ")

    expected: dict[EventId, CostPosting] = {}
    seen: set[str] = set()
    expected_receipts: list[StockArrival] = []
    for purchase, evidence in zip(
        provisioning.purchases, provisioning.purchase_evidence, strict=True,
    ):
        if not isinstance(purchase, ExternalStockPurchase):
            raise ValueError("P19 requires typed external purchase evidence")
        if purchase.source_id in seen:
            raise ValueError("P19 duplicate external purchase source identity")
        seen.add(purchase.source_id)
        if purchase.currency != provisioning.currency:
            raise ValueError("P19 external purchase currency differs from journal currency")
        if purchase.good_id not in goods:
            raise ValueError("P19 external purchase references an unknown stock good")
        for line in consumption.evidence:
            if line.measure.good_id == purchase.good_id:
                if (
                    type(line.measure.exact_cost) is not Fraction
                    or line.measure.exact_cost < 0
                ):
                    raise ValueError("P18 cost evidence must be exact and nonnegative")
                if line.measure.exact_cost > 0:
                    raise ValueError(
                        "P18 already owns priced consumption for this good; "
                        "P19 external acquisition would double count"
                    )
        if type(purchase.unit_price) is not Fraction or not isinstance(purchase.price_unit, str):
            raise ValueError("P19 external purchase price is incomplete")

        priced_quantity = convert_physical(
            purchase.quantity, purchase.physical_unit, purchase.price_unit,
        )
        amount = priced_quantity * purchase.unit_price
        event_id = ("CONSUMABLE", f"EXTERNAL_PROVISION:{purchase.source_id}")
        expected_evidence = AcquisitionEvidenceLine(
            source_id=event_id[1],
            kind="PLANNED_CLOSED_SCOPE",
            activity_id=f"EXTERNAL_STOCK_PROVISION:{purchase.source_id}",
            week=purchase.arrival_week,
            measure=PhysicalPurchaseMeasure(
                good_id=purchase.good_id,
                physical_quantity=purchase.quantity,
                physical_unit=purchase.physical_unit,
                priced_quantity=priced_quantity,
                price_unit=purchase.price_unit,
                exact_cost=amount,
            ),
            category=purchase.category,
            price_source=purchase.price_source,
            price_reference_date=purchase.price_reference_date,
        )
        if evidence != expected_evidence:
            raise ValueError("P19 external purchase evidence differs from declared purchase")
        if event_id in expected:
            raise ValueError("P19 duplicate external acquisition identity")
        expected[event_id] = CostPosting(
            event_id,
            PostingNature.ACQUISITION,
            purchase.category,
            amount,
            purchase.good_id,
            purchase.arrival_week,
        )
        expected_receipts.append(StockArrival(
            source_id=f"EXTERNAL_RECEIPT:{purchase.source_id}",
            good_id=purchase.good_id,
            arrival_week=purchase.arrival_week,
            quantity=purchase.quantity,
            unit=purchase.physical_unit,
            source="EXTERNAL_DELIVERY",
            ordered_week=purchase.ordered_week,
        ))

    if any(receipt not in provisioning.arrivals for receipt in expected_receipts):
        raise ValueError("P19 external stock receipt does not match purchase provenance")
    if any(
        arrival.source == "EXTERNAL_DELIVERY" and arrival not in expected_receipts
        for arrival in provisioning.arrivals
    ):
        raise ValueError("P19 external delivery lacks matched priced purchase evidence")
    replayed_stock = project_exact_weekly_stock(
        goods,
        provisioning.calendar_weeks,
        consumption.evidence,
        provisioning.arrivals,
    )
    if not replayed_stock.feasible:
        raise ValueError("P19 external provisioning contains unresolved physical stockout")
    if replayed_stock != provisioning.stock:
        raise ValueError("P19 external stock projection does not reconcile to its inputs")
    return expected


def _ownership_projection(
    ledger: ExclusiveCostLedger,
    consumption: PhysicalConsumptionJournalResult,
) -> tuple[
    tuple[FinancialEventAttribution, ...],
    tuple[WeeklyCategoryBalance, ...],
    tuple[ActivityAttributableConsumableCost, ...],
]:
    """Expose source ownership without distributing shared costs by guess."""
    activity_by_event = {
        ("CONSUMABLE", evidence.source_id): evidence.activity_id
        for evidence in consumption.evidence
        if evidence.measure.priced_quantity > 0
    }
    trace: list[FinancialEventAttribution] = []
    category_amounts: dict[tuple[str, str], Fraction] = {}
    activity_amounts: dict[tuple[str, str, str], Fraction] = {}
    for row in ledger.postings:
        if not isinstance(row.week, str) or not row.week.strip():
            raise ValueError("financial attribution requires explicit weekly provenance")
        activity_id = activity_by_event.get(row.event_id)
        if activity_id is not None:
            scope: Literal["ACTIVITY", "INSTANCE", "GOOD", "SOURCE"] = "ACTIVITY"
            owner_id = (activity_id,)
            if row.nature != PostingNature.ACQUISITION or row.category not in ("MAT", "COMB"):
                raise ValueError("activity ownership is only valid for typed P18 consumable acquisition")
            key = (activity_id, row.week, row.category)
            activity_amounts[key] = activity_amounts.get(key, Fraction(0)) + row.amount
        elif row.nature in (
            PostingNature.ACTIVE, PostingNature.IDLE,
            PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION,
        ):
            scope = "INSTANCE"
            owner_id = row.event_id[1:5] if row.event_id[:1] == ("POOL",) else (row.source,)
        elif row.nature in (PostingNature.ACQUISITION, PostingNature.HOLDING):
            scope = "GOOD"
            good_id = (
                row.source.removeprefix("PHYSICAL_STOCK:")
                if row.nature == PostingNature.HOLDING
                else row.source
            )
            if not good_id.strip():
                raise ValueError("P20 stock ownership requires an explicit good ID")
            owner_id = (good_id,)
        else:
            scope = "SOURCE"
            owner_id = (row.source,)
        trace.append(FinancialEventAttribution(
            event_id=row.event_id,
            nature=row.nature,
            category=row.category,
            amount=row.amount,
            source=row.source,
            week=row.week,
            owner_scope=scope,
            owner_id=owner_id,
            activity_id=activity_id,
        ))
        category_key = (row.week, row.category)
        category_amounts[category_key] = category_amounts.get(category_key, Fraction(0)) + row.amount

    if sum((line.amount for line in trace), Fraction(0)) != ledger.total:
        raise ValueError("P20 event attribution does not conserve the project ledger")
    category_balances = tuple(
        WeeklyCategoryBalance(week, category, amount)
        for (week, category), amount in sorted(category_amounts.items())
    )
    if sum((line.amount for line in category_balances), Fraction(0)) != ledger.total:
        raise ValueError("P20 category balance does not conserve the project ledger")
    activity_costs = tuple(
        ActivityAttributableConsumableCost(activity, week, category, amount)
        for (activity, week, category), amount in sorted(activity_amounts.items())
    )
    if sum((line.amount for line in activity_costs), Fraction(0)) > ledger.consumable_v:
        raise ValueError("P20 activity-attributable consumables exceed project acquisitions")
    return tuple(trace), category_balances, activity_costs


def reconcile_financial_sources(
    pool: ExclusiveCostLedger,
    consumption: PhysicalConsumptionJournalResult,
    holding: HoldingJournal | None = None,
    stock_provisioning: ExternalStockProvisioningJournal | None = None,
) -> ExactFinancialReconciliation:
    """Reconcile P17 pool → P18 usage → optional P19 external purchases/holding.

    Evidence is checked by source identity and exact value, making equal
    aggregate totals insufficient to conceal omitted, shifted or forged costs.
    No implicit zero-priced purchases, BDI assumptions or Skill06 projection.
    """
    if not isinstance(pool, ExclusiveCostLedger):
        raise ValueError("P17 exact physical pool ledger required")
    if not isinstance(consumption, PhysicalConsumptionJournalResult):
        raise ValueError("P18 typed consumption journal required")
    if holding is not None and not isinstance(holding, HoldingJournal):
        raise ValueError("P19 typed holding journal required")
    if stock_provisioning is not None and not isinstance(
        stock_provisioning, ExternalStockProvisioningJournal
    ):
        raise ValueError("P19 typed external stock provisioning journal required")
    if any(row.nature not in _POOL_NATURES for row in pool.postings):
        raise ValueError("P17 pool input cannot already contain variable or holding costs")

    acquired = _acquisition_expectations(consumption)
    _delta(pool, consumption.journal, acquired, "P18 acquisitions")
    final = consumption.journal
    if stock_provisioning is not None:
        external_acquisitions = _external_stock_expectations(
            stock_provisioning, consumption,
        )
        _delta(
            final,
            stock_provisioning.ledger,
            external_acquisitions,
            "P19 external stock acquisition",
        )
        final = stock_provisioning.ledger
    if holding is not None:
        _delta(final, holding.ledger, _holding_expectations(holding), "P19 holding")
        final = holding.ledger

    buckets: dict[str, list[Fraction]] = {}
    for row in final.postings:
        if not isinstance(row.week, str) or not row.week.strip():
            raise ValueError("financial reconciliation requires explicit weekly provenance")
        values = buckets.setdefault(row.week, [Fraction(0), Fraction(0), Fraction(0)])
        if row.nature in (PostingNature.ACTIVE, PostingNature.IDLE):
            if row.category not in ("MO", "EQ"):
                raise ValueError("contractual K was misclassified")
            values[0] += row.amount
        elif row.nature == PostingNature.ACQUISITION:
            if row.category not in ("MAT", "COMB"):
                raise ValueError("physical V was misclassified")
            values[1] += row.amount
        else:
            if row.category != "IND":
                raise ValueError("indirect charge was booked as direct")
            values[2] += row.amount

    weeks = tuple(
        WeekFinancialBalance(week, buckets[week][0], buckets[week][1], buckets[week][2])
        for week in sorted(buckets)
    )
    if (
        sum((w.contractual_k for w in weeks), Fraction(0)) != final.contractual_k
        or sum((w.consumable_v for w in weeks), Fraction(0)) != final.consumable_v
        or sum((w.indirect for w in weeks), Fraction(0)) != final.indirect
        or sum((w.total for w in weeks), Fraction(0)) != final.total
    ):
        raise ValueError("P20 financial cost-account identity failed")
    event_attribution, category_balances, activity_costs = _ownership_projection(
        final, consumption,
    )
    return ExactFinancialReconciliation(
        final,
        weeks,
        holding is not None,
        event_attribution=event_attribution,
        category_balances=category_balances,
        activity_attributable_consumables=activity_costs,
    )
