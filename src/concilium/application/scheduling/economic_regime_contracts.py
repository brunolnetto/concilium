"""P13-B: opt-in economic regime contract over exact P16/P18 evidence.

A canonical pool snapshot with legacy defaults is NOT commercial evidence.
This is a read-only diagnostic. It does not book P17 postings or certify GO.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Literal

from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis,
    PhysicallyPricedGood,
    convert_physical,
)
from concilium.application.scheduling.resource_level_contracts import (
    ExactPoolResult,
    ResourceTariff,
)
from concilium.domain.models.canonical._estoque_consumiveis import RecursoConsumivelCanonical
from concilium.domain.models.canonical._pool_recursos import RecursoContrato


class ContractRegime(StrEnum):
    FULL_RATE_STANDBY = "FULL_RATE_STANDBY"
    DISCOUNTED_STANDBY = "DISCOUNTED_STANDBY"
    EXPLICIT_OFF_HIRE = "EXPLICIT_OFF_HIRE"


class ConsumptionRegime(StrEnum):
    OUTPUT_PROPORTIONAL = "OUTPUT_PROPORTIONAL"
    OUTPUT_WITH_MEASURED_LOSS = "OUTPUT_WITH_MEASURED_LOSS"
    HOURLY_WITH_MEASURED_IDLE = "HOURLY_WITH_MEASURED_IDLE"


@dataclass(frozen=True)
class ContractRegimeEvidence:
    """One resource type's declared commercial identity and weekly tariff."""

    contract_id: str
    resource_type: str
    regime: ContractRegime
    tariff: ResourceTariff
    source_id: str
    currency: str
    off_hire_weeks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.regime, ContractRegime):
            raise ValueError("typed contract regime is mandatory")
        if not isinstance(self.tariff, ResourceTariff):
            raise ValueError("exact P16 contractual tariff is mandatory")
        if any(not isinstance(v, str) or not v.strip()
               for v in (self.contract_id, self.resource_type, self.source_id)):
            raise ValueError("contract identity, resource type and source are mandatory")
        if not isinstance(self.currency, str) or not (
            len(self.currency) == 3 and self.currency.isalpha()
            and self.currency == self.currency.upper()
        ):
            raise ValueError("contract currency must be explicit ISO-style code")
        if len(self.off_hire_weeks) != len(set(self.off_hire_weeks)):
            raise ValueError("duplicate off-hire week")
        if self.regime is ContractRegime.FULL_RATE_STANDBY:
            if self.tariff.idle_week != self.tariff.active_week:
                raise ValueError("full-rate standby requires equal active and idle tariffs")
            if self.off_hire_weeks:
                raise ValueError("baseline cannot silently declare off-hire variant")
        elif self.regime is ContractRegime.DISCOUNTED_STANDBY:
            if self.tariff.idle_week >= self.tariff.active_week:
                raise ValueError("discounted standby requires strictly lower idle tariff")
            if self.off_hire_weeks:
                raise ValueError("off-hire requires its own explicit contract regime")
        elif not self.off_hire_weeks:
            raise ValueError("off-hire contract needs explicitly declared off-hire weeks")


@dataclass(frozen=True)
class ContractRegimeWitness:
    contract_id: str
    resource_type: str
    regime: ContractRegime
    active_cost: Fraction
    standby_cost: Fraction
    movement_cost: Fraction
    off_hire_weeks: tuple[str, ...]
    scope: Literal["NOT_PROJECT_GO"] = "NOT_PROJECT_GO"


