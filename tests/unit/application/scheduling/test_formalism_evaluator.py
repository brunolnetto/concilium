from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from types import SimpleNamespace

import pytest

from concilium.application.scheduling.formalism_evaluator import (
    REQUIRED_GATES,
    ProductivityRateWitness,
    evaluate_formalism_certificate,
    evaluate_project_evidence,
    gate_evidence_from_status,
)
from concilium.domain.models.formalism_certificate import (
    REQUIRED_SOURCES,
    build_provisional_certificate,
)


def _envelope(scope: str = "RFP"):
    sources = {name: {"source": name, "version": 1} for name in REQUIRED_SOURCES}
    return build_provisional_certificate(
        project_id="project-1",
        run_id="run-001",
        scope=scope,
        formalism_sha256="a" * 64,
        oracle_sha256="b" * 64,
        sources=sources,
    )


def _all_pass(envelope):
    return tuple(
        gate_evidence_from_status(
            envelope, gate_id, "PASS", observed={"checked": True}, expected={"checked": True}
        )
        for gate_id in REQUIRED_GATES
    )


def test_complete_rfp_with_every_gate_and_source_present_is_go() -> None:
    envelope = _envelope()
    result = evaluate_formalism_certificate(envelope, _all_pass(envelope))
    assert result.decision == "GO"
    assert tuple(item.gate_id for item in result.gate_evidence) == REQUIRED_GATES
    assert len(result.evaluation_sha256) == 64


@pytest.mark.parametrize("gate_id", [f"V{i}" for i in range(1, 7)])
def test_each_v1_to_v6_falsifier_is_nogo(gate_id: str) -> None:
    envelope = _envelope()
    evidence = list(_all_pass(envelope))
    evidence[REQUIRED_GATES.index(gate_id)] = gate_evidence_from_status(
        envelope, gate_id, "FAIL", reason=f"independent falsifier for {gate_id}",
        observed={"counterexample": gate_id},
    )
    result = evaluate_formalism_certificate(envelope, evidence)
    assert result.decision == "NOGO"
    assert any(gate_id in reason for reason in result.reasons)


@pytest.mark.parametrize(
    "gate_id",
    ["FINANCIAL_COST_RECONCILIATION", "PRICE_PRESENT", "REGULATORY_BDI_BASIS", "PROFITABILITY"],
)
def test_financial_falsifiers_are_nogo_with_gate_reason(gate_id: str) -> None:
    envelope = _envelope()
    evidence = list(_all_pass(envelope))
    evidence[REQUIRED_GATES.index(gate_id)] = gate_evidence_from_status(
        envelope, gate_id, "FAIL", reason=f"financial falsifier for {gate_id}",
        observed={"invalid": True},
    )
    result = evaluate_formalism_certificate(envelope, evidence)
    assert result.decision == "NOGO"
    assert any(gate_id in reason for reason in result.reasons)


def test_unknown_missing_gate_unavailable_source_and_rfi_never_become_go() -> None:
    envelope = _envelope()
    evidence = list(_all_pass(envelope))
    evidence[0] = gate_evidence_from_status(
        envelope, "V1", "UNKNOWN", reason="physical witness unavailable"
    )
    assert evaluate_formalism_certificate(envelope, evidence).decision == "NOT_CERTIFIABLE"
    assert evaluate_formalism_certificate(envelope, evidence[1:]).decision == "NOT_CERTIFIABLE"

    missing = {name: None if name == "solver" else {"source": name} for name in REQUIRED_SOURCES}
    unavailable_envelope = build_provisional_certificate(
        project_id="project-1", run_id="run-002", scope="RFP",
        formalism_sha256="a" * 64, oracle_sha256="b" * 64, sources=missing,
    )
    unavailable_gate = gate_evidence_from_status(
        unavailable_envelope, "V6", "PASS", artifact_refs=("solver",)
    )
    assert unavailable_gate.status == "UNKNOWN"
    assert "solver" in (unavailable_gate.reason or "")

    rfi = _envelope("RFI")
    assert evaluate_formalism_certificate(rfi, _all_pass(rfi)).decision == "NOT_CERTIFIABLE"


