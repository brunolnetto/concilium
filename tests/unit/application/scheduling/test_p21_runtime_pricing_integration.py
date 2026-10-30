"""P21-C: the canonical report exposes one shared, fail-closed pricing gate."""
from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from fractions import Fraction as F
from pathlib import Path

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.operational_pricing_diagnostics import (
    CatalogPriceBenchmark,
)
from concilium.application.scheduling.physical_consumption_journal import (
    AcquisitionEvidenceLine,
    PhysicalConsumptionJournalResult,
)
from concilium.application.scheduling.physical_consumption_rates import (
    PhysicalPurchaseMeasure,
)
from concilium.application.scheduling.pricing_gates import RegulatoryBdiBasis
from concilium.application.scheduling.pricing_report_adapter import (
    InventoryEvidenceScope,
    apply_pricing_report_evidence,
)
from concilium.application.skills import _load
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Cronograma,
    DistribuicaoSemanal,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    ScheduledActivityCanonical,
)


def _result() -> Resultado:
    return Resultado.model_construct(
        pricing_diagnostics={},
        pricing_gates={},
        pricing_authority="",
    )


def test_preview_without_exact_ledger_is_unknown_and_visible() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(result, {"certification_intent": "PREVIEW"}, validations)

    assert result.pricing_gates["status"] == "UNKNOWN"
    assert result.pricing_authority == "P21_C_PRICING_GATES_UNKNOWN_NOT_PROJECT_GO"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "AVISO"
    payload = result.model_dump()
    assert payload["pricing_gates"]["status"] == "UNKNOWN"
    assert payload["pricing_authority"] == result.pricing_authority


def test_certified_mode_without_exact_ledger_fails_closed() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(result, {"certification_intent": "CERTIFIED"}, validations)

    assert result.pricing_gates["status"] == "UNKNOWN"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "ERRO"


def test_auto_go_without_exact_ledger_fails_closed() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(result, {"certification_intent": "AUTO_GO"}, validations)

    assert result.pricing_gates["status"] == "UNKNOWN"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "ERRO"


def test_rfi_and_rfp_keep_the_same_canonical_pricing_gate_shape() -> None:
    for mode in ("RFI", "RFP"):
        result = _result()
        validations: list = []
        apply_pricing_report_evidence(
            result,
            {"certification_intent": "PREVIEW", "proposal_mode": mode},
            validations,
        )
        payload = result.model_dump()
        assert payload["pricing_gates"]["status"] == "UNKNOWN"
        assert payload["pricing_diagnostics"]["status"] == "UNKNOWN"


def test_invalid_typed_financial_sources_fail_closed_in_auto_go() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(
        result,
        {
            "certification_intent": "AUTO_GO",
            "p20_financial_sources": {
                "pool_ledger": object(),
                "consumption_journal": object(),
            },
        },
        validations,
    )
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == "ERRO"


