"""#24 P24-B: metamorphic relations on the golden RFPs through the real pipeline.

Each relation runs the pipeline on a golden spec and on a controlled
transformation of it, and checks how the outputs must relate — without
re-deriving the expected numbers from the code under test:

- pointwise wetter climate cannot improve any week's nominal throughput nor
  finish any activity earlier (fixed resource policy);
- halving Q halves every baseline consumable, physically and in currency,
  within the documented physical tolerance;
- the declared idle gap toggles plant perpetuation exactly at the threshold
  (gap = 1 week: one hire on standby; max_idle_gap 0: release and remobilise),
  and forbidding perpetuation cannot make the pool cheaper.

Every transformed run must remain a clean GO whose phases match the
independent oracles. All runs are `slow` (one pipeline run each).
"""

from __future__ import annotations

import copy
from collections import defaultdict
from fractions import Fraction

import pytest

from tests.support.golden_differential import differential_report
from tests.support.golden_pipeline import (
    catalog,
    climate_snapshot,
    load_canonical,
    oracle_c_cat,
    run,
    scenario,
    wetter_climate,
)

pytestmark = pytest.mark.slow

# P24-A documented absolute tolerance on weekly physical quantities.
Q_TOL = Fraction(1, 10**6)
PLANT = "EQ-USINA-SOLOS-300TH"


def _go_matching_oracles(result, service, spec, *, allow_unverified: bool = False):
    certificate = result["formalism_certificate"]
    assert (certificate["effective_decision"], certificate["project_go"]) == ("GO", True), certificate["reasons"]
    canonical = load_canonical(result, service)
    report = differential_report(canonical, catalog(spec), certificate)
    assert report["first_divergence"] is None, report["first_divergence"]
    if not allow_unverified:
        assert report["unverified"] == []
    return canonical, report


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory):
    cache: dict[str, tuple] = {}

    def get(name: str, spec: dict, climate: dict | None = None, **kwargs):
        if name not in cache:
            result, service = run(tmp_path_factory.mktemp(name), spec, climate=climate)
            canonical, report = _go_matching_oracles(result, service, spec, **kwargs)
            cache[name] = (canonical, report, spec)
        return cache[name]

    return get


def _cells(canonical):
    return {
        (activity.activity_id, week): cell
        for activity in canonical.cronograma.scheduled_activities
        for week, cell in activity.distribuicao_semanal.items()
    }


def _nominal(cell) -> float:
    return cell.num_equipes * cell.fator_clima * cell.fator_calendario * cell.fator_jornada


def test_wetter_climate_cannot_improve_throughput_or_finish_earlier(runs) -> None:
    spec = scenario("sharing_theta_standby_remob")
    base, _report, _spec = runs("sharing", spec)
    # The window of the remobilised loaders grows past the exhaustive P22-C
    # oracle's 6-week bound, so those POOL checks are UNVERIFIED (never DIVERGE).
    wet, _report, _spec = runs(
        "sharing_wetter", copy.deepcopy(spec), wetter_climate(climate_snapshot(spec)), allow_unverified=True
    )

    base_cells, wet_cells = _cells(base), _cells(wet)
    common = base_cells.keys() & wet_cells.keys()
    assert common
    for key in common:
        assert wet_cells[key].fator_clima <= base_cells[key].fator_clima, key
        assert _nominal(wet_cells[key]) <= _nominal(base_cells[key]) + 1e-12, key

    base_end = {a.activity_id: a.end_week for a in base.cronograma.scheduled_activities}
    wet_end = {a.activity_id: a.end_week for a in wet.cronograma.scheduled_activities}
    assert all(wet_end[a] >= base_end[a] for a in base_end), (base_end, wet_end)
    assert max(wet_end.values()) > max(base_end.values()), "the perturbation must actually bind"


