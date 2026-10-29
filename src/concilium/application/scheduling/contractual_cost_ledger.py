"""P17-A: exclusive, exact financial postings from fixed physical pool evidence.

The P16 optimizer knows physical demand, weekly presence, idle, and contractual
movements. It does NOT know whether a resource type is MO or EQ; this must be
declared explicitly. MAT/COMB cannot be booked as contractual pool presence.

This is an additive, strict adapter; Skill 05/06 consumers migrate in P17-B/C.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Literal

from .resource_level_contracts import ExactPoolResult, ResourceTariff

ContractCategory = Literal["MO", "EQ"]
ConsumableCategory = Literal["MAT", "COMB"]


class PostingNature(StrEnum):
    ACTIVE = "CONTRACTUAL_ACTIVE"
    IDLE = "CONTRACTUAL_IDLE"
    MOBILIZATION = "MOBILIZATION_EVENT"
    DEMOBILIZATION = "DEMOBILIZATION_EVENT"
    ACQUISITION = "CONSUMABLE_ACQUISITION"
    INDIRECT = "INDIRECT"
    HOLDING = "INVENTORY_HOLDING"


@dataclass(frozen=True)
class CostPosting:
    """One uniquely owned monetary fact, never a projection of the same fact."""

    event_id: tuple[str, ...]
    nature: PostingNature
    category: Literal["MO", "EQ", "MAT", "COMB", "IND"]
    amount: Fraction
    source: str
    week: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id or any(not v for v in self.event_id):
            raise ValueError("event_id must have nonempty provenance segments")
        if not isinstance(self.nature, PostingNature):
            raise ValueError("posting nature must be typed")
        if self.category not in {"MO", "EQ", "MAT", "COMB", "IND"}:
            raise ValueError("posting category must be typed")
        if type(self.amount) is not Fraction or self.amount < 0:
            raise ValueError("posting amount must be a nonnegative exact Fraction")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("posting source must be explicit")
        if self.nature in (PostingNature.ACTIVE, PostingNature.IDLE):
            if self.category not in {"MO", "EQ"} or not self.week:
                raise ValueError("presence needs MO/EQ classification and exact week")
        elif self.nature == PostingNature.ACQUISITION:
            if self.category not in {"MAT", "COMB"} or not self.week:
                raise ValueError("acquisition needs MAT/COMB category and week")
        elif self.nature in (PostingNature.MOBILIZATION, PostingNature.DEMOBILIZATION,
                             PostingNature.INDIRECT, PostingNature.HOLDING):
            if self.category != "IND":
                raise ValueError("mobility and indirect costs are not contractual K or V")


@dataclass(frozen=True)
class ExclusiveCostLedger:
    """P17-A. Disjoint authoritative postings, with exact rational totals."""

    postings: tuple[CostPosting, ...]
    contract_scope: str = "EXACT_FIXED_PHYSICAL_POOL_AND_DECLARED_PURCHASES"

    def __post_init__(self) -> None:
        ids = [line.event_id for line in self.postings]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate financial ownership for the same cost event")

    def sum_natures(self, *natures: PostingNature) -> Fraction:
        return sum((line.amount for line in self.postings if line.nature in natures),
                   start=Fraction(0))

    @property
    def contractual_k(self) -> Fraction:
        return self.sum_natures(PostingNature.ACTIVE, PostingNature.IDLE)

    @property
    def consumable_v(self) -> Fraction:
        return self.sum_natures(PostingNature.ACQUISITION)

    @property
    def indirect(self) -> Fraction:
        return self.sum_natures(PostingNature.MOBILIZATION,
                                PostingNature.DEMOBILIZATION,
                                PostingNature.INDIRECT, PostingNature.HOLDING)

    @property
    def direct(self) -> Fraction:
        return self.contractual_k + self.consumable_v

    @property
    def total(self) -> Fraction:
        return self.direct + self.indirect


@dataclass(frozen=True)
class PhysicalPurchase:
    """Physically measured consumption; NEVER a monetary hourly proxy."""

    evidence_id: str
    activity_id: str
    good_id: str
    week: str
    quantity: Fraction
    physical_unit: str
    unit_price: Fraction
    category: ConsumableCategory

    def __post_init__(self) -> None:
        if any(not isinstance(s, str) or not s.strip() for s in
               (self.evidence_id, self.activity_id, self.good_id, self.week,
                self.physical_unit)):
            raise ValueError("acquisition needs complete physical provenance")
        if self.category not in {"MAT", "COMB"}:
            raise ValueError("physical purchases cannot be contractual MO/EQ")
        for field in ("quantity", "unit_price"):
            v = getattr(self, field)
            if type(v) is not Fraction or v < 0:
                raise ValueError(f"{field} must be a nonnegative exact Fraction")


def book_exact_pool(
    pool: ExactPoolResult,
    tariffs: Mapping[str, ResourceTariff],
    categories: Mapping[str, ContractCategory],
) -> ExclusiveCostLedger:
    """Reconstruct weekly active/standby and movements from SAME P16 chains.

    One active or idle entry per actual instance level and week; one
    mobilization/demobilization event per chain. No MAT or COMB emitted.
    Contractual tariffs must refer to the same week and exact instance.
    """
    resources = {ledger.resource_type for ledger in pool.ledgers}
    if set(tariffs) != resources or set(categories) != resources:
        raise ValueError("all physical resource types need explicit tariffs and MO/EQ classification")
    if len(resources) != len(pool.ledgers):
        raise ValueError("duplicate resource type in pool")

    lines: list[CostPosting] = []
    for physical in pool.ledgers:
        resource = physical.resource_type
        category = categories[resource]
        if category not in ("MO", "EQ"):
            raise ValueError(f"{resource}: mixed or consumable category requires separate composition")
        tariff = tariffs[resource]
        if not isinstance(tariff, ResourceTariff):
            raise ValueError(f"{resource}: tariff missing exact physical contract")
        if not (len(physical.demand) == len(physical.presence) ==
                len(physical.standby) == len(pool.calendar_weeks)):
            raise ValueError(f"{resource}: incomplete weekly contract")
        if any(p < d or p - d != s for p, d, s in
               zip(physical.presence, physical.demand, physical.standby, strict=True)):
            raise ValueError(f"{resource}: contractual presence violates physical demand")

        actual_presence = [0] * len(pool.calendar_weeks)
        actual_active = [0] * len(pool.calendar_weeks)
        # P16-E explicit assignment paths and legacy fixed-level chains have
        # different semantics. Never silently mix them: explicit paths use
        # active_week_indices, while legacy chains infer active state from level.
        explicit_modes = {bool(chain.active_week_indices) for chain in physical.chains}
        if len(explicit_modes) > 1:
            raise ValueError(f"{resource}: mixed explicit-instance and fixed-level chain encodings")
        explicit_assignment = explicit_modes == {True}
        owned_level_weeks: set[tuple[int, int]] = set()
        active_level_weeks: set[tuple[int, int]] = set()
        for chain in physical.chains:
            if chain.resource_type != resource or chain.level < 1:
                raise ValueError(f"{resource}: invalid instance-chain identity")
            if not 0 <= chain.start < chain.end <= len(pool.calendar_weeks):
                raise ValueError(f"{resource}: contract outside physical horizon")
            active_indices = tuple(chain.active_week_indices)
            if explicit_assignment:
                if (
                    any(type(j) is not int or not chain.start <= j < chain.end for j in active_indices)
                    or not active_indices
                    or tuple(sorted(set(active_indices))) != active_indices
                    or active_indices[0] != chain.start
                    or active_indices[-1] != chain.end - 1
                ):
                    raise ValueError(f"{resource}: invalid explicit active-week instance assignment")
                expected_idle = chain.end - chain.start - len(active_indices)
                if len(active_indices) != chain.active_weeks or expected_idle != chain.idle_weeks:
                    raise ValueError(f"{resource}: explicit chain active/standby metadata mismatch")
                if any(
                    following - previous - 1 > tariff.max_idle_gap
                    for previous, following in zip(active_indices[:-1], active_indices[1:], strict=True)
                ):
                    raise ValueError(f"{resource}: explicit instance exceeds maximum idle gap")
                active_index_set = set(active_indices)
            else:
                active_index_set = set()

            origin = ("POOL", resource, str(chain.level), str(chain.start), str(chain.end))
            active_weeks = 0
            idle_weeks = 0
            for j in range(chain.start, chain.end):
                level_week = (chain.level, j)
                if level_week in owned_level_weeks:
                    raise ValueError(f"{resource}: overlapping instance-level contract ownership")
                owned_level_weeks.add(level_week)
                actual_presence[j] += 1
                is_active = j in active_index_set if explicit_assignment else physical.demand[j] >= chain.level
                if is_active:
                    active_level_weeks.add(level_week)
                    actual_active[j] += 1
                active_weeks += int(is_active)
                idle_weeks += int(not is_active)
                nature = PostingNature.ACTIVE if is_active else PostingNature.IDLE
                amount = tariff.active_week if is_active else tariff.idle_week
                lines.append(CostPosting(origin + (nature.value, str(j)), nature,
                                         category, amount, resource, pool.calendar_weeks[j]))
            if active_weeks != chain.active_weeks or idle_weeks != chain.idle_weeks:
                raise ValueError(f"{resource}: chain activity/standby evidence mismatch")
            lines.extend((
                CostPosting(origin + ("MOB",), PostingNature.MOBILIZATION, "IND",
                            tariff.mobilize, resource, pool.calendar_weeks[chain.start]),
                CostPosting(origin + ("DEMOB",), PostingNature.DEMOBILIZATION, "IND",
                            tariff.demobilize, resource, pool.calendar_weeks[chain.end - 1]),
            ))
        if tuple(actual_presence) != physical.presence:
            raise ValueError(f"{resource}: instance chains do not reconstruct presence")
        if tuple(actual_active) != physical.demand:
            raise ValueError(f"{resource}: active instance chains do not reconstruct exact physical demand")
        if not explicit_assignment:
            required_levels = {
                (level, j)
                for j, demand in enumerate(physical.demand)
                for level in range(1, demand + 1)
            }
            if active_level_weeks != required_levels:
                raise ValueError(f"{resource}: instance levels do not cover exact physical demand")
        contract_active = sum((x.amount for x in lines if x.source == resource and
                               x.nature == PostingNature.ACTIVE), start=Fraction(0))
        contract_idle = sum((x.amount for x in lines if x.source == resource and
                             x.nature == PostingNature.IDLE), start=Fraction(0))
        contract_movements = sum((x.amount for x in lines if x.source == resource and
                                  x.nature in (PostingNature.MOBILIZATION,
                                               PostingNature.DEMOBILIZATION)),
                                 start=Fraction(0))
        if (contract_active, contract_idle, contract_movements) != (
                physical.active_cost, physical.standby_cost, physical.mobility_cost):
            raise ValueError(f"{resource}: monetary ledger not reconciled to P16 exact pool")
    return ExclusiveCostLedger(tuple(lines))


def attach_physical_purchases(
    ledger: ExclusiveCostLedger,
    purchases: Iterable[PhysicalPurchase],
) -> ExclusiveCostLedger:
    """Append physically measured acquisitions, never inferred from idle weeks."""
    lines = list(ledger.postings)
    for purchase in purchases:
        if not isinstance(purchase, PhysicalPurchase):
            raise ValueError("typed physical-purchase evidence required")
        if purchase.quantity == 0:
            continue
        lines.append(CostPosting(
            ("CONSUMABLE", purchase.evidence_id),
            PostingNature.ACQUISITION,
            purchase.category,
            purchase.quantity * purchase.unit_price,
            purchase.good_id,
            purchase.week,
        ))
    return ExclusiveCostLedger(tuple(lines))