def test_typed_p20_sources_reach_one_shared_operational_and_regulatory_gate() -> None:
    pool = ExclusiveCostLedger((
        CostPosting(
            ("POOL", "R", "ACTIVE"), PostingNature.ACTIVE,
            "EQ", F(14), "R", "2026-W01",
        ),
        CostPosting(
            ("POOL", "R", "MOB"), PostingNature.MOBILIZATION,
            "IND", F(9), "R", "2026-W01",
        ),
    ))
    evidence = AcquisitionEvidenceLine(
        "c1", "PLANNED_CLOSED_SCOPE", "A", "2026-W01",
        PhysicalPurchaseMeasure("ORE", F(1), "kg", F(1), "kg", F(5, 2)),
        "MAT",
    )
    acquisition = CostPosting(
        ("CONSUMABLE", "c1"), PostingNature.ACQUISITION,
        "MAT", F(5, 2), "ORE", "2026-W01",
    )
    consumption = PhysicalConsumptionJournalResult(
        ExclusiveCostLedger(pool.postings + (acquisition,)), (evidence,),
    )
    catalog_metadata = {
        "currency": "BRL",
        "currency_source": "catalog_metadata.json",
    }
    context = {
        "inventory_scope": InventoryEvidenceScope(
            status="NO_INVENTORY",
            source="test-fixture",
            reference_id="no-inventory-fixture",
            fingerprint="inventory-scope-fingerprint",
        ),
        "pool_ledger": pool,
        "consumption_journal": consumption,
        "bdi_by_category": {
            "MO": F(1, 10),
            "EQ": F(1, 5),
            "MAT": F(1, 2),
            "COMB": F(3, 10),
            "IND": F(1, 4),
        },
        "catalog": CatalogPriceBenchmark(
            amount=F(100),
            currency="BRL",
            source="catalog",
            reference_id="catalog-ref",
            basis_fingerprint="scope-fp",
        ),
        "catalog_metadata": catalog_metadata,
        "operational_basis_fingerprint": "scope-fp",
        "regulatory_basis": RegulatoryBdiBasis(
            amount=F(100),
            currency="BRL",
            basis_fingerprint="scope-fp",
            minimum_rate=F(1, 10),
            source="regulatory",
            reference_id="regulatory-ref",
        ),
        "minimum_profit_margin": F(0),
    }
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(
        result,
        {"certification_intent": "PREVIEW", "p20_financial_sources": context},
        validations,
    )

    assert result.pricing_diagnostics["operational_price"] == "159/5"
    assert result.pricing_diagnostics["total_cost"] == "51/2"
    assert result.pricing_gates["regulatory_status"] == "FAIL"
    assert result.pricing_gates["profitability_status"] == "PASS"
    assert result.pricing_gates["status"] == "FAIL"
    assert validations[-1].codigo == "VAL-P21-PRICE-GATES"
    assert validations[-1].status == "AVISO"


def _json_runtime_fixture() -> tuple[CanonicalModel, dict[str, object], dict[str, object]]:
    root = Path(__file__).resolve().parents[4]
    cpu = json.loads(
        (root / "config/catalogos/rfi-r02/cpus/CPU-TERRA-ATI-003.json").read_text(
            encoding="utf-8",
        )
    )
    diesel = json.loads(
        (root / "config/catalogos/rfi-r02/insumos/material/MA-DIESEL-S10.json").read_text(
            encoding="utf-8",
        )
    )
    canonical = CanonicalModel(
        meta=Meta(
            gerado_em=datetime(2026, 5, 1, tzinfo=UTC),
            contexto_id="p21-json-boundary",
        ),
        projeto=Projeto(
            id="p21-json-boundary",
            nome="P21 JSON boundary",
            tipo_obra="terraplenagem",
            localizacao="test",
            coordenadas=Coordenadas(lat=-3, lng=-38),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio=date(2026, 5, 4),
            data_termino=date(2026, 6, 30),
            snapshot_catalogo_id="catalog-v1",
            snapshot_perfil_id="profile-v1",
        ),
        eap=[
            EapItem(
                item_id="A",
                cpu_id=cpu["codigo"],
                unidade=cpu["unidade"],
                quantitativo=100.0,
            ),
        ],
        cronograma=Cronograma(
            scheduled_activities=[
                ScheduledActivityCanonical(
                    activity_id="A",
                    start_week=0,
                    end_week=0,
                    duration_weeks=1,
                    distribuicao_semanal={
                        "2026-W19": DistribuicaoSemanal(
                            num_equipes=1,
                            qtd_executada=100.0,
                            qtd_acumulada=100.0,
                            pct=1.0,
                        ),
                    },
                ),
            ],
            is_feasible=True,
        ),
    )
    catalogo: dict[str, object] = {
        "cpus": [cpu],
        "insumos": [diesel],
        "currency": "BRL",
        "currency_source": "catalog_metadata.json",
    }
    declaration: dict[str, object] = {
        "schema": "concilium.p21.pricing-evidence.v1",
        "inventory_scope": {
            "status": "COMPLETE",
            "source": "physical-inventory-count",
            "reference_id": "stocktake-2026-10-01",
            "fingerprint": "inventory-scope-2026-v1",
        },
        "bdi_by_category": {
            "MO": "0",
            "EQ": "0",
            "MAT": "0",
            "COMB": "1",
            "IND": "0",
        },
        "catalog": {
            "amount": "100",
            "currency": "BRL",
            "source": "resolved-project-catalog",
            "reference_id": "catalog-price-2026-10",
            "basis_fingerprint": "physical-scope-2026-v1",
        },
        "operational_basis_fingerprint": "physical-scope-2026-v1",
        "regulatory_basis": {
            "amount": "40",
            "currency": "BRL",
            "basis_fingerprint": "physical-scope-2026-v1",
            "minimum_rate": "1/10",
            "source": "regulatory-basis",
            "reference_id": "regulatory-2026-v1",
        },
        "minimum_profit_margin": "1/5",
        "inventory": {
            "calendar_weeks": ["2026-W18", "2026-W19"],
            "goods": [
                {
                    "good_id": "MA-DIESEL-S10",
                    "unit": "L",
                    "initial_quantity": "10",
                    "capacity": None,
                    "lead_time_weeks": 0,
                },
                {
                    "good_id": "ORE",
                    "unit": "kg",
                    "initial_quantity": "0",
                    "capacity": None,
                    "lead_time_weeks": 1,
                },
            ],
            "internal_arrivals": [],
            "purchases": [
                {
                    "source_id": "ore-purchase-001",
                    "good_id": "ORE",
                    "ordered_week": "2026-W18",
                    "arrival_week": "2026-W19",
                    "quantity": "5",
                    "physical_unit": "kg",
                    "unit_price": "2",
                    "price_unit": "kg",
                    "price_source": "supplier-quote-2026-10",
                    "price_reference_date": "2026-10-01",
                    "currency": "BRL",
                    "category": "MAT",
                },
            ],
            "holding_tariffs": [
                {
                    "good_id": "MA-DIESEL-S10",
                    "amount_per_unit_week": "1/10",
                    "physical_unit": "L",
                    "basis": "END_OF_WEEK",
                },
                {
                    "good_id": "ORE",
                    "amount_per_unit_week": "1/20",
                    "physical_unit": "kg",
                    "basis": "END_OF_WEEK",
                },
            ],
        },
    }
    return canonical, catalogo, declaration


