"""P16-C: typed resources derive from physical team profiles, never sums of types."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import concilium.application.skills as skills

_ = skills.run_equipes_e_alocacao
mod = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]


def _fixture(fronts: tuple[int, ...], costs: float = 600.0):
    keys = ["2026-W52", "2026-W53", "2027-W01"][: len(fronts)]
    # ISO week 53 is valid for 2026? For deterministic physical test use
    # only valid 2020 ISO year with a week 53.
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


def _run(fronts: tuple[int, ...], resource_map: dict[str, int]):
    sched, equipe = _fixture(fronts)
    pool = {key: max(1, value) for key, value in resource_map.items()}
    items, weekly, validations = {}, {}, []
    mod._process_item_tipo_map(
        "A", resource_map, {"A": equipe}, pool, {"A": sched},
        items, weekly, validations,
    )
    return items, weekly, validations


def test_heterogeneous_types_are_never_added_to_form_a_team_count() -> None:
    # Peak 3 real teams -> 6 workers and 3 machines; ramp 1, 2, 3.
    items, weekly, validations = _run((1, 2, 3), {"WORKERS": 6, "MACHINES": 3})
    assert weekly["WORKERS"] == {"2020-W52": 2, "2020-W53": 4, "2021-W01": 6}
    assert weekly["MACHINES"] == {"2020-W52": 1, "2020-W53": 2, "2021-W01": 3}
    assert items["WORKERS"][0]["machine_weeks"] == 12
    assert items["MACHINES"][0]["machine_weeks"] == 6
    assert items["WORKERS"][0]["machine_weeks"] == sum(weekly["WORKERS"].values())
    assert items["MACHINES"][0]["machine_weeks"] == sum(weekly["MACHINES"].values())
    assert not validations
    assert mod._week_idx("2020-W53") + 1 == mod._week_idx("2021-W01")


def test_changing_unrelated_resource_counts_never_changes_machine_demand() -> None:
    _, initial, _ = _run((1, 2, 3), {"MACHINES": 3, "WORKERS": 6})
    _, changed, _ = _run((1, 2, 3), {"MACHINES": 3, "WORKERS": 30})
    assert changed["MACHINES"] == initial["MACHINES"]


def test_shared_single_machine_at_peak_requires_explicit_composition_function() -> None:
    # 1 machine at peak of 2 fronts: partial-front demand is NOT 0.5
    # physical machines and may not be guessed as 0 or 1.
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01.*explicit"):
        _run((1, 2), {"WORKERS": 4, "SHARED_MACHINE": 1})


def test_failure_does_not_leave_partially_written_heterogeneous_ledger() -> None:
    sched, eq = _fixture((1, 2))
    items, weekly = {}, {}
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-01"):
        mod._process_item_tipo_map(
            "A", {"WORKERS": 4, "SHARED_MACHINE": 1},
            {"A": eq}, {"WORKERS": 4, "SHARED_MACHINE": 1},
            {"A": sched}, items, weekly, [],
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
