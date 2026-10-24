"""P13-B: typed regime witnesses against real P16, P18, and canonical models."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F

import pytest

from concilium.application.scheduling.economic_regime_contracts import (
    ConsumptionRegime,
    ContractRegime,
    ContractRegimeEvidence,
    MeasuredExtra,
    witness_consumption_regime,
    witness_contract_regime,
)
from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis,
    PhysicalConsumptionRate,
    PhysicallyPricedGood,
)
from concilium.application.scheduling.resource_level_contracts import (
    ExactPoolResult,
    InstanceChain,
    ResourceContractLedger,
    ResourceTariff,
)
from concilium.domain.models.canonical._pool_recursos import RecursoContrato


def canonical(**overrides: object) -> RecursoContrato:
    data: dict[str, object] = {
        "contrato_id": "C-01", "tipo_id": "EXC", "quantidade_contratada": 1,
        "semana_inicio": "S001", "semana_fim": "S004",
        "semanas_contrato": 4, "custo_unit_semanal": 100.0,
        "custo_total_contrato": 330.0,
        "regime_economico_p13": "DISCOUNTED_STANDBY",
        "origem_regime_p13": "contract:123",
    }
    data.update(overrides)
    return RecursoContrato.model_validate(data)


def real_pool(rate: ResourceTariff) -> ExactPoolResult:
    chain = InstanceChain("EXC", 1, 0, 4, 2, 2)
    return ExactPoolResult(
        ("S001", "S002", "S003", "S004"),
        (ResourceContractLedger(
            "EXC", (1, 0, 0, 1), (1, 1, 1, 1), (0, 1, 1, 0),
            (chain,), F(2) * rate.active_week, F(2) * rate.idle_week,
            rate.movement,
        ),),
    )


def discounted() -> tuple[ContractRegimeEvidence, ExactPoolResult]:
    rate = ResourceTariff(F(100), F(25), F(40), F(40), 2)
    return (
        ContractRegimeEvidence("C-01", "EXC", ContractRegime.DISCOUNTED_STANDBY,
                               rate, "contract:123", "BRL"),
        real_pool(rate),
    )


def test_real_p16_pool_matches_canonical_discounted_regime_and_serialization() -> None:
    declaration, physical = discounted()
    copied = RecursoContrato.model_validate(canonical().model_dump(mode="json"))
    witness = witness_contract_regime(declaration, physical, copied)
    assert (witness.active_cost, witness.standby_cost, witness.movement_cost) == (
        F(200), F(50), F(80),
    )
    assert witness.scope == "NOT_PROJECT_GO"
    assert witness.active_cost + witness.standby_cost + witness.movement_cost == F(330)


def test_absent_legacy_selector_and_missing_provenance_fail_closed() -> None:
    declaration, physical = discounted()
    with pytest.raises(ValueError, match="missing or inconsistent"):
        witness_contract_regime(
            declaration, physical,
            canonical(regime_economico_p13=None, origem_regime_p13=None),
        )
    with pytest.raises(ValueError, match="missing or inconsistent"):
        witness_contract_regime(
            declaration, physical, canonical(origem_regime_p13=None),
        )
    with pytest.raises(ValueError, match="missing or inconsistent"):
        witness_contract_regime(
            declaration, physical,
            canonical(regime_economico_p13="FULL_RATE_STANDBY"),
        )


def test_regime_rejects_mismatched_tariff_and_unproven_source() -> None:
    declaration, physical = discounted()
    with pytest.raises(ValueError, match="full-rate"):
        ContractRegimeEvidence(
            "C-01", "EXC", ContractRegime.FULL_RATE_STANDBY,
            declaration.tariff, "contract:123", "BRL",
        )
    with pytest.raises(ValueError, match="discounted"):
        ContractRegimeEvidence(
            "C-01", "EXC", ContractRegime.DISCOUNTED_STANDBY,
            ResourceTariff(F(100), F(100), F(40), F(40), 2),
            "contract:123", "BRL",
        )
    with pytest.raises(ValueError, match="source"):
        ContractRegimeEvidence(
            "C-01", "EXC", ContractRegime.DISCOUNTED_STANDBY,
            declaration.tariff, "", "BRL",
        )
    with pytest.raises(ValueError, match="do not reconcile"):
        witness_contract_regime(
            replace(declaration, tariff=ResourceTariff(F(110), F(25), F(40), F(40), 2)),
            physical, canonical(),
        )


def test_offhire_must_be_declared_and_have_no_presence() -> None:
    rate = ResourceTariff(F(100), F(25), F(40), F(40), 0)
    chains = (
        InstanceChain("EXC", 1, 0, 1, 1, 0),
        InstanceChain("EXC", 1, 2, 3, 1, 0),
    )
    physical = ExactPoolResult(
        ("S001", "S002", "S003"),
        (ResourceContractLedger(
            "EXC", (1, 0, 1), (1, 0, 1), (0, 0, 0), chains,
            F(200), F(0), F(160),
        ),),
    )
    declaration = ContractRegimeEvidence(
        "C-01", "EXC", ContractRegime.EXPLICIT_OFF_HIRE,
        rate, "contract:123", "BRL", ("S002",),
    )
    assert witness_contract_regime(
        declaration, physical, canonical(regime_economico_p13="EXPLICIT_OFF_HIRE")
    ).movement_cost == F(160)
    with pytest.raises(ValueError, match="zero actual contractual presence"):
        witness_contract_regime(
            replace(declaration, off_hire_weeks=("S001",)),
            physical, canonical(regime_economico_p13="EXPLICIT_OFF_HIRE"),
        )
    with pytest.raises(ValueError, match="explicitly declared"):
        replace(declaration, off_hire_weeks=())


def output_good() -> PhysicallyPricedGood:
    return PhysicallyPricedGood(
        PhysicalConsumptionRate("DIESEL", F(2), "l",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
        F(5), "l",
    )


def test_output_baseline_is_invariant_only_with_fixed_physical_rate() -> None:
    good = output_good()
    one = witness_consumption_regime(
        regime=ConsumptionRegime.OUTPUT_PROPORTIONAL,
        good=good, rate_source="measure:rate", price_source="invoice:price",
        delivered=F(100), delivered_unit="m³",
    )
    part1 = witness_consumption_regime(
        regime=ConsumptionRegime.OUTPUT_PROPORTIONAL,
        good=good, rate_source="measure:rate", price_source="invoice:price",
        delivered=F(40), delivered_unit="m³",
    )
    part2 = witness_consumption_regime(
        regime=ConsumptionRegime.OUTPUT_PROPORTIONAL,
        good=good, rate_source="measure:rate", price_source="invoice:price",
        delivered=F(60), delivered_unit="m³",
    )
    assert one.total_quantity == part1.total_quantity + part2.total_quantity == F(200)
    assert one.total_cost == part1.total_cost + part2.total_cost == F(1000)
    assert one.extra_cost == 0
    assert one.schedule_invariance_proved
    assert one.scope == "NOT_PROJECT_GO"


def test_loss_variant_discloses_noninvariant_delta_without_booking_purchases() -> None:
    good = output_good()
    result = witness_consumption_regime(
        regime=ConsumptionRegime.OUTPUT_WITH_MEASURED_LOSS,
        good=good, rate_source="measure:rate", price_source="invoice:price",
        delivered=F(100), delivered_unit="m³",
        loss=MeasuredExtra(F(20), "l", "loss:measured"),
    )
    assert (result.baseline_quantity, result.extra_quantity,
            result.total_quantity, result.total_cost, result.extra_cost) == (
        F(200), F(20), F(220), F(1100), F(100),
    )
    assert not result.schedule_invariance_proved
    with pytest.raises(ValueError, match="explicit measured loss"):
        witness_consumption_regime(
            regime=ConsumptionRegime.OUTPUT_WITH_MEASURED_LOSS,
            good=good, rate_source="measure:rate", price_source="invoice:price",
            delivered=F(100), delivered_unit="m³",
        )


def test_hourly_idle_and_waste_are_independently_measured() -> None:
    good = PhysicallyPricedGood(
        PhysicalConsumptionRate("DIESEL", F(3), "l",
                                ConsumptionBasis.PER_OPERATING_HOUR),
        F(5), "l",
    )
    kwargs = dict(
        regime=ConsumptionRegime.HOURLY_WITH_MEASURED_IDLE,
        good=good, rate_source="calibration:3", price_source="invoice:price",
        operating_hours=F(10),
        idle=MeasuredExtra(F(2), "l", "idle:fuel"),
        loss=MeasuredExtra(F(1), "l", "waste:fuel"),
    )
    witness = witness_consumption_regime(**kwargs)
    assert (witness.baseline_quantity, witness.extra_quantity,
            witness.total_quantity, witness.total_cost, witness.extra_cost) == (
        F(30), F(3), F(33), F(165), F(15),
    )
    assert not witness.schedule_invariance_proved
    with pytest.raises(ValueError, match="duplicate physical extra evidence"):
        witness_consumption_regime(
            **(kwargs | {"loss": MeasuredExtra(F(1), "l", "idle:fuel")})
        )
    with pytest.raises(ValueError, match="requires explicit idle and loss"):
        witness_consumption_regime(**(kwargs | {"loss": None}))


def test_baseline_rejects_unclassified_idle_and_missing_price_provenance() -> None:
    kwargs = dict(
        regime=ConsumptionRegime.OUTPUT_PROPORTIONAL, good=output_good(),
        rate_source="measure:rate", price_source="invoice:price",
        delivered=F(100), delivered_unit="m³",
    )
    with pytest.raises(ValueError, match="not output proportional"):
        witness_consumption_regime(
            **(kwargs | {"idle": MeasuredExtra(F(1), "l", "idle:1")})
        )
    with pytest.raises(ValueError, match="provenance"):
        witness_consumption_regime(**(kwargs | {"price_source": ""}))
    with pytest.raises(ValueError, match="requires unit-of-output"):
        witness_consumption_regime(
            **(kwargs | {"good": PhysicallyPricedGood(
                PhysicalConsumptionRate("DIESEL", F(3), "l",
                                        ConsumptionBasis.PER_OPERATING_HOUR),
                F(5), "l",
            )})
        )
