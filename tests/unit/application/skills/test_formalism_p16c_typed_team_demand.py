"""P16-C: typed resources derive from physical team profiles, never sums of types."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import concilium.application.skills as skills

_ = skills.run_equipes_e_alocacao
mod = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]


def _fixture(fronts: tuple[int, ...], costs: float = 600.0):
    # ISO 2020 has a valid week 53; next week is 2021-W01.
    keys = ["2020-W52", "2020-W53", "2021-W01"][: len(fronts)]
    dist = {w: SimpleNamespace(num_equipes=m) for w, m in zip(keys, fronts, strict=True)}
    sched = SimpleNamespace(distribuicao_semanal=dist)
    equipe = SimpleNamespace(
        custo_operacional_agregado=costs,
        custo_mao_obra_mensal=100.0,
        custo_equipamentos_mensal=50.0,
        custo_combustivel_total_mensal=0.0,
        custo_material_mensal=0.0,
    )
    return sched, equipe


def _run(fronts: tuple[int, ...], resource_map: dict[str, int], profiles: dict | None = None):
    sched, equipe = _fixture(fronts)
    pool = {key: max(1, value) for key, value in resource_map.items()}
    items, weekly, validations = {}, {}, []
    mod._process_item_tipo_map(
        "A", resource_map, {"A": equipe}, pool, {"A": sched},
        items, weekly, validations, profiles,
    )
    return items, weekly, validations


def test_heterogeneous_types_are_never_added_to_form_a_team_count() -> None:
    # Peak 3 real teams -> 6 workers and 3 machines; ramp 1, 2, 3.
    items, weekly, validations = _run(
        (1, 2, 3), {"WORKERS": 6, "MACHINES": 3},
        {"WORKERS": {"per_front": 2}, "MACHINES": {"per_front": 1}},
    )
    assert weekly["WORKERS"] == {"2020-W52": 2, "2020-W53": 4, "2021-W01": 6}
    assert weekly["MACHINES"] == {"2020-W52": 1, "2020-W53": 2, "2021-W01": 3}
    assert items["WORKERS"][0]["machine_weeks"] == 12
    assert items["MACHINES"][0]["machine_weeks"] == 6
    assert items["WORKERS"][0]["machine_weeks"] == sum(weekly["WORKERS"].values())
    assert items["MACHINES"][0]["machine_weeks"] == sum(weekly["MACHINES"].values())
    assert not validations
    assert mod._week_idx("2020-W53") + 1 == mod._week_idx("2021-W01")


def test_changing_unrelated_resource_counts_never_changes_machine_demand() -> None:
    _, initial, _ = _run(
        (1, 2, 3), {"MACHINES": 3, "WORKERS": 6},
        {"MACHINES": {"per_front": 1}, "WORKERS": {"per_front": 2}},
    )
    _, changed, _ = _run(
        (1, 2, 3), {"MACHINES": 3, "WORKERS": 30},
        {"MACHINES": {"per_front": 1}, "WORKERS": {"per_front": 10}},
    )
    assert changed["MACHINES"] == initial["MACHINES"]


def test_shared_single_machine_at_peak_requires_explicit_composition_function() -> None:
    # 1 machine at peak of 2 fronts: partial-front demand is NOT 0.5
    # physical machines and may not be guessed as 0 or 1.
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01.*explicit"):
        _run((1, 2), {"WORKERS": 4, "SHARED_MACHINE": 1}, {"WORKERS": {"per_front": 2}})


def test_failure_does_not_leave_partially_written_heterogeneous_ledger() -> None:
    sched, eq = _fixture((1, 2))
    items, weekly = {}, {}
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01"):
        mod._process_item_tipo_map(
            "A", {"WORKERS": 4, "SHARED_MACHINE": 1},
            {"A": eq}, {"WORKERS": 4, "SHARED_MACHINE": 1},
            {"A": sched}, items, weekly, [], {"WORKERS": {"per_front": 2}},
        )
    assert items == {}
    assert weekly == {}


@pytest.mark.parametrize("fronts", [(1, 0.5), (1, -2), (1, float("nan"))])
def test_fractional_or_nonfinite_fronts_are_never_accepted(fronts: tuple[float, ...]) -> None:
    # A physical resource contract needs integer fronts. A fraction cannot
    # turn into a rounding-dependent monetary obligation.
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01"):
        mod._demand_from_team_profile(4, 2, fronts[1], "WORKERS")


def test_zero_required_resources_do_not_fabricate_machine_weeks() -> None:
    items, weekly, _ = _run((1, 1), {"NO_RESOURCE": 0})
    assert items["NO_RESOURCE"][0]["machine_weeks"] == 0
    assert weekly["NO_RESOURCE"] == {"2020-W52": 0, "2020-W53": 0}


def test_resource_demand_is_fully_mobilized_at_peak_without_linear_guessing() -> None:
    # Shared resource whose peak demand is 1: if m stays at peak=2,
    # that count is known and no partial-front extrapolation is necessary.
    items, weekly, _ = _run((2, 2), {"SHARED": 1})
    assert weekly["SHARED"] == {"2020-W52": 1, "2020-W53": 1}
    assert items["SHARED"][0]["machine_weeks"] == 2


def test_explicit_nonlinear_shared_equipment_needs_no_fractional_guess() -> None:
    items, weekly, _ = _run(
        (1, 2), {"MACHINES": 1, "WORKERS": 4},
        {
            "MACHINES": {"by_fronts": {"1": 1, "2": 1}},
            "WORKERS": {"per_front": 2},
        },
    )
    assert weekly["MACHINES"] == {"2020-W52": 1, "2020-W53": 1}
    assert items["MACHINES"][0]["machine_weeks"] == 2


def test_integral_ratio_is_not_automatically_proof_of_linear_composition() -> None:
    # At peak two teams can use two machines, but one team might use
    # one OR two machines. Do not infer from integer divisibility.
    with pytest.raises(ValueError, match="needs explicit a_i,g"):
        _run((1, 2), {"MACHINES": 2})


def test_inconsistent_declared_peak_is_rejected() -> None:
    with pytest.raises(ValueError, match="peak disagrees"):
        _run((1, 2), {"MACHINES": 1}, {"MACHINES": {"per_front": 1}})


def test_auto_derived_composite_team_maps_one_unit_per_front() -> None:
    _, weekly, _ = _run((1, 2), {"EQUIPE-COMP-ABC123": 2})
    assert weekly["EQUIPE-COMP-ABC123"] == {"2020-W52": 1, "2020-W53": 2}


def test_peak_resource_count_is_not_silently_rounded_in_activity_spec() -> None:
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01"):
        mod._build_item_tipo_map(
            [{"item_id": "A", "required_resources": {"MACHINES": 1.5}}]
        )


def test_nonfinite_scheduled_team_weeks_fail_even_if_other_week_is_valid() -> None:
    sched, eq = _fixture((1, 2))
    sched.distribuicao_semanal["2020-W53"] = SimpleNamespace(num_equipes=float("nan"))
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01"):
        mod._process_item_tipo_map(
            "A", {"EQUIPE-COMP-ABC123": 2},
            {"A": eq}, {"EQUIPE-COMP-ABC123": 2},
            {"A": sched}, {}, {}, [],
        )


def test_binary_float_ramp_noise_is_not_an_extra_team() -> None:
    # P2 regression: scheduler emits fractions and then multiplies by n_max.
    # Exactly seven mobilized teams must survive 25 * (7/25).
    encoded = 25 * (7 / 25)
    assert encoded != 7  # confirms a real float representation artifact
    assert mod._integral_front_count(encoded, "m_ij") == 7
    _, weekly, _ = _run((encoded, 25), {"EQUIPE-COMP-ABC123": 25})
    assert weekly["EQUIPE-COMP-ABC123"] == {"2020-W52": 7, "2020-W53": 25}


@pytest.mark.parametrize(
    "bad",
    [7.00000001, 7.125, 6.5, float("inf"), float("-inf"), float("nan"), float(2**53 + 2)],
)
def test_ulp_normalization_does_not_accept_real_fractional_or_unsafe_counts(bad: float) -> None:
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01"):
        mod._integral_front_count(bad, "m_ij")


def test_explicit_decimal_fraction_is_not_rounded() -> None:
    # An authored high precision fraction is NOT an artifact of binary math.
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01"):
        mod._integral_front_count("7.000000000000001", "m_ij")
