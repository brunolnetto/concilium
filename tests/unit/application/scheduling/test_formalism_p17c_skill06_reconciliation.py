"""P17-C: Skill06 exact K/V reconciliation without changing legacy finance."""
from __future__ import annotations

from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.skill06_p17_cost_reconciliation import (
    build_skill06_p17_reconciliation,
)
from concilium.domain.models.canonical import (
    AtividadeCustoCompleto,
    CanonicalModel,
    CustoDiretoSemanalAtividade,
    RecursoContrato,
)


def _pool() -> ExclusiveCostLedger:
    return ExclusiveCostLedger((
        CostPosting(("POOL", "CRANE", "1", "0", "3", "CONTRACTUAL_ACTIVE", "0"),
                    PostingNature.ACTIVE, "EQ", F(5), "CRANE", "2026-W01"),
        CostPosting(("POOL", "CRANE", "1", "0", "3", "CONTRACTUAL_IDLE", "1"),
                    PostingNature.IDLE, "EQ", F(2), "CRANE", "2026-W02"),
        CostPosting(("POOL", "CRANE", "1", "0", "3", "CONTRACTUAL_ACTIVE", "2"),
                    PostingNature.ACTIVE, "EQ", F(5), "CRANE", "2026-W03"),
        CostPosting(("POOL", "CRANE", "1", "0", "3", "MOB"),
                    PostingNature.MOBILIZATION, "IND", F(30), "CRANE", "2026-W01"),
        CostPosting(("POOL", "CRANE", "1", "0", "3", "DEMOB"),
                    PostingNature.DEMOBILIZATION, "IND", F(30), "CRANE", "2026-W03"),
    ))


def _preview() -> dict[str, object]:
    ledger = _pool()
    postings = [
        {
            "event_id": list(post.event_id), "nature": post.nature.value,
            "category": post.category, "amount": str(post.amount),
            "source": post.source, "week": post.week,
        }
        for post in ledger.postings
    ]
    acquisition = CostPosting(
        ("CONSUMABLE", "invoice-1"), PostingNature.ACQUISITION,
        "COMB", F(3), "DIESEL", "2026-W02",
    )
    postings.append({
        "event_id": list(acquisition.event_id), "nature": acquisition.nature.value,
        "category": acquisition.category, "amount": str(acquisition.amount),
        "source": acquisition.source, "week": acquisition.week,
    })
    return {
        "schema": "concilium.p18.skill06-preview.v1",
        "authority": "P18_SKILL06_READ_ONLY_PREVIEW_NOT_PROJECT_GO",
        "project_go_authorized": False,
        "currency": "BRL", "currency_source": "catalog_metadata.json",
        "totals": {
            "contractual_k": "12", "consumable_v": "3", "indirect": "60",
            "direct": "15", "total": "75",
        },
        "exclusive_postings": postings,
    }


def _canonical(*, diagnostic_mo_eq: float = 36.0) -> CanonicalModel:
    witness = {
        "resource_type": "CRANE", "contract_id": "C1", "currency": "BRL",
        "calendar_weeks": ["2026-W01", "2026-W02", "2026-W03"],
        "tariff": {"active_week": "5"},
        "demand_by_activity": {"A": [1, 0, 1]},
        "chains": [{
            "active_week_indices": [0, 2],
            "activity_by_week": {"2026-W01": "A", "2026-W03": "A"},
        }],
        "costs": {"active": "10", "standby": "2", "mobility": "60", "pool_total": "72"},
    }
    contract = RecursoContrato(
        contrato_id="C1", tipo_id="CRANE", quantidade_contratada=1,
        semana_inicio="2026-W01", semana_fim="2026-W03", semanas_contrato=3,
        custo_unit_semanal=5, custo_total_contrato=72,
        p16_global_assignment=witness,
        particao_por_item=[{"item_id": "A", "custo_total_particionado": 72.0}],
    )
    costs = AtividadeCustoCompleto(
        atividade_id="A", semana_inicio=0, semana_fim=2,
        custos_diretos_semanais=[
            CustoDiretoSemanalAtividade(
                semana_iso="2026-W01", quantitativo=1, frentes=1,
                custo_mao_obra=0, custo_equipamentos=diagnostic_mo_eq,
                custo_contratual=diagnostic_mo_eq,
            ),
            CustoDiretoSemanalAtividade(
                semana_iso="2026-W03", quantitativo=1, frentes=1,
                custo_mao_obra=0, custo_equipamentos=diagnostic_mo_eq,
                custo_contratual=diagnostic_mo_eq,
            ),
        ],
    )
    return CanonicalModel.model_construct(
        contratos_recurso=[contract], custos_atividades=[costs],
        p18_consumption_preview=_preview(),
    )