def test_real_skill06_json_contract_builds_p19_p20_and_reaches_p21_pass(monkeypatch) -> None:
    skill_id = "06-resultado-financeiro"
    _load(skill_id, "run_resultado_financeiro")
    skill_module = sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]
    canonical, catalogo, declaration = _json_runtime_fixture()
    seen: dict[str, object] = {}

    def stage_pre(current, *_args):
        return SkillResult(current, [])

    def stage_indirect(current, *_args):
        return SkillResult(current, [])

    def stage_consolidation(current, inputs, *_args):
        # The real Skill 06 must turn the caller's plain JSON into typed internal
        # evidence before invoking the consolidation stage.
        context = inputs["p21_pricing_evidence"]
        seen["context"] = context
        result = _result()
        validations: list = []
        apply_pricing_report_evidence(result, inputs, validations)
        seen["result"] = result
        return SkillResult(current, validations)

    monkeypatch.setattr(skill_module, "_run_precificacao", stage_pre)
    monkeypatch.setattr(skill_module, "_run_indiretos", stage_indirect)
    monkeypatch.setattr(skill_module, "_run_consolidacao", stage_consolidation)
    monkeypatch.setattr(
        skill_module,
        "build_skill06_p17_reconciliation",
        lambda _canonical: {"status": "RECONCILED"},
    )

    outcome = skill_module.run_resultado_financeiro(
        canonical,
        {
            "p18_consumption_preview_enabled": True,
            "certification_intent": "CERTIFIED",
            "p21_pricing_evidence": declaration,
        },
        catalogo,
        {},
    )

    context = seen["context"]
    result = seen["result"]
    assert isinstance(context["inventory_scope"], InventoryEvidenceScope)
    assert context["inventory_scope"].status == "COMPLETE"
    assert context["reconciliation"].ledger.consumable_v == F("52.804")
    assert context["reconciliation"].ledger.indirect == F("1.512")
    assert result.pricing_gates["regulatory_status"] == "PASS"
    assert result.pricing_gates["profitability_status"] == "PASS"
    assert result.pricing_gates["status"] == "PASS"
    assert result.pricing_diagnostics["operational_price"] == str(F("97.12"))
    assert result.pricing_diagnostics["total_cost"] == str(F("54.316"))
    assert result.pricing_authority != "PROJECT_GO"
    assert not outcome.has_errors


