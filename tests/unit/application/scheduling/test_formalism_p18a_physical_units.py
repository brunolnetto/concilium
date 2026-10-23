"""P18-A: deterministic physical units, tariffs and explicit unverified proxies."""
from fractions import Fraction

import pytest

from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis,
    LegacyHourlyMoneyProxy,
    PhysicalConsumptionRate,
    PhysicallyPricedGood,
    convert_physical,
)

F = Fraction


def test_mass_quantity_and_prices_are_equivalent_in_kg_and_tonnes() -> None:
    by_kg = PhysicallyPricedGood(
        PhysicalConsumptionRate("AGGREGATE", F(500), "kg",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
        F(1, 5), "kg",
    )
    by_tonne = PhysicallyPricedGood(
        PhysicalConsumptionRate("AGGREGATE", F(1, 2), "t",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
        F(200), "t",
    )
    a = by_kg.cost(delivered=F(4), delivered_unit="m³")
    b = by_tonne.cost(delivered=F(4), delivered_unit="m³")
    assert a.physical_quantity == F(2000)
    assert b.physical_quantity == F(2)
    assert a.exact_cost == b.exact_cost == F(400)
    assert convert_physical(a.physical_quantity, "kg", "t") == b.physical_quantity


def test_hourly_consumption_uses_actual_hours_not_output_over_peak_productivity() -> None:
    diesel = PhysicallyPricedGood(
        PhysicalConsumptionRate("DIESEL", F(5, 2), "l",
                                ConsumptionBasis.PER_OPERATING_HOUR),
        F(6), "L",
    )
    witness = diesel.cost(operating_hours=F(4))
    assert witness.physical_quantity == F(10)
    assert witness.exact_cost == F(60)
    assert diesel.cost(operating_hours=F(0)).exact_cost == 0
    with pytest.raises(ValueError, match="not inferred"):
        diesel.cost(operating_hours=F(4), delivered=F(100), delivered_unit="m³")


def test_normalized_length_and_volume_are_exact_but_mass_volume_not_equivalent() -> None:
    assert convert_physical(F(1), "T", "kg") == 1000
    assert convert_physical(F(500), "L", "m³") == F(1, 2)
    assert convert_physical(F(1), "km", "m") == 1000
    with pytest.raises(ValueError, match="incompatible"):
        convert_physical(F(1), "kg", "m³")
    with pytest.raises(ValueError, match="incompatible"):
        convert_physical(F(1), "sc", "unid")


def test_missing_unit_and_hourly_money_proxy_do_not_become_measured_quantity() -> None:
    with pytest.raises(ValueError, match="Unidade desconhecida"):
        PhysicalConsumptionRate("SAND", F(1), "R$/h",
                                ConsumptionBasis.PER_OPERATING_HOUR)
    rate = PhysicalConsumptionRate("DIESEL", F(2), "l",
                                   ConsumptionBasis.PER_OPERATING_HOUR)
    with pytest.raises(ValueError, match="incompatible"):
        PhysicallyPricedGood(rate, F(6), "h")
    legacy = LegacyHourlyMoneyProxy("DIESEL", F(20))
    assert legacy.evidence_status == "UNVERIFIED_LEGACY_MONETARY_PROXY"
    assert not hasattr(legacy, "physical_quantity")


def test_invalid_rate_basis_and_quantities_fail_closed() -> None:
    with pytest.raises(ValueError, match="basis"):
        PhysicalConsumptionRate("D", F(1), "l", "UNKNOWN")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="hourly rates"):
        PhysicalConsumptionRate("D", F(1), "l",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "h")
    with pytest.raises(ValueError, match="hourly consumption"):
        PhysicalConsumptionRate("D", F(1), "l",
                                ConsumptionBasis.PER_OPERATING_HOUR, "m³")
    with pytest.raises(ValueError, match="exact"):
        convert_physical(2.0, "kg", "t")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact"):
        LegacyHourlyMoneyProxy("D", 1.0)  # type: ignore[arg-type]


def test_no_fractional_loss_or_double_pricing_on_final_partial_week() -> None:
    material = PhysicallyPricedGood(
        PhysicalConsumptionRate("SAND", F(3, 5), "t",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
        F(400), "t",
    )
    capacity_full_week = F(400)
    realized_last_week = F(100)
    actual = material.cost(delivered=realized_last_week, delivered_unit="m³")
    assert actual.exact_cost == F(24000)
    assert material.cost(delivered=capacity_full_week,
                         delivered_unit="m³").exact_cost == F(96000)