def test_duplicate_gate_and_cross_snapshot_evidence_are_rejected() -> None:
    envelope = _envelope()
    pass_evidence = _all_pass(envelope)
    with pytest.raises(ValueError, match="duplicate gate"):
        evaluate_formalism_certificate(envelope, [*pass_evidence, pass_evidence[0]])

    sources = {name: {"source": name, "version": 2} for name in REQUIRED_SOURCES}
    other = build_provisional_certificate(
        project_id="project-1", run_id="run-001", scope="RFP",
        formalism_sha256="a" * 64, oracle_sha256="b" * 64, sources=sources,
    )
    mismatched = gate_evidence_from_status(other, "V1", "PASS", artifact_refs=("artifact",))
    with pytest.raises(ValueError, match="different source fingerprints"):
        evaluate_formalism_certificate(envelope, [mismatched])


def test_evaluation_fingerprint_is_stable_for_same_gate_evidence() -> None:
    envelope = _envelope()
    first = evaluate_formalism_certificate(envelope, _all_pass(envelope))
    second = evaluate_formalism_certificate(envelope, _all_pass(envelope))
    assert first.evaluation_sha256 == second.evaluation_sha256


@dataclass(frozen=True)
class _Violation:
    code: str
    item_id: str = "A"
    week: int | None = None
    reason: str = "counterexample"


@dataclass(frozen=True)
class _Audit:
    status: str
    violations: tuple[_Violation, ...] = ()


def _pricing_gates(regulatory: str = "PASS", profitability: str = "PASS", reasons=()):
    return SimpleNamespace(
        regulatory_status=regulatory,
        profitability_status=profitability,
        regulatory_bdi_rate=F("1/5"),
        regulatory_bdi_floor=F("1/10"),
        regulatory_basis_reference="regulatory-v1",
        profit_amount=F("20"),
        realized_margin=F("1/6"),
        reasons=tuple(reasons),
    )


def _financial_reconciliation():
    line = SimpleNamespace(
        event_id=("POOL", "EQ-1", "ACTIVE", "0"),
        nature="CONTRACTUAL_ACTIVE", category="EQ", amount=F("60"),
        source="EQ-1", week="2026-W01",
    )
    attribution = SimpleNamespace(
        event_id=line.event_id, nature=line.nature, category=line.category,
        amount=line.amount, source=line.source, week=line.week,
    )
    ledger = SimpleNamespace(
        postings=(line,), direct=F("60"), indirect=F("20"), total=F("80"),
    )
    week = SimpleNamespace(total=F("80"))
    return SimpleNamespace(
        ledger=ledger, event_attribution=(attribution,), weeks=(week,),
        holding_evidence_present=True,
    )


def _runtime_evidence(envelope):
    schedule_fp = next(x.sha256 for x in envelope.source_fingerprints if x.name == "schedule")
    return {
        "physical_audit": _Audit("PASS"),
        "physical_resolution": {
            "schema": "concilium.p15.physical-resolution.v1",
            "status": "PASS", "audit_status": "PASS", "attempts": 3,
            "complete_search": True, "schedule_sha256": schedule_fp,
            "reason": "bounded feasible witness",
        },
        "pool_summaries": [SimpleNamespace(
            contrato_id="contract-1", tipo_id="EQ-1",
            quantidade_contratada=2, semanas_contrato=5,
            machine_weeks_disponiveis=10, machine_weeks_usados=2,
            machine_weeks_standby=2,
            p16_global_assignment={
                "schema": "p16-global-instance-assignment/v1",
                "proof_scope": "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
                "status": "EXACT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
                "is_project_go_certificate": False,
                "legacy_financial_projection_overridden": False,
                "resource_type": "EQ-1",
                "contract_id": "contract-1",
                "calendar_weeks": ["2026-W01", "2026-W02", "2026-W03", "2026-W04", "2026-W05"],
                "demand": [1, 1, 0, 0, 0],
                "presence": [2, 2, 0, 0, 0],
                "standby": [1, 1, 0, 0, 0],
                "demand_by_activity": {"A": [1, 1, 0, 0, 0]},
            },
        )],
        "productivity_witnesses": [ProductivityRateWitness(
            activity_id="A", hourly_rate="12", origin="GRAFO_FLUXO",
            source_reference="production-catalog-v1", calibration_reference="calibration-v1",
        )],
        "expected_activity_ids": ["A"],
        "financial_reconciliation": _financial_reconciliation(),
        "pricing_diagnostics": SimpleNamespace(
            operational_price=F("100"), total_cost=F("80"), profit_amount=F("20"),
            inventory_scope_status="COMPLETE",
            inventory_scope_source="inventory-fixture",
            inventory_scope_reference_id="inventory-v1",
            inventory_scope_fingerprint="d" * 64,
        ),
        "pricing_gates": _pricing_gates(),
    }


