"""P16-E: the actual Skill 05 runtime persists a bounded exact instance-path witness."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import concilium.application.skills as skills
from concilium.domain.models.canonical import RecursoContrato

_ = skills.run_equipes_e_alocacao
helpers = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]
builder = sys.modules[helpers.__name__ + "._resource_instance_build"]


WEEKS = ("2026-W01", "2026-W02", "2026-W03", "2026-W04")


def _case(*, tariff_overrides: dict | None = None):
    per_item = {
        "A": {"2026-W01": 1, "2026-W02": 1, "2026-W04": 1},
        "B": {"2026-W01": 1, "2026-W03": 1, "2026-W04": 1},
    }
    fronts = {
        "A": {"2026-W01": 1, "2026-W02": 1, "2026-W04": 1},
        "B": {"2026-W01": 1, "2026-W03": 1, "2026-W04": 1},
    }
    contract = RecursoContrato(
        contrato_id="contract-crane",
        tipo_id="CRANE",
        quantidade_contratada=2,
        semana_inicio=WEEKS[0],
        semana_fim=WEEKS[-1],
        semanas_contrato=4,
        custo_unit_semanal=5,
        custo_total_contrato=40,
        items_cobertos=["A", "B"],
        demanda_fisica_semanal={
            "2026-W01": 2, "2026-W02": 1, "2026-W03": 1, "2026-W04": 2,
        },
        demanda_por_item_semanal=per_item,
        frentes_por_item_semanal=fronts,
        gap_max_economico=1,
        custo_mob_unit=20,
        custo_demob_unit=10,
        custo_idle_semanal_unit=1,
    )
    spec = {
        "activities": [
            {"item_id": "A", "required_resources": {"CRANE": 1}},
            {"item_id": "B", "required_resources": {"CRANE": 1}},
        ],
        "p16_exact_tariffs": {
            "CRANE": {
                "active_week": "5",
                "idle_week": "1",
                "mobilize": "20",
                "demobilize": "10",
                "max_idle_gap": 1,
                "gap_max_viavel": 1,
                "source_id": "contract:CRANE:2026",
                "currency": "BRL",
                "category": "EQ",
            },
        },
    }
    if tariff_overrides:
        spec["p16_exact_tariffs"]["CRANE"].update(tariff_overrides)
    schedules = {
        "A": SimpleNamespace(distribuicao_semanal={
            "2026-W01": SimpleNamespace(num_equipes=1),
            "2026-W02": SimpleNamespace(num_equipes=1),
            "2026-W04": SimpleNamespace(num_equipes=1),
        }),
        "B": SimpleNamespace(distribuicao_semanal={
            "2026-W01": SimpleNamespace(num_equipes=1),
            "2026-W03": SimpleNamespace(num_equipes=1),
            "2026-W04": SimpleNamespace(num_equipes=1),
        }),
    }
    return contract, spec, schedules


def test_skill05_persists_global_p16_witness_and_reconciles_exact_ledger() -> None:
    contract, spec, schedules = _case()
    instances, compositions, summaries = builder._build_instancias_recurso(
        [contract], spec, schedules, [],
    )

    witness = contract.p16_global_assignment
    assert witness is not None
    assert witness["schema"] == "p16-global-instance-assignment/v1"
    assert witness["proof_scope"] == "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND"
    assert witness["is_project_go_certificate"] is False
    assert witness["legacy_financial_projection_overridden"] is False
    assert witness["demand"] == [2, 1, 1, 2]
    assert witness["presence"] == [2, 2, 2, 2]
    assert witness["standby"] == [0, 1, 1, 0]
    assert witness["tariff"]["gap_max_viavel"] == 1
    assert witness["tariff"]["max_idle_gap_effective"] == 1
    assert witness["costs"] == {
        "active": "30", "standby": "2", "mobility": "60", "pool_total": "92",
    }
    assert witness["exclusive_ledger"]["contractual_k"] == "32"
    assert witness["exclusive_ledger"]["indirect"] == "60"
    assert witness["exclusive_ledger"]["total"] == "92"
    assert len(witness["chains"]) == 2
    assert {
        tuple(chain["active_week_indices"]) for chain in witness["chains"]
    } == {(0, 1, 3), (0, 2, 3)}

    # One instance event is assigned to each active chain in each physical week.
    assigned = {
        week: [
            chain["activity_by_week"][week]
            for chain in witness["chains"]
            if week in chain["activity_by_week"]
        ]
        for week in WEEKS
    }
    assert {week: len(activity_ids) for week, activity_ids in assigned.items()} == {
        "2026-W01": 2, "2026-W02": 1, "2026-W03": 1, "2026-W04": 2,
    }
    assert len(instances) == 2
    assert len(compositions) == 2
    assert len(summaries) == 1

    # The exact witness survives canonical serialization, separate from legacy costs.
    stored = RecursoContrato.model_validate(contract.model_dump(mode="json"))
    assert stored.p16_global_assignment == witness
    assert contract.custo_total_contrato == 40


def test_declared_p16_tariff_rejects_float_rate_instead_of_rounding_it() -> None:
    contract, spec, schedules = _case(tariff_overrides={"active_week": 5.0})
    with pytest.raises(ValueError, match="active_week must be an exact decimal string"):
        builder._build_instancias_recurso([contract], spec, schedules, [])
    assert contract.p16_global_assignment is None


def test_declared_p16_tariff_requires_full_physical_provenance() -> None:
    contract, spec, schedules = _case()
    contract.frentes_por_item_semanal = {}
    with pytest.raises(ValueError, match="source mobilization m_i,j is required"):
        builder._build_instancias_recurso([contract], spec, schedules, [])


def test_p16_tariff_cannot_name_a_resource_without_a_physical_contract() -> None:
    contract, spec, schedules = _case()
    spec["p16_exact_tariffs"]["UNUSED"] = spec["p16_exact_tariffs"]["CRANE"]
    with pytest.raises(ValueError, match="without a physical contract"):
        builder._build_instancias_recurso([contract], spec, schedules, [])



def test_p16_enforces_explicit_viability_cap_instead_of_legacy_economic_gap() -> None:
    contract, spec, schedules = _case(tariff_overrides={
        "max_idle_gap": 2,
        "gap_max_viavel": 0,
    })
    contract.gap_max_economico = 9999
    builder._build_instancias_recurso([contract], spec, schedules, [])

    witness = contract.p16_global_assignment
    assert witness is not None
    assert witness["tariff"]["max_idle_gap_declared"] == 2
    assert witness["tariff"]["gap_max_viavel"] == 0
    assert witness["tariff"]["gap_max_economico_legado"] == 9999
    assert witness["tariff"]["max_idle_gap_effective"] == 0
    assert all(
        following - preceding == 1
        for chain in witness["chains"]
        for preceding, following in zip(chain["active_week_indices"], chain["active_week_indices"][1:])
    )



def test_p16_tariff_fails_when_no_contracts_exist() -> None:
    _contract, spec, schedules = _case()
    with pytest.raises(ValueError, match="without a physical contract"):
        builder._build_instancias_recurso([], spec, schedules, [])


def test_p16_tariff_rejects_duplicate_homogeneous_contracts() -> None:
    contract, spec, schedules = _case()
    duplicate = contract.model_copy(update={"contrato_id": "contract-crane-duplicate"})
    with pytest.raises(ValueError, match="one homogeneous contract per tariffed resource type"):
        builder._build_instancias_recurso([contract, duplicate], spec, schedules, [])


def test_failed_multitype_p16_call_does_not_leave_partial_witnesses() -> None:
    contract, spec, schedules = _case()
    invalid_second = contract.model_copy(update={
        "contrato_id": "contract-exc",
        "tipo_id": "EXC",
        "frentes_por_item_semanal": {},
    })
    spec["activities"] = [
        {
            **activity,
            "required_resources": {**activity["required_resources"], "EXC": 1},
        }
        for activity in spec["activities"]
    ]
    spec["p16_exact_tariffs"]["EXC"] = dict(spec["p16_exact_tariffs"]["CRANE"])
    validations = []

    with pytest.raises(ValueError, match="source mobilization m_i,j is required"):
        builder._build_instancias_recurso(
            [contract, invalid_second], spec, schedules, validations,
        )

    assert contract.p16_global_assignment is None
    assert invalid_second.p16_global_assignment is None
    assert contract.mobilizacao_por_instancia == {}
    assert invalid_second.mobilizacao_por_instancia == {}
    assert validations == []