def _consumption(canonical):
    physical: dict[tuple[str, str], Fraction] = defaultdict(Fraction)
    cost: dict[tuple[str, str], Fraction] = defaultdict(Fraction)
    for row in canonical.p18_consumption_preview["evidence"]:
        key = (row["activity_id"], row["good_id"])
        physical[key] += Fraction(str(row["physical_quantity"]))
        cost[key] += Fraction(str(row["exact_cost"]))
    return physical, cost


def test_halving_q_halves_every_baseline_consumable(runs) -> None:
    spec = scenario("single_plant_sequence")
    half = copy.deepcopy(spec)
    for item in half["eap"]:
        item["quantitativo"] = item["quantitativo"] / 2
    basis = oracle_c_cat(half)  # independent C^cat of the halved scope
    evidence = half["skill_inputs"]["06-resultado-financeiro"]["p21_pricing_evidence"]
    evidence["catalog"]["amount"] = basis
    evidence["regulatory_basis"]["amount"] = basis

    base, _report, _spec = runs("sequence", spec)
    halved, _report, _spec = runs("sequence_half_q", half)
    base_q, base_v = _consumption(base)
    half_q, half_v = _consumption(halved)
    assert base_q.keys() == half_q.keys() and base_q

    coefficients = {
        (item["item_id"], row["insumo_id"]): Fraction(str(row["coeficiente"]))
        for item in spec["eap"]
        for cpu in spec["fixture_cpus"]
        if cpu["codigo"] == item["cpu_id"]
        for row in cpu["composicao_itens"]
    }
    for key, quantity in base_q.items():
        # Both runs may differ from Q by the physical tolerance (Σq = Q ± Q_TOL).
        bound = coefficients[key] * 2 * Q_TOL
        assert abs(half_q[key] - quantity / 2) <= bound, key
        unit_cost = base_v[key] / quantity
        assert abs(half_v[key] - base_v[key] / 2) <= unit_cost * bound, key


def _plant(canonical):
    for contract in canonical.contratos_recurso:
        witness = contract.p16_global_assignment or {}
        if witness.get("resource_type") == PLANT:
            return witness
    raise AssertionError(f"{PLANT} contract missing")


def _gap_spec(gap: int) -> dict:
    spec = scenario("sharing_theta_standby_remob")
    tariffs = spec["skill_inputs"]["05-equipes-e-alocacao"]["rcpsp_spec"]["p16_exact_tariffs"]
    tariffs[PLANT].update(max_idle_gap=gap, gap_max_viavel=gap)
    return spec


def test_idle_gap_toggles_plant_perpetuation_exactly_at_threshold(runs) -> None:
    at, _report, _spec = runs("gap_1", _gap_spec(1))
    below, _report, _spec = runs("gap_0", _gap_spec(0))
    at_plant, below_plant = _plant(at), _plant(below)

    # Same physical demand with a one-week hole: the decision is only the bridge.
    assert at_plant["demand"] == below_plant["demand"]
    demand = [int(d) for d in at_plant["demand"]]
    nonzero = [j for j, d in enumerate(demand) if d]
    holes = [j for j in range(nonzero[0], nonzero[-1] + 1) if demand[j] == 0]
    assert len(holes) == 1

    tariff = at_plant["tariff"]
    movement = Fraction(tariff["mobilize"]) + Fraction(tariff["demobilize"])
    assert (at_plant["tariff"]["max_idle_gap_effective"], below_plant["tariff"]["max_idle_gap_effective"]) == (1, 0)

    # gap = threshold: one hire bridges the hole on standby.
    assert len(at_plant["chains"]) == 1
    assert Fraction(at_plant["costs"]["standby"]) > 0
    assert Fraction(at_plant["costs"]["mobility"]) == movement
    # gap > threshold: release and remobilise, no standby.
    assert len(below_plant["chains"]) == 2
    assert Fraction(below_plant["costs"]["standby"]) == 0
    assert Fraction(below_plant["costs"]["mobility"]) == 2 * movement
    # Removing an option cannot make the optimal pool cheaper.
    assert Fraction(below_plant["costs"]["pool_total"]) >= Fraction(at_plant["costs"]["pool_total"])
