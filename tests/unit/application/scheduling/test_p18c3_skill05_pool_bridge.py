"""P18-C3: reconstruct Skill05 exact pool postings from persisted P16 witnesses."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import book_exact_pool
from concilium.application.scheduling.resource_level_contracts import (
    ExactPoolResult,
    InstanceChain,
    ResourceContractLedger,
    ResourceTariff,
)
from concilium.application.scheduling.skill06_p18c_consumption_preview import (
    _validate_catalog_currency,
    build_skill05_exact_pool_ledger,
)
from concilium.domain.models.canonical import CanonicalModel, RecursoContrato
from concilium.domain.services.planning.week_sequence import enumerar_semanas


def _contract_and_witness() -> RecursoContrato:
    weeks = tuple(enumerar_semanas("2026-W01", "2026-W02"))
    tariff = ResourceTariff(F(5), F(1), F(30), F(30), 1)
    physical = ResourceContractLedger(
        resource_type="CRANE",
        demand=(1, 1),
        presence=(1, 1),
        standby=(0, 0),
        chains=(InstanceChain("CRANE", 1, 0, 2, 2, 0, (0, 1)),),
        active_cost=F(10),
        standby_cost=F(0),
        mobility_cost=F(60),
    )
    pool = ExactPoolResult(
        calendar_weeks=weeks,
        ledgers=(physical,),
        proof_scope="EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
    )
    booked = book_exact_pool(pool, {"CRANE": tariff}, {"CRANE": "EQ"})
    witness = {
        "schema": "p16-global-instance-assignment/v1",
        "proof_scope": pool.proof_scope,
        "status": "EXACT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
        "is_project_go_certificate": False,
        "legacy_financial_projection_overridden": False,
        "resource_type": "CRANE",
        "contract_id": "contract-crane",
        "source_id": "tariff-crane-v1",
        "currency": "BRL",
        "category": "EQ",
        "tariff": {
            "active_week": "5",
            "idle_week": "1",
            "mobilize": "30",
            "demobilize": "30",
            "max_idle_gap_declared": 1,
            "gap_max_viavel": 1,
            "gap_max_economico_legado": 1,
            "max_idle_gap_effective": 1,
        },
        "calendar_weeks": list(weeks),
        "demand_by_activity": {"A": [1, 1]},
        "demand": [1, 1],
        "presence": [1, 1],
        "standby": [0, 0],
        "chains": [{
            "instance_id": 1,
            "start_index": 0,
            "end_exclusive_index": 2,
            "start_week": weeks[0],
            "end_week": weeks[-1],
            "active_week_indices": [0, 1],
            "active_weeks": 2,
            "idle_weeks": 0,
            "active_weeks_iso": list(weeks),
            "activity_by_week": {weeks[0]: "A", weeks[1]: "A"},
        }],
        "costs": {
            "active": str(F(10)),
            "standby": str(F(0)),
            "mobility": str(F(60)),
            "pool_total": str(F(70)),
        },
        "exclusive_ledger": {
            "contractual_k": str(booked.contractual_k),
            "consumable_v": str(booked.consumable_v),
            "indirect": str(booked.indirect),
            "direct": str(booked.direct),
            "total": str(booked.total),
            "postings": [
                {
                    "event_id": list(post.event_id),
                    "nature": post.nature.value,
                    "category": post.category,
                    "amount": str(post.amount),
                    "source": post.source,
                    "week": post.week,
                }
                for post in booked.postings
            ],
        },
    }
    return RecursoContrato(
        contrato_id="contract-crane",
        tipo_id="CRANE",
        quantidade_contratada=1,
        semana_inicio=weeks[0],
        semana_fim=weeks[-1],
        semanas_contrato=2,
        custo_unit_semanal=5,
        custo_total_contrato=10,
        items_cobertos=["A"],
        p16_global_assignment=witness,
    )


def _canonical(contract: RecursoContrato) -> CanonicalModel:
    return CanonicalModel.model_construct(
        contratos_recurso=[contract],
        recurso_pool=[],
        instancias_recurso=[],
    )


def test_reconstructs_exact_skill05_pool_and_financial_ownership() -> None:
    ledger = build_skill05_exact_pool_ledger(_canonical(_contract_and_witness()))
    assert ledger.contractual_k == F(10)
    assert ledger.consumable_v == F(0)
    assert ledger.indirect == F(60)
    assert ledger.total == F(70)
    assert len(ledger.postings) == 4


def test_missing_p16_e_witness_fails_closed() -> None:
    contract = _contract_and_witness().model_copy(update={"p16_global_assignment": None})
    with pytest.raises(ValueError, match="missing exact P16-E witness"):
        build_skill05_exact_pool_ledger(_canonical(contract))


def test_tampered_persisted_pool_posting_fails_closed() -> None:
    contract = _contract_and_witness()
    witness = contract.p16_global_assignment
    assert witness is not None
    changed = dict(witness)
    stored = dict(changed["exclusive_ledger"])
    rows = [dict(row) for row in stored["postings"]]
    rows[0]["amount"] = "999"
    stored["postings"] = rows
    changed["exclusive_ledger"] = stored
    contract = contract.model_copy(update={"p16_global_assignment": changed})
    with pytest.raises(ValueError, match="postings do not match"):
        build_skill05_exact_pool_ledger(_canonical(contract))


def test_tampered_per_activity_demand_fails_closed() -> None:
    contract = _contract_and_witness()
    witness = dict(contract.p16_global_assignment or {})
    witness["demand_by_activity"] = {"A": [0, 2]}
    contract = contract.model_copy(update={"p16_global_assignment": witness})
    with pytest.raises(ValueError, match="per-activity demand"):
        build_skill05_exact_pool_ledger(_canonical(contract))

def test_tampered_cost_component_fails_even_when_pool_total_is_unchanged() -> None:
    contract = _contract_and_witness()
    witness = dict(contract.p16_global_assignment or {})
    costs = dict(witness["costs"])
    costs["active"] = "9"
    costs["mobility"] = "61"
    witness["costs"] = costs
    contract = contract.model_copy(update={"p16_global_assignment": witness})
    with pytest.raises(ValueError, match="cost components differ"):
        build_skill05_exact_pool_ledger(_canonical(contract))

def test_catalog_currency_must_be_explicit_and_match_pool_currency() -> None:
    contract = _contract_and_witness()
    canonical = _canonical(contract)
    with pytest.raises(ValueError, match="catalog price currency"):
        _validate_catalog_currency(canonical, {})
    with pytest.raises(ValueError, match="differs from the exact Skill05 pool currency"):
        _validate_catalog_currency(canonical, {"currency": "USD"})
    assert _validate_catalog_currency(canonical, {"currency": "BRL"}) == "BRL"


def test_activity_week_assignment_must_match_p16_per_activity_demand() -> None:
    contract = _contract_and_witness()
    witness = dict(contract.p16_global_assignment or {})
    witness["demand_by_activity"] = {"A": [1, 0], "B": [0, 1]}
    contract = contract.model_copy(update={"p16_global_assignment": witness})
    with pytest.raises(ValueError, match="do not reconstruct per-activity demand"):
        build_skill05_exact_pool_ledger(_canonical(contract))

def test_witness_cannot_assign_more_instance_ids_than_contract_capacity() -> None:
    contract = _contract_and_witness()
    witness = dict(contract.p16_global_assignment or {})
    rows = [dict(row) for row in witness["chains"]]
    rows[0]["instance_id"] = contract.quantidade_contratada + 1
    witness["chains"] = rows
    contract = contract.model_copy(update={"p16_global_assignment": witness})
    with pytest.raises(ValueError, match="over-contracted"):
        build_skill05_exact_pool_ledger(_canonical(contract))