def test_runtime_adapter_uses_p15_p16_p20_p21_witnesses_and_goes_only_when_all_pass() -> None:
    envelope = _envelope()
    result = evaluate_project_evidence(envelope, **_runtime_evidence(envelope))
    assert result.decision == "GO"


def test_runtime_adapter_rejects_stale_p15_schedule_and_arbitrary_productivity() -> None:
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["physical_resolution"] = {
        **inputs["physical_resolution"], "schedule_sha256": "0" * 64,
    }
    inputs["productivity_witnesses"] = [ProductivityRateWitness(
        activity_id="A", hourly_rate="12", origin="FALLBACK_ARBITRARIO",
        source_reference="legacy", calibration_reference="legacy",
    )]
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOGO"
    assert any("V6" in reason for reason in result.reasons)
    assert any("PRODUCTIVITY_PROVENANCE" in reason for reason in result.reasons)


def test_positive_standby_is_not_a_v3_failure_but_missing_bdi_and_negative_profit_are_nogo() -> None:
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    # P16 exact ledger: 4 active MW + 6 standby MW = 10 deployed MW;
    # declared contractual availability is 20 MW. Positive standby is lawful.
    witness = {
        "schema": "p16-global-instance-assignment/v1",
        "proof_scope": "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
        "status": "EXACT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
        "is_project_go_certificate": False,
        "legacy_financial_projection_overridden": False,
        "resource_type": "EQ-1",
        "contract_id": "contract-1",
        "calendar_weeks": ["2026-W01", "2026-W02"],
        "demand": [2, 2],
        "presence": [5, 5],
        "standby": [3, 3],
        "demand_by_activity": {"A": [2, 2]},
    }
    inputs["pool_summaries"] = [SimpleNamespace(
        contrato_id="contract-1", tipo_id="EQ-1",
        quantidade_contratada=10, semanas_contrato=2,
        machine_weeks_disponiveis=20, machine_weeks_usados=4,
        machine_weeks_standby=6, p16_global_assignment=witness,
    )]
    inputs["pricing_gates"] = _pricing_gates(
        regulatory="UNKNOWN", profitability="FAIL",
        reasons=("regulatory BDI basis is missing", "operational price does not exceed total cost"),
    )
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOGO"
    gates = {row.gate_id: row for row in result.gate_evidence}
    assert gates["V3"].status == "PASS"
    assert gates["REGULATORY_BDI_BASIS"].status == "FAIL"
    assert gates["PROFITABILITY"].status == "FAIL"


def test_v3_rejects_forged_weekly_standby_identity_and_missing_p16_witness() -> None:
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    witness = {
        "schema": "p16-global-instance-assignment/v1",
        "proof_scope": "EXACT_GLOBAL_INSTANCE_ASSIGNMENT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
        "status": "EXACT_CONDITIONAL_ON_FIXED_PHYSICAL_DEMAND",
        "is_project_go_certificate": False,
        "legacy_financial_projection_overridden": False,
        "resource_type": "EQ-1",
        "contract_id": "contract-1",
        "calendar_weeks": ["2026-W01", "2026-W02"],
        "demand": [2, 2],
        "presence": [5, 5],
        "standby": [3, 2],
        "demand_by_activity": {"A": [2, 2]},
    }
    inputs["pool_summaries"] = [SimpleNamespace(
        contrato_id="contract-1", tipo_id="EQ-1",
        quantidade_contratada=10, semanas_contrato=2,
        machine_weeks_disponiveis=20, machine_weeks_usados=4,
        machine_weeks_standby=5, p16_global_assignment=witness,
    )]
    result = evaluate_project_evidence(envelope, **inputs)
    v3 = next(row for row in result.gate_evidence if row.gate_id == "V3")
    assert v3.status == "FAIL"
    assert "presence" in (v3.reason or "")

    inputs["pool_summaries"] = [SimpleNamespace(
        contrato_id="contract-1", tipo_id="EQ-1",
        quantidade_contratada=10, semanas_contrato=2,
        machine_weeks_disponiveis=20, machine_weeks_usados=4,
        machine_weeks_standby=6,
    )]
    result = evaluate_project_evidence(envelope, **inputs)
    v3 = next(row for row in result.gate_evidence if row.gate_id == "V3")
    assert v3.status == "UNKNOWN"
    assert "witness" in (v3.reason or "")