def test_p21_json_contract_rejects_caller_supplied_authoritative_ledgers(monkeypatch) -> None:
    skill_id = "06-resultado-financeiro"
    _load(skill_id, "run_resultado_financeiro")
    skill_module = sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]
    canonical, catalogo, declaration = _json_runtime_fixture()
    declaration["pool_ledger"] = {"postings": []}
    seen: dict[str, object] = {}

    def stage_pre(current, *_args):
        return SkillResult(current, [])

    def stage_indirect(current, *_args):
        return SkillResult(current, [])

    def stage_consolidation(current, inputs, *_args):
        result = _result()
        validations: list = []
        apply_pricing_report_evidence(result, inputs, validations)
        seen["result"] = result
        return SkillResult(current, validations)

    monkeypatch.setattr(skill_module, "_run_precificacao", stage_pre)
    monkeypatch.setattr(skill_module, "_run_indiretos", stage_indirect)
    monkeypatch.setattr(skill_module, "_run_consolidacao", stage_consolidation)

    outcome = skill_module.run_resultado_financeiro(
        canonical,
        {
            "p18_consumption_preview_enabled": True,
            "certification_intent": "CERTIFIED",
            "p21_pricing_evidence": declaration,
        },
        catalogo,
        {},
    )

    result = seen["result"]
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert "unsupported P21 evidence fields" in result.pricing_gates["reason"]
    assert outcome.has_errors



def test_complete_inventory_scope_without_p19_financial_charges_still_validates_stock(monkeypatch) -> None:
    skill_id = "06-resultado-financeiro"
    _load(skill_id, "run_resultado_financeiro")
    skill_module = sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]
    canonical, catalogo, declaration = _json_runtime_fixture()
    inventory = declaration["inventory"]
    inventory["purchases"] = []
    inventory["holding_tariffs"] = []
    seen: dict[str, object] = {}

    def stage_pre(current, *_args):
        return SkillResult(current, [])

    def stage_indirect(current, *_args):
        return SkillResult(current, [])

    def stage_consolidation(current, inputs, *_args):
        context = inputs["p21_pricing_evidence"]
        result = _result()
        validations: list = []
        apply_pricing_report_evidence(result, inputs, validations)
        seen["context"] = context
        seen["result"] = result
        return SkillResult(current, validations)

    monkeypatch.setattr(skill_module, "_run_precificacao", stage_pre)
    monkeypatch.setattr(skill_module, "_run_indiretos", stage_indirect)
    monkeypatch.setattr(skill_module, "_run_consolidacao", stage_consolidation)
    monkeypatch.setattr(
        skill_module,
        "build_skill06_p17_reconciliation",
        lambda _canonical: {"status": "RECONCILED"},
    )

    outcome = skill_module.run_resultado_financeiro(
        canonical,
        {
            "p18_consumption_preview_enabled": True,
            "certification_intent": "CERTIFIED",
            "p21_pricing_evidence": declaration,
        },
        catalogo,
        {},
    )

    context = seen["context"]
    assert context["inventory_scope"].status == "COMPLETE"
    assert context["reconciliation"].ledger.consumable_v == F("42.804")
    assert context["reconciliation"].ledger.indirect == 0
    assert seen["result"].pricing_gates["status"] == "PASS"
    assert not outcome.has_errors



def test_complete_inventory_scope_without_a_p19_journal_is_unknown() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(
        result,
        {
            "certification_intent": "PREVIEW",
            "p21_pricing_evidence": {
                "inventory_scope": InventoryEvidenceScope(
                    status="COMPLETE",
                    source="test-fixture",
                    reference_id="inventory-complete-fixture",
                    fingerprint="inventory-complete-fingerprint",
                ),
            },
        },
        validations,
    )
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert "requires an explicit holding or provisioning journal" in result.pricing_gates["reason"]