def witness_contract_regime(
    evidence: ContractRegimeEvidence,
    pool: ExactPoolResult,
    canonical: RecursoContrato,
) -> ContractRegimeWitness:
    """Fail closed unless typed canonical identity and P16 physical totals agree."""
    if not isinstance(evidence, ContractRegimeEvidence):
        raise ValueError("explicit contract regime evidence required")
    if not isinstance(pool, ExactPoolResult) or not isinstance(canonical, RecursoContrato):
        raise ValueError("real physical pool and canonical contract required")
    if (canonical.contrato_id != evidence.contract_id
            or canonical.tipo_id != evidence.resource_type):
        raise ValueError("canonical contract identity does not match evidence")
    if (canonical.regime_economico_p13 != evidence.regime.value
            or canonical.origem_regime_p13 != evidence.source_id
            or canonical.moeda_regime_p13 != evidence.currency):
        raise ValueError("canonical regime/source missing or inconsistent; NOT_EVALUATED")
    matches = [v for v in pool.ledgers if v.resource_type == evidence.resource_type]
    if len(matches) != 1:
        raise ValueError("unique P16 resource ledger is required")
    ledger = matches[0]
    if len(ledger.demand) != len(pool.calendar_weeks) or len(ledger.presence) != len(pool.calendar_weeks):
        raise ValueError("incomplete physical weeks")
    if (len(ledger.standby) != len(pool.calendar_weeks)
            or any(d < 0 or p < d or s < 0 or p - d != s
                   for d, p, s in zip(ledger.demand, ledger.presence,
                                      ledger.standby, strict=True))):
        raise ValueError("physical contractual presence/standby identity violated")
    # P16-E may encode explicit global instance paths; legacy P16-B/C outputs
    # use demand-height levels. Validate one representation per resource only.
    chain_modes = {bool(chain.active_week_indices) for chain in ledger.chains}
    if len(chain_modes) > 1:
        raise ValueError("mixed explicit-instance and fixed-level physical chains")
    explicit_assignment = chain_modes == {True}
    owned_level_weeks: set[tuple[int, int]] = set()
    active_level_weeks: set[tuple[int, int]] = set()
    actual_presence = [0] * len(pool.calendar_weeks)
    actual_active = [0] * len(pool.calendar_weeks)
    for chain in ledger.chains:
        if chain.resource_type != evidence.resource_type or chain.level < 1:
            raise ValueError("physical chain identity does not match resource type")
        if not 0 <= chain.start < chain.end <= len(pool.calendar_weeks):
            raise ValueError("physical chain outside the declared calendar")
        active_indices = tuple(chain.active_week_indices)
        if explicit_assignment:
            if (
                not active_indices
                or any(type(j) is not int or not chain.start <= j < chain.end for j in active_indices)
                or tuple(sorted(set(active_indices))) != active_indices
                or active_indices[0] != chain.start
                or active_indices[-1] != chain.end - 1
            ):
                raise ValueError("invalid explicit physical instance assignment")
            idle_expected = chain.end - chain.start - len(active_indices)
            if len(active_indices) != chain.active_weeks or idle_expected != chain.idle_weeks:
                raise ValueError("physical chain active/idle count mismatch")
            if any(
                following - previous - 1 > evidence.tariff.max_idle_gap
                for previous, following in zip(active_indices, active_indices[1:])
            ):
                raise ValueError("physical standby exceeds declared max_idle_gap")
            active_index_set = set(active_indices)
        else:
            if (ledger.demand[chain.start] < chain.level
                    or ledger.demand[chain.end - 1] < chain.level):
                raise ValueError("physical chain cannot start or end on standby")
            active_index_set = set()

        active = 0
        idle = 0
        consecutive_idle = 0
        for j in range(chain.start, chain.end):
            level_week = (chain.level, j)
            if level_week in owned_level_weeks:
                raise ValueError("duplicate physical chain level-week ownership")
            owned_level_weeks.add(level_week)
            actual_presence[j] += 1
            is_active = j in active_index_set if explicit_assignment else ledger.demand[j] >= chain.level
            if is_active:
                active_level_weeks.add(level_week)
                actual_active[j] += 1
                active += 1
                consecutive_idle = 0
            else:
                idle += 1
                consecutive_idle += 1
                if not explicit_assignment and consecutive_idle > evidence.tariff.max_idle_gap:
                    raise ValueError("physical standby exceeds declared max_idle_gap")
        if (active, idle) != (chain.active_weeks, chain.idle_weeks):
            raise ValueError("physical chain active/idle count mismatch")
    if not explicit_assignment:
        required_levels = {
            (level, j)
            for j, demand in enumerate(ledger.demand)
            for level in range(1, demand + 1)
        }
        if active_level_weeks != required_levels:
            raise ValueError("physical chains do not cover required demand levels")
    if tuple(actual_active) != ledger.demand:
        raise ValueError("physical instance chains do not reconstruct exact demand")
    if tuple(actual_presence) != ledger.presence:
        raise ValueError("physical chains do not reconstruct contractual presence")
    week_presence = dict(zip(pool.calendar_weeks, ledger.presence, strict=True))
    if len(week_presence) != len(pool.calendar_weeks):
        raise ValueError("non-unique calendar week")
    for week in evidence.off_hire_weeks:
        if week not in week_presence or week_presence[week] != 0:
            raise ValueError("off-hire must have zero actual contractual presence")
    t = evidence.tariff
    expected = (
        sum(ledger.demand) * t.active_week,
        sum(ledger.standby) * t.idle_week,
        len(ledger.chains) * t.movement,
    )
    actual = (ledger.active_cost, ledger.standby_cost, ledger.mobility_cost)
    if expected != actual:
        raise ValueError("P16 physical and commercial tariff totals do not reconcile")
    return ContractRegimeWitness(
        evidence.contract_id, evidence.resource_type, evidence.regime,
        *actual, evidence.off_hire_weeks,
    )