def _canonical_shared_machine_partial_final_week() -> CanonicalModel:
    """One machine serves A and B across an idle week; B has a partial final week."""
    witness = {
        "resource_type": "CRANE", "contract_id": "C1", "currency": "BRL",
        "calendar_weeks": ["2026-W01", "2026-W02", "2026-W03"],
        "tariff": {"active_week": "5"},
        "demand_by_activity": {"A": [1, 0, 0], "B": [0, 0, 1]},
        "chains": [{
            "active_week_indices": [0, 2],
            "activity_by_week": {"2026-W01": "A", "2026-W03": "B"},
        }],
        "costs": {"active": "10", "standby": "2", "mobility": "60", "pool_total": "72"},
    }
    contract = RecursoContrato(
        contrato_id="C1", tipo_id="CRANE", quantidade_contratada=1,
        semana_inicio="2026-W01", semana_fim="2026-W03", semanas_contrato=3,
        custo_unit_semanal=5, custo_total_contrato=72,
        p16_global_assignment=witness,
        particao_por_item=[
            {"item_id": "A", "custo_total_particionado": 36.0},
            {"item_id": "B", "custo_total_particionado": 36.0},
        ],
    )
    activity_a = AtividadeCustoCompleto(
        atividade_id="A", semana_inicio=0, semana_fim=0,
        custos_diretos_semanais=[
            CustoDiretoSemanalAtividade(
                semana_iso="2026-W01", quantitativo=1.0, frentes=1,
                custo_mao_obra=0, custo_equipamentos=36, custo_contratual=36,
            ),
        ],
    )
    activity_b = AtividadeCustoCompleto(
        atividade_id="B", semana_inicio=2, semana_fim=2,
        custos_diretos_semanais=[
            CustoDiretoSemanalAtividade(
                # The final activity's physical scope is only 0.25 units, but
                # the contracted instance still incurs the full active-week rate.
                semana_iso="2026-W03", quantitativo=0.25, frentes=1,
                custo_mao_obra=0, custo_equipamentos=36, custo_contratual=36,
            ),
        ],
    )
    return CanonicalModel.model_construct(
        contratos_recurso=[contract],
        custos_atividades=[activity_a, activity_b],
        p18_consumption_preview=_preview(),
    )


def test_reconciles_active_k_after_lifecycle_costs_and_keeps_v_separate(monkeypatch) -> None:
    monkeypatch.setattr(
        "concilium.application.scheduling.skill06_p17_cost_reconciliation.build_skill05_exact_pool_ledger",
        lambda _canonical: _pool(),
    )
    result = build_skill06_p17_reconciliation(_canonical())
    assert result["status"] == "RECONCILED"
    assert result["project_go_authorized"] is False
    assert result["totals"]["pool_contractual_k"] == "12"
    assert result["totals"]["p16_activity_active_k"] == "10"
    assert result["totals"]["allocated_standby_and_mobility"] == "62"
    assert result["totals"]["skill06_activity_diagnostic_mo_eq"] == "72"
    assert result["totals"]["skill06_active_k_diagnostic"] == "10"
    assert result["totals"]["pool_k_minus_activity_active_k_diagnostic"] == "2"
    assert result["totals"]["physical_consumable_v"] == "3"
    assert result["totals"]["total"] == "75"
    assert result["invariants"]["activity_diagnostics_match_p16_active_k"] is True
    assert result["invariants"]["lifecycle_allocation_closes"] is True
    assert result["invariants"]["consumables_are_separate_from_k"] is True