def test_runtime_adapter_fails_duplicate_event_ownership() -> None:
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    reconciliation = inputs["financial_reconciliation"]
    duplicate = reconciliation.ledger.postings[0]
    reconciliation.ledger.postings = (duplicate, duplicate)
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOGO"
    gate = next(x for x in result.gate_evidence if x.gate_id == "FINANCIAL_COST_RECONCILIATION")
    assert gate.status == "FAIL"
    assert "duplicate" in (gate.reason or "")


def test_missing_regulatory_basis_is_nogo_for_rfp_not_a_zero_bdi_pass() -> None:
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["pricing_gates"] = _pricing_gates(
        regulatory="UNKNOWN", reasons=("regulatory BDI basis is missing",),
    )
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOGO"
    gate = next(x for x in result.gate_evidence if x.gate_id == "REGULATORY_BDI_BASIS")
    assert gate.status == "FAIL"


def _persisted_financial_reconciliation():
    return {
        "schema": "concilium.p20.financial-reconciliation.v1",
        "authority": "FINANCIAL_SOURCES_RECONCILED_PREVIEW_NOT_PROJECT_GO",
        "contract_scope": "EXACT_FIXED_PHYSICAL_POOL_AND_DECLARED_PURCHASES",
        "holding_evidence_present": True,
        "postings": [
            {"event_id": ["POOL", "EQ-1", "ACTIVE", "0"], "nature": "CONTRACTUAL_ACTIVE", "category": "EQ", "amount": "60", "source": "EQ-1", "week": "2026-W01"},
            {"event_id": ["STOCK", "IND-1"], "nature": "INDIRECT", "category": "IND", "amount": "20", "source": "IND-1", "week": "2026-W01"},
        ],
        "event_attribution": [
            {"event_id": ["POOL", "EQ-1", "ACTIVE", "0"], "nature": "CONTRACTUAL_ACTIVE", "category": "EQ", "amount": "60", "source": "EQ-1", "week": "2026-W01", "owner_scope": "INSTANCE", "owner_id": ["EQ-1"]},
            {"event_id": ["STOCK", "IND-1"], "nature": "INDIRECT", "category": "IND", "amount": "20", "source": "IND-1", "week": "2026-W01", "owner_scope": "SOURCE", "owner_id": ["IND-1"]},
        ],
        "weekly_balances": [{"week": "2026-W01", "contractual_k": "60", "consumable_v": "0", "indirect": "20"}],
        "weekly_category_balances": [
            {"week": "2026-W01", "category": "EQ", "amount": "60"},
            {"week": "2026-W01", "category": "IND", "amount": "20"},
        ],
        "totals": {"contractual_k": "60", "consumable_v": "0", "direct": "60", "indirect": "20", "total": "80"},
    }


def _persisted_pricing():
    return {
        "schema": "concilium.p21.pricing-diagnostics.v1",
        "operational_price": "100", "total_cost": "80", "profit_amount": "20",
        "operational_basis_fingerprint": "c" * 64,
        "inventory_scope_status": "COMPLETE",
        "inventory_scope_source": "inventory-fixture",
        "inventory_scope_reference_id": "inventory-v1",
        "inventory_scope_fingerprint": "d" * 64,
    }