@dataclass(frozen=True)
class MeasuredExtra:
    """Real physical quantity, never an implicit purchase or monetary proxy."""

    quantity: Fraction
    unit: str
    source_id: str

    def __post_init__(self) -> None:
        if type(self.quantity) is not Fraction or self.quantity < 0:
            raise ValueError("extra consumption must be exact and nonnegative")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError("extra consumption physical unit required")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("measured extra consumption requires source")


@dataclass(frozen=True)
class ConsumptionRegimeWitness:
    good_id: str
    regime: ConsumptionRegime
    baseline_quantity: Fraction
    extra_quantity: Fraction
    total_quantity: Fraction
    total_cost: Fraction
    extra_cost: Fraction
    schedule_invariance_proved: bool
    scope: Literal["NOT_PROJECT_GO"] = "NOT_PROJECT_GO"


def witness_consumption_regime(
    *,
    regime: ConsumptionRegime,
    good: PhysicallyPricedGood,
    canonical: RecursoConsumivelCanonical,
    rate_source: str,
    price_source: str,
    delivered: Fraction | None = None,
    delivered_unit: str | None = None,
    operating_hours: Fraction | None = None,
    idle: MeasuredExtra | None = None,
    loss: MeasuredExtra | None = None,
) -> ConsumptionRegimeWitness:
    """Use measured q/h and extras; do not book purchases or infer stock ownership."""
    if not isinstance(regime, ConsumptionRegime) or not isinstance(good, PhysicallyPricedGood):
        raise ValueError("typed consumption regime and physical priced good required")
    if any(not isinstance(s, str) or not s.strip() for s in (rate_source, price_source)):
        raise ValueError("rate and unit-price provenance required")
    if (not isinstance(canonical, RecursoConsumivelCanonical)
            or canonical.resource_id != good.rate.good_id
            or canonical.regime_consumo_p13 != regime.value
            or canonical.origem_taxa_consumo_p13 != rate_source
            or canonical.origem_preco_consumo_p13 != price_source):
        raise ValueError("canonical consumption regime/provenance missing; NOT_EVALUATED")
    if regime in (ConsumptionRegime.OUTPUT_PROPORTIONAL,
                  ConsumptionRegime.OUTPUT_WITH_MEASURED_LOSS):
        if good.rate.basis is not ConsumptionBasis.PER_DELIVERED_UNIT:
            raise ValueError("output regime requires unit-of-output physical consumption rate")
        base = good.cost(delivered=delivered, delivered_unit=delivered_unit,
                         operating_hours=operating_hours)
        if idle is not None:
            raise ValueError("idle consumption is not output proportional")
        if regime is ConsumptionRegime.OUTPUT_PROPORTIONAL and loss is not None:
            raise ValueError("baseline cannot contain unclassified waste")
        if regime is ConsumptionRegime.OUTPUT_WITH_MEASURED_LOSS and loss is None:
            raise ValueError("loss regime requires explicit measured loss, including zero")
    else:
        if good.rate.basis is not ConsumptionBasis.PER_OPERATING_HOUR:
            raise ValueError("hourly regime requires real operating-hour consumption rate")
        base = good.cost(delivered=delivered, delivered_unit=delivered_unit,
                         operating_hours=operating_hours)
        if idle is None or loss is None:
            raise ValueError("hourly variant requires explicit idle and loss measurements")
    extras = tuple(x for x in (idle, loss) if x is not None)
    if len({x.source_id for x in extras}) != len(extras):
        raise ValueError("duplicate physical extra evidence")
    extra = sum(
        (convert_physical(x.quantity, x.unit, good.rate.good_unit) for x in extras),
        start=Fraction(0),
    )
    total = base.physical_quantity + extra
    extra_billed = convert_physical(extra, good.rate.good_unit, good.price_unit)
    return ConsumptionRegimeWitness(
        good.rate.good_id, regime, base.physical_quantity, extra, total,
        base.exact_cost + extra_billed * good.price_per_unit,
        extra_billed * good.price_per_unit,
        regime is ConsumptionRegime.OUTPUT_PROPORTIONAL,
    )