def test_shared_machine_across_activities_closes_with_partial_final_week(monkeypatch) -> None:
    monkeypatch.setattr(
        "concilium.application.scheduling.skill06_p17_cost_reconciliation.build_skill05_exact_pool_ledger",
        lambda _canonical: _pool(),
    )
    result = build_skill06_p17_reconciliation(_canonical_shared_machine_partial_final_week())

    assert result["status"] == "RECONCILED"
    assert result["project_go_authorized"] is False
    assert result["totals"]["pool_active_k"] == "10"
    assert result["totals"]["pool_idle_k"] == "2"
    assert result["totals"]["p16_activity_active_k"] == "10"
    assert result["totals"]["skill06_activity_diagnostic_mo_eq"] == "72"
    assert result["totals"]["skill06_active_k_diagnostic"] == "10"
    assert result["activity_costs"] == [
        {
            "activity_id": "A",
            "exact_p16_active_k": "5",
            "allocated_p16_standby_and_mobility": "31",
            "skill06_diagnostic_mo_eq": "36",
            "skill06_active_k_diagnostic": "5",
            "delta_active_diagnostic_minus_p16": "0",
        },
        {
            "activity_id": "B",
            "exact_p16_active_k": "5",
            "allocated_p16_standby_and_mobility": "31",
            "skill06_diagnostic_mo_eq": "36",
            "skill06_active_k_diagnostic": "5",
            "delta_active_diagnostic_minus_p16": "0",
        },
    ]


def test_activity_cost_mismatch_is_nogo_not_a_favorable_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "concilium.application.scheduling.skill06_p17_cost_reconciliation.build_skill05_exact_pool_ledger",
        lambda _canonical: _pool(),
    )
    result = build_skill06_p17_reconciliation(_canonical(diagnostic_mo_eq=35.0))
    assert result["status"] == "NOGO"
    assert result["project_go_authorized"] is False
    assert any("active MO+EQ diagnostic after lifecycle allocation differs" in reason for reason in result["reasons"])


def test_forged_preview_total_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "concilium.application.scheduling.skill06_p17_cost_reconciliation.build_skill05_exact_pool_ledger",
        lambda _canonical: _pool(),
    )
    canonical = _canonical()
    preview = dict(canonical.p18_consumption_preview or {})
    preview["totals"] = {**preview["totals"], "total": "1"}
    canonical = canonical.model_copy(update={"p18_consumption_preview": preview})
    with pytest.raises(ValueError, match="does not reconstruct"):
        build_skill06_p17_reconciliation(canonical)


def test_duplicate_acquisition_identity_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "concilium.application.scheduling.skill06_p17_cost_reconciliation.build_skill05_exact_pool_ledger",
        lambda _canonical: _pool(),
    )
    canonical = _canonical()
    preview = dict(canonical.p18_consumption_preview or {})
    rows = list(preview["exclusive_postings"])
    rows.append(dict(rows[-1]))
    preview["exclusive_postings"] = rows
    canonical = canonical.model_copy(update={"p18_consumption_preview": preview})
    with pytest.raises(ValueError, match="duplicate financial ownership"):
        build_skill06_p17_reconciliation(canonical)


def test_missing_activity_diagnostic_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "concilium.application.scheduling.skill06_p17_cost_reconciliation.build_skill05_exact_pool_ledger",
        lambda _canonical: _pool(),
    )
    canonical = _canonical().model_copy(update={"custos_atividades": []})
    with pytest.raises(ValueError, match="no activity-cost diagnostics"):
        build_skill06_p17_reconciliation(canonical)