def _persisted_pricing_gates():
    return {
        "schema": "concilium.p21.pricing-gates.v1",
        "status": "PASS", "regulatory_status": "PASS", "profitability_status": "PASS",
        "regulatory_bdi_rate": "1/5", "regulatory_bdi_floor": "1/10",
        "regulatory_basis_reference": "regulatory-v1", "profit_amount": "20",
        "realized_margin": "1/5", "reasons": "",
    }


def test_persisted_p20_and_p21_json_are_replayed_without_domain_objects():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["financial_reconciliation"] = _persisted_financial_reconciliation()
    inputs["pricing_diagnostics"] = _persisted_pricing()
    inputs["pricing_gates"] = _persisted_pricing_gates()
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "GO"


def test_p15_feasible_but_incomplete_search_cannot_certify_go():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["physical_resolution"] = {
        **inputs["physical_resolution"], "complete_search": False,
    }
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOT_CERTIFIABLE"
    gate = next(x for x in result.gate_evidence if x.gate_id == "V6")
    assert gate.status == "UNKNOWN"


def test_persisted_p20_duplicate_or_modified_financial_source_is_nogo():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    reconciliation = _persisted_financial_reconciliation()
    reconciliation["postings"].append(dict(reconciliation["postings"][0]))
    inputs["financial_reconciliation"] = reconciliation
    inputs["pricing_diagnostics"] = _persisted_pricing()
    inputs["pricing_gates"] = _persisted_pricing_gates()
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOGO"
    gate = next(x for x in result.gate_evidence if x.gate_id == "FINANCIAL_COST_RECONCILIATION")
    assert gate.status == "FAIL"


def test_infeasible_bounded_search_is_v6_nogo_without_falsely_failing_v1():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["physical_resolution"] = {
        **inputs["physical_resolution"],
        "status": "FAIL",
        "audit_status": "FAIL",
        "complete_search": True,
        "violation_details": [],
        "reason": "all declared candidate starts exhausted without a feasible calendar",
    }
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOGO"
    gates = {row.gate_id: row for row in result.gate_evidence}
    assert gates["V1"].status == "UNKNOWN"
    assert gates["V6"].status == "FAIL"


def test_post_materialization_pool_conflict_is_attributed_to_v6_only():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["physical_resolution"] = {
        **inputs["physical_resolution"],
        "status": "FAIL",
        "audit_status": "FAIL",
        "complete_search": True,
        "violation_details": ["V6_POOL_OVERBOOKED:VAL-POOL-01:resource exceeds capacity"],
        "reason": "post-materialization resource pool violation",
    }
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOGO"
    gates = {row.gate_id: row for row in result.gate_evidence}
    assert gates["V1"].status == "PASS"
    assert gates["V6"].status == "FAIL"


def test_assumed_per_front_productivity_without_independent_calibration_is_unknown():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["productivity_witnesses"] = [ProductivityRateWitness(
        activity_id="A", hourly_rate="12", origin="TAXA_POR_FRENTE_ASSUMIDA",
        source_reference="declared-assumption", calibration_reference="unverified-calibration-id",
    )]
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOT_CERTIFIABLE"
    gates = {row.gate_id: row for row in result.gate_evidence}
    assert gates["V5"].status == "UNKNOWN"
    assert gates["PRODUCTIVITY_PROVENANCE"].status == "UNKNOWN"


def test_missing_inventory_scope_prevents_financial_go():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["pricing_diagnostics"] = SimpleNamespace(
        operational_price=F("100"), total_cost=F("80"), profit_amount=F("20"),
    )
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "NOT_CERTIFIABLE"
    gate = next(x for x in result.gate_evidence if x.gate_id == "FINANCIAL_COST_RECONCILIATION")
    assert gate.status == "UNKNOWN"
    assert "inventory scope" in (gate.reason or "")


def test_explicit_no_inventory_scope_is_valid_without_p19_holding_journal():
    envelope = _envelope()
    inputs = _runtime_evidence(envelope)
    inputs["financial_reconciliation"].holding_evidence_present = False
    inputs["pricing_diagnostics"].inventory_scope_status = "NO_INVENTORY"
    result = evaluate_project_evidence(envelope, **inputs)
    assert result.decision == "GO"
