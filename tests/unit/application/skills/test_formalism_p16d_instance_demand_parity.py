"""P16-D: instance allocation MUST consume the exact typed a_i,g(m_ij) tensor.

An unrelated worker resource must never reduce the machine demand or cost.
All checks use *physically scheduled* integer fronts and persisted typed demand;
no F(m), climate, practicability or calendar efficiency can modify resource count.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import concilium.application.skills as skills
from concilium.domain.models.canonical import RecursoContrato

_ = skills.run_equipes_e_alocacao
helpers = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]
builder = sys.modules[helpers.__name__ + "._resource_instance_build"]


def _case(
    *,
    demand: tuple[int, int, int] = (1, 2, 3),
    contracted: int = 3,
    weeks: tuple[str, str, str] = ("2020-W52", "2020-W53", "2021-W01"),
):
    activities = [{
        "item_id": "A",
        "required_resources": {"MAQ": 3, "OPERADORES": 6},
    }]
    physical = dict(zip(weeks, demand, strict=True))
    contract = RecursoContrato(
        contrato_id="contrato-maq",
        tipo_id="MAQ",
        quantidade_contratada=contracted,
        semana_inicio=weeks[0],
        semana_fim=weeks[-1],
        semanas_contrato=3,
        custo_unit_semanal=100,
        custo_total_contrato=contracted * 300,
        items_cobertos=["A"],
        demanda_fisica_semanal=physical,
        demanda_por_item_semanal={"A": physical},
        frentes_por_item_semanal={
            "A": dict(zip(weeks, (1, 2, 3), strict=True))
        },
    )
    sched = SimpleNamespace(
        distribuicao_semanal={
            week: SimpleNamespace(num_equipes=fronts)
            for week, fronts in zip(weeks, (1, 2, 3), strict=True)
        }
    )
    return contract, {"activities": activities}, {"A": sched}


def test_instances_use_exact_weekly_machine_counts_not_sums_of_other_types() -> None:
    contract, spec, schedules = _case()
    instances, compositions, summaries = builder._build_instancias_recurso(
        [contract], spec, schedules, [],
    )
    assert len(instances) == 3
    assert sum(instance.semanas_ativas for instance in instances) == 6
    assert sorted(instance.semanas_ativas for instance in instances) == [1, 2, 3]
    assert len(compositions) == 1
    assert compositions[0].machine_weeks == 6
    assert summaries[0].machine_weeks_usados == 6


def test_inconsistent_contract_demand_fails_before_instance_assignment() -> None:
    contract, spec, schedules = _case()
    contract.demanda_fisica_semanal["2020-W53"] = 3
    with pytest.raises(ValueError, match="VAL-POOL-DEMANDA-02"):
        builder._build_instancias_recurso([contract], spec, schedules, [])


def test_overload_fails_instead_of_silently_truncating_instances() -> None:
    contract, spec, schedules = _case(contracted=2)
    with pytest.raises(ValueError, match="exceeds contracted instance slots"):
        builder._build_instancias_recurso([contract], spec, schedules, [])


def test_schedule_change_invalidates_stale_typed_contract() -> None:
    contract, spec, schedules = _case()
    schedules["A"].distribuicao_semanal["2020-W53"].num_equipes = 0
    with pytest.raises(ValueError, match="incomplete weeks"):
        builder._build_instancias_recurso([contract], spec, schedules, [])


def test_unverified_legacy_instance_derivation_emits_warning_not_certificate() -> None:
    contract, spec, schedules = _case()
    contract.demanda_fisica_semanal = {}
    contract.demanda_por_item_semanal = {}
    validations = []
    builder._build_instancias_recurso([contract], spec, schedules, validations)
    assert any(v.codigo == "VAL-POOL-DEMANDA-LEGADO" and v.status == "AVISO" for v in validations)


def test_contract_schema_retains_exact_physical_provenance() -> None:
    contract, _, _ = _case()
    stored = RecursoContrato.model_validate(contract.model_dump())
    assert stored.demanda_fisica_semanal["2020-W53"] == 2
    assert stored.demanda_por_item_semanal["A"]["2021-W01"] == 3
    assert stored.frentes_por_item_semanal["A"]["2020-W53"] == 2


def test_changed_front_count_same_weeks_rejects_stale_contract() -> None:
    contract, spec, schedules = _case()
    schedules["A"].distribuicao_semanal["2020-W53"].num_equipes = 3
    with pytest.raises(ValueError, match="stale mobilization"):
        builder._build_instancias_recurso([contract], spec, schedules, [])


def test_calendar_and_practicability_dont_reduce_physical_resource_demand() -> None:
    contract, spec, schedules = _case()
    for week in schedules["A"].distribuicao_semanal.values():
        week.praticabilidade = 0.25
        week.calendario = 0.50
    instances, _compositions, summaries = builder._build_instancias_recurso(
        [contract], spec, schedules, [],
    )
    assert sum(instance.semanas_ativas for instance in instances) == 6
    assert summaries[0].machine_weeks_usados == 6


def test_missing_mobilization_provenance_is_explicitly_uncertified() -> None:
    contract, spec, schedules = _case()
    contract.frentes_por_item_semanal = {}
    validations = []
    builder._build_instancias_recurso([contract], spec, schedules, validations)
    assert any(
        v.codigo == "VAL-POOL-FRENTES-LEGADO" and v.status == "AVISO"
        for v in validations
    )


def test_missing_active_activity_fails_even_if_existing_aggregate_is_self_consistent() -> None:
    contract, spec, schedules = _case()
    spec["activities"].append(
        {"item_id": "B", "required_resources": {"MAQ": 1}}
    )
    schedules["B"] = SimpleNamespace(
        distribuicao_semanal={"2020-W52": SimpleNamespace(num_equipes=1)}
    )
    with pytest.raises(ValueError, match="missing mobilized activity B/MAQ"):
        builder._build_instancias_recurso([contract], spec, schedules, [])
