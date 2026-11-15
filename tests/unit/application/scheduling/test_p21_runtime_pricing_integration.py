"""P21-C: the canonical report exposes one shared, fail-closed pricing gate."""
from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime
from fractions import Fraction as F
from pathlib import Path

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.markup_layers import LayerRates
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
    SiteIndirectsScope,
    apply_pricing_report_evidence,
    build_pricing_report_evidence_context,
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


_NO_SITE_SCOPE_JSON: dict[str, object] = {
    "status": "NO_SITE_INDIRECTS",
    "source": "fixture: no site administration modelled",
    "reference_id": "no-site-indirects-fixture",
    "fingerprint": "site-indirects-scope-fixture-v1",
}
_DECLARED_SITE_SCOPE_JSON: dict[str, object] = {**_NO_SITE_SCOPE_JSON, "status": "DECLARED"}


def _no_site_scope() -> SiteIndirectsScope:
    return SiteIndirectsScope(
        status="NO_SITE_INDIRECTS",
        source="test-fixture",
        reference_id="no-site-indirects-fixture",
        fingerprint="site-indirects-scope-fingerprint",
    )


def test_preview_without_exact_ledger_is_unknown_and_visible() -> None:
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(result, {"certification_intent": "PREVIEW"}, validations)

    assert result.pricing_gates["schema"] == "concilium.p21.pricing-gates.v1"
    assert result.pricing_gates["certification_intent"] == "PREVIEW"
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert result.pricing_diagnostics["schema"] == "concilium.p21.pricing-diagnostics.v1"
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


def _typed_context() -> dict[str, object]:
    """Complete typed evidence (N9 layers included) for the adapter's direct boundary."""
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
        "site_indirects_scope": _no_site_scope(),
        "pool_ledger": pool,
        "consumption_journal": consumption,
        "bdi_by_category": {
            "MO": F(1, 10),
            "EQ": F(1, 5),
            "MAT": F(1, 2),
            "COMB": F(3, 10),
            "IND": F(1, 4),
        },
        # N9: declared layers whose markup is exactly the rates above. Profit
        # layer: EQ 14 * 1.1 / 11 = 7/5, IND 9/4, MAT 5/2 * 1.25 / 5 = 5/8.
        "markup_layers": {
            "MO": LayerRates(F(0), F(0), F(0), F(1, 10)),
            "EQ": LayerRates(F(1, 10), F(0), F(0), F(1, 11)),
            "MAT": LayerRates(F(1, 4), F(0), F(0), F(1, 5)),
            "COMB": LayerRates(F(1, 10), F(0), F(0), F(2, 11)),
            "IND": LayerRates(F(0), F(0), F(0), F(1, 4)),
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
    return context


def _apply_typed(context: dict[str, object], intent: str = "PREVIEW"):
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(
        result,
        {"certification_intent": intent, "p20_financial_sources": context},
        validations,
    )
    return result, validations


def test_typed_p20_sources_reach_one_shared_operational_and_regulatory_gate() -> None:
    result, validations = _apply_typed(_typed_context())

    assert result.pricing_diagnostics["operational_price"] == "159/5"
    assert result.pricing_diagnostics["total_cost"] == "51/2"
    assert result.pricing_gates["regulatory_status"] == "FAIL"
    assert result.pricing_gates["profitability_status"] == "PASS"
    assert result.pricing_gates["profit_layer_amount"] == "171/40"
    assert result.pricing_gates["profit_layer_share"] == "57/424"
    assert result.markup_layers["total"]["price"] == "159/5"
    assert result.pricing_gates["status"] == "FAIL"
    assert validations[-1].codigo == "VAL-P21-PRICE-GATES"
    assert validations[-1].status == "AVISO"


def _without(context: dict[str, object], key: str) -> dict[str, object]:
    return {k: v for k, v in context.items() if k != key}


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda c: _without(c, "markup_layers"), "must declare markup layers"),
        (lambda c: {**c, "markup_layers": None}, "must declare markup layers"),
        (
            lambda c: {**c, "markup_layers": _without(c["markup_layers"], "IND")},  # type: ignore[arg-type]
            "must declare markup layers",
        ),
        (
            lambda c: {**c, "markup_layers": {**c["markup_layers"], "MO": {"l": "1/10"}}},  # type: ignore[dict-item]
            "must declare markup layers",
        ),
        # A flat rate that is not the layers' own markup is not the declared price.
        (
            lambda c: {**c, "bdi_by_category": {**c["bdi_by_category"], "EQ": F(1, 4)}},  # type: ignore[dict-item]
            "bdi_by_category differs from the declared markup layers for EQ",
        ),
    ],
)
@pytest.mark.parametrize("intent", ["PREVIEW", "CERTIFIED"])
def test_n9_typed_evidence_without_consistent_markup_layers_is_not_priced(mutate, reason: str, intent: str) -> None:
    """N9: there is no flat path — without declared layers nothing is priced or graded."""
    result, validations = _apply_typed(mutate(_typed_context()), intent)
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert result.pricing_gates["profitability_status"] == "UNKNOWN"
    assert reason in result.pricing_gates["reason"]
    assert "operational_price" not in result.pricing_diagnostics
    assert result.markup_layers is None
    assert validations[-1].codigo == "VAL-P21-PRICE-EVIDENCE"
    assert validations[-1].status == ("ERRO" if intent == "CERTIFIED" else "AVISO")


C_CAT_FIXTURE = "6462935383/44925750"
_ZERO_LAYERS: dict[str, object] = {"ac": "0", "rsg": "0", "df": "0", "l": "0", "taxes": {}}


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
    # C^cat (FORMALISMO_LONGO §XIV.8) is derived from the production team, so
    # the fixture carries the real production record and its team insumos.
    production = json.loads(
        (root / "config/catalogos/rfi-r02/produtividades/CPU-TERRA-ATI-003-PROD-001.json").read_text(
            encoding="utf-8",
        )
    )
    team = production["composicao_padrao_equipe"]
    team_ids = [r["equip_id"] for r in team["equipamentos"]] + [r["funcao_id"] for r in team["funcoes"]]
    team_insumos = [
        json.loads(next((root / "config/catalogos/rfi-r02/insumos").rglob(f"{ident}.json")).read_text(encoding="utf-8"))
        for ident in team_ids
    ]
    catalogo: dict[str, object] = {
        "cpus": [cpu],
        "producoes": [production],
        "insumos": [diesel, *team_insumos],
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
        "site_indirects_scope": dict(_NO_SITE_SCOPE_JSON),
        "bdi_by_category": {
            "MO": "0",
            "EQ": "0",
            "MAT": "0",
            # Hand check: the fixture ledger carries only diesel (no P16 pool),
            # while C^cat counts the full production team (~143.858). With
            # COMB markup 3: P = diesel 42.804*4 + ORE 10 (MAT, 0) + IND 1.512
            # = 182.728 -> BDI over C^cat ~27.0% >= 10% floor.
            "COMB": "3",
            "IND": "0",
        },
        # N9: the layers are the declaration. COMB (1 + AC 1)(1 + L 1) = 4 -> markup 3;
        # profit layer = 42.804 * 2 * 1 = 85.608 -> 85.608/182.728 ~46.9% of the price
        # >= 20% (the other half of P - C is overhead, not profit).
        "markup_layers": {
            **{category: dict(_ZERO_LAYERS) for category in ("MO", "EQ", "MAT", "IND")},
            "COMB": {**_ZERO_LAYERS, "ac": "1", "l": "1"},
        },
        "catalog": {
            # Independent oracle (tests/reference_formalism/catalog_envelope_reference.py).
            "amount": C_CAT_FIXTURE,
            "currency": "BRL",
            "source": "resolved-project-catalog",
            "reference_id": "catalog-price-2026-10",
            "basis_fingerprint": "physical-scope-2026-v1",
        },
        "operational_basis_fingerprint": "physical-scope-2026-v1",
        "regulatory_basis": {
            "amount": C_CAT_FIXTURE,
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
    assert result.pricing_diagnostics["schema"] == "concilium.p21.pricing-diagnostics.v1"
    assert result.pricing_diagnostics["p20_authority"].endswith("NOT_PROJECT_GO")
    assert result.pricing_diagnostics["catalog_source"] == "resolved-project-catalog"
    assert result.pricing_diagnostics["catalog_reference_id"] == "catalog-price-2026-10"
    assert result.pricing_diagnostics["operational_basis_fingerprint"] == "physical-scope-2026-v1"
    assert result.pricing_diagnostics["inventory_scope_reference_id"] == "stocktake-2026-10-01"
    assert result.pricing_diagnostics["bdi_rate_comb"] == "3"
    assert result.pricing_gates["profit_layer_amount"] == str(F("85.608"))
    assert result.pricing_gates["profit_layer_share"] == str(F("85.608") / F("182.728"))
    assert result.markup_layers["total"]["overhead"] == str(F("42.804"))
    assert result.pricing_diagnostics["operational_price"] == str(F("182.728"))
    assert result.pricing_diagnostics["total_cost"] == str(F("54.316"))
    assert result.pricing_gates["schema"] == "concilium.p21.pricing-gates.v1"
    assert result.pricing_gates["certification_intent"] == "CERTIFIED"
    assert result.pricing_gates["regulatory_basis_source"] == "regulatory-basis"
    assert result.pricing_gates["regulatory_basis_reference"] == "regulatory-2026-v1"
    assert result.pricing_gates["regulatory_basis_amount"] == C_CAT_FIXTURE
    assert result.pricing_gates["regulatory_basis_minimum_rate"] == "1/10"
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


@pytest.mark.parametrize("field", ["catalog", "regulatory_basis"])
def test_declared_bdi_basis_must_equal_derived_catalog_envelope(field: str) -> None:
    """FORMALISMO_LONGO §XIV.8: BDI = P / C^cat - 1 is derived, not a free input.
    A declared basis that differs from C^cat (here a placeholder "1", which
    previously made V2 pass trivially) is rejected and the evidence fails closed."""
    canonical, catalogo, declaration = _json_runtime_fixture()
    declaration[field]["amount"] = "1"
    with pytest.raises(ValueError, match="differs from derived C\\^cat"):
        build_pricing_report_evidence_context(canonical, catalogo, declaration)


# --- N10: site-indirects scope and declared lines through the real Skill 06 JSON boundary ---

_SITE_INDIRECTS: dict[str, object] = {
    "schema": "concilium.n10.site-indirects.v1",
    "currency": "BRL",
    "source": "planilha de administração local do projeto",
    "reference_id": "adm-local-2026-v1",
    # The only scheduled activity runs in 2026-W19; the site opens one week earlier.
    "mobilised_weeks": {"first": "2026-W18", "last": "2026-W19"},
    "lines": [
        {
            "line_id": "ADM",
            "driver": "perm",
            "source": "folha ADM 2026-05",
            # 1461/1461 = 1 -> 336/week of MO; VM 14.61 -> 3.36/week.
            "monthly": {"MO": "1461", "EQ": "0", "COMB": "0", "VM": "14.61"},
        },
        {"line_id": "MOB_SITE", "driver": "onetime", "source": "orçamento", "mobilize": "7", "demobilize": "3"},
    ],
}


def _run_skill06_with(monkeypatch, evidence: dict[str, object] | None = None, **skill_inputs: object):
    """Run the real Skill 06 over the fixture; ``evidence`` overrides/removes (None) declaration keys."""
    _load("06-resultado-financeiro", "run_resultado_financeiro")
    skill_module = sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]
    canonical, catalogo, declaration = _json_runtime_fixture()
    for key, value in (evidence or {}).items():
        if value is None:
            declaration.pop(key, None)
        else:
            declaration[key] = value
    seen: dict[str, object] = {}

    def stage_consolidation(current, stage_inputs, *_args):
        result = _result()
        validations: list = []
        apply_pricing_report_evidence(result, stage_inputs, validations)
        seen["context"] = stage_inputs["p21_pricing_evidence"]
        seen["result"] = result
        return SkillResult(current, validations)

    monkeypatch.setattr(skill_module, "_run_precificacao", lambda current, *_a: SkillResult(current, []))
    monkeypatch.setattr(skill_module, "_run_indiretos", lambda current, *_a: SkillResult(current, []))
    monkeypatch.setattr(skill_module, "_run_consolidacao", stage_consolidation)
    monkeypatch.setattr(skill_module, "build_skill06_p17_reconciliation", lambda _c: {"status": "RECONCILED"})
    inputs: dict[str, object] = {
        "p18_consumption_preview_enabled": True,
        "certification_intent": "PREVIEW",
        "p21_pricing_evidence": declaration,
        **skill_inputs,
    }
    outcome = skill_module.run_resultado_financeiro(canonical, inputs, catalogo, {})
    return outcome, seen


def _scopes(diagnostics: dict) -> tuple[dict, dict]:
    return tuple(  # type: ignore[return-value]
        {field: diagnostics[f"{scope}_scope_{field}"] for field in ("status", "source", "reference_id", "fingerprint")}
        for scope in ("inventory", "site_indirects")
    )


def test_declared_site_indirects_enter_p20_and_are_replayed_by_p23(monkeypatch) -> None:
    from concilium.application.scheduling.formalism_evaluator import _financial_reconciliation_status

    outcome, seen = _run_skill06_with(
        monkeypatch, {"site_indirects_scope": _DECLARED_SITE_SCOPE_JSON, "site_indirects": _SITE_INDIRECTS}
    )
    result = seen["result"]
    reconciliation = seen["context"]["reconciliation"]
    # Site: ADM 2 weeks x (336 + 3.36) = 678.72; MOB_SITE 7 + 3 = 10.
    site_cost = F("688.72")
    assert reconciliation.site_indirects.cost == site_cost
    assert reconciliation.ledger.consumable_v == F("52.804")  # direct cost untouched
    assert reconciliation.ledger.indirect == F("1.512") + site_cost
    assert result.pricing_diagnostics["site_indirects_scope_status"] == "DECLARED"
    assert result.pricing_diagnostics["site_indirects_scope_reference_id"] == "no-site-indirects-fixture"
    assert result.pricing_diagnostics["site_indirects_cost"] == str(site_cost)
    assert result.pricing_diagnostics["site_indirects_reference_id"] == "adm-local-2026-v1"
    assert result.pricing_diagnostics["total_cost"] == str(F("54.316") + site_cost)
    assert not outcome.has_errors

    persisted = result.p20_financial_reconciliation
    witness = persisted["site_indirects"]
    assert witness["mobilised_weeks"] == ["2026-W18", "2026-W19"]
    assert witness["lines"][0]["cost_by_category"] == {"IND": "168/25", "MO": "672"}
    assert witness["lines"][1]["cost"] == "10"
    site_rows = [row for row in persisted["postings"] if row["event_id"][0] == "SITE_INDIRECT"]
    assert {(row["nature"], row["category"]) for row in site_rows} == {("INDIRECT", "MO"), ("INDIRECT", "IND")}
    # P23 replays the persisted ledger, including INDIRECT postings in the MO markup category.
    inventory_scope, site_scope = _scopes(result.pricing_diagnostics)
    replayed = json.loads(json.dumps(persisted))
    status, observed, reason = _financial_reconciliation_status(replayed, inventory_scope, site_scope)
    assert (status, reason) == ("PASS", None)
    assert observed["indirect"] == str(F("1.512") + site_cost)
    assert observed["site_indirects_scope"]["status"] == "DECLARED"
    # The same ledger under a scope that denies it, or with no scope, never passes.
    denied, _, why = _financial_reconciliation_status(
        replayed, inventory_scope, {**site_scope, "status": "NO_SITE_INDIRECTS"}
    )
    assert denied == "FAIL" and "conflicts with site-indirect postings" in why
    assert _financial_reconciliation_status(replayed, inventory_scope)[0] == "UNKNOWN"


def test_no_site_indirects_scope_is_an_explicit_declaration(monkeypatch) -> None:
    from concilium.application.scheduling.formalism_evaluator import _financial_reconciliation_status

    outcome, seen = _run_skill06_with(monkeypatch)
    result = seen["result"]
    assert seen["context"]["reconciliation"].site_indirects is None
    assert result.pricing_diagnostics["site_indirects_scope_status"] == "NO_SITE_INDIRECTS"
    assert result.pricing_diagnostics["site_indirects_scope_source"] == "fixture: no site administration modelled"
    assert result.pricing_diagnostics["site_indirects_cost"] is None  # not a computed "0"
    assert result.pricing_diagnostics["total_cost"] == str(F("54.316"))
    assert result.p20_financial_reconciliation["site_indirects"] is None
    assert not outcome.has_errors
    status, _observed, reason = _financial_reconciliation_status(
        result.p20_financial_reconciliation, *_scopes(result.pricing_diagnostics)
    )
    assert (status, reason) == ("PASS", None)


@pytest.mark.parametrize("intent", ["PREVIEW", "CERTIFIED"])
def test_without_a_site_indirects_scope_the_price_is_not_evaluated(monkeypatch, intent: str) -> None:
    outcome, seen = _run_skill06_with(monkeypatch, {"site_indirects_scope": None}, certification_intent=intent)
    result = seen["result"]
    assert "site_indirects_scope is required" in seen["context"]["source_build_error"]
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert result.pricing_diagnostics["status"] == "UNKNOWN"
    assert "total_cost" not in result.pricing_diagnostics and "operational_price" not in result.pricing_diagnostics
    assert outcome.has_errors is (intent == "CERTIFIED")


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        ({"site_indirects_scope": _DECLARED_SITE_SCOPE_JSON}, "requires the site_indirects declaration"),
        ({"site_indirects": _SITE_INDIRECTS}, "NO_SITE_INDIRECTS scope conflicts"),
        ({"site_indirects_scope": {**_NO_SITE_SCOPE_JSON, "status": "NONE_ASSUMED"}}, "must be DECLARED or NO_SITE"),
        ({"site_indirects_scope": {**_NO_SITE_SCOPE_JSON, "source": " "}}, "source must be nonempty"),
        ({"site_indirects_scope": {**_NO_SITE_SCOPE_JSON, "estimated": True}}, "unsupported fields"),
        ({"site_indirects_scope": {k: v for k, v in _NO_SITE_SCOPE_JSON.items() if k != "fingerprint"}},
         "fingerprint must be nonempty"),
        ({"site_indirects_scope": "NO_SITE_INDIRECTS"}, "must be a JSON object"),
    ],
)
def test_inconsistent_site_indirects_scope_is_rejected(monkeypatch, evidence: dict, reason: str) -> None:
    _outcome, seen = _run_skill06_with(monkeypatch, evidence)
    assert reason in seen["context"]["source_build_error"]
    assert seen["result"].pricing_gates["status"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"mobilised_weeks": {"first": "2026-W18", "last": "2026-W18"}}, "does not cover every week"),
        ({"currency": "USD"}, "currency differs"),
        ({"lines": []}, "at least one line"),
        ({"source": ""}, "source must be nonempty"),
    ],
)
def test_invalid_site_indirects_leave_the_price_not_evaluated(monkeypatch, change: dict, reason: str) -> None:
    _outcome, seen = _run_skill06_with(
        monkeypatch,
        {"site_indirects_scope": _DECLARED_SITE_SCOPE_JSON, "site_indirects": {**_SITE_INDIRECTS, **change}},
    )
    result = seen["result"]
    assert reason in seen["context"]["source_build_error"]
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert "total_cost" not in result.pricing_diagnostics


def test_skill06_inputs_carry_the_scope_and_the_lines(monkeypatch) -> None:
    """Project-level inputs are merged into a declaration that does not carry them itself."""
    _outcome, seen = _run_skill06_with(
        monkeypatch,
        {"site_indirects_scope": None},
        site_indirects_scope=_DECLARED_SITE_SCOPE_JSON,
        site_indirects=_SITE_INDIRECTS,
    )
    assert seen["result"].pricing_diagnostics["site_indirects_scope_status"] == "DECLARED"
    assert seen["context"]["reconciliation"].site_indirects.cost == F("688.72")


@pytest.mark.parametrize("key", ["site_indirects_scope", "site_indirects"])
def test_site_indirects_cannot_be_declared_in_two_places(monkeypatch, key: str) -> None:
    both = {"site_indirects_scope": _DECLARED_SITE_SCOPE_JSON, "site_indirects": _SITE_INDIRECTS}
    _outcome, seen = _run_skill06_with(monkeypatch, both, **{key: both[key]})
    assert "declared both" in seen["context"]["source_build_error"]
    assert seen["result"].pricing_gates["status"] == "UNKNOWN"


def test_typed_context_without_a_site_indirects_scope_is_unknown() -> None:
    result = _result()
    validations: list = []
    scope = InventoryEvidenceScope(status="NO_INVENTORY", source="s", reference_id="r", fingerprint="f")
    apply_pricing_report_evidence(
        result, {"certification_intent": "AUTO_GO", "p21_pricing_evidence": {"inventory_scope": scope}}, validations
    )
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert "site-indirects scope" in result.pricing_gates["reason"]
    assert validations[-1].status == "ERRO"


def test_typed_context_scope_must_agree_with_the_journal() -> None:
    from concilium.application.scheduling.financial_cost_reconciliation import reconcile_financial_sources

    pool = ExclusiveCostLedger((
        CostPosting(("POOL", "R", "ACTIVE"), PostingNature.ACTIVE, "EQ", F(14), "R", "2026-W01"),
    ))
    reconciliation = reconcile_financial_sources(pool, PhysicalConsumptionJournalResult(pool, ()))
    result = _result()
    validations: list = []
    apply_pricing_report_evidence(
        result,
        {
            "p21_pricing_evidence": {
                "inventory_scope": InventoryEvidenceScope(
                    status="NO_INVENTORY", source="s", reference_id="r", fingerprint="f"
                ),
                "site_indirects_scope": SiteIndirectsScope(
                    status="DECLARED", source="s", reference_id="r", fingerprint="f"
                ),
                "reconciliation": reconciliation,
            },
        },
        validations,
    )
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert "requires the site_indirects declaration" in result.pricing_gates["reason"]


# --- N9: markup layers are mandatory at the JSON boundary (no flat declaration) ---


@pytest.mark.parametrize("intent", ["PREVIEW", "CERTIFIED"])
def test_n9_declaration_without_markup_layers_is_not_priced(monkeypatch, intent: str) -> None:
    outcome, seen = _run_skill06_with(monkeypatch, {"markup_layers": None}, certification_intent=intent)
    result = seen["result"]
    assert "markup_layers is required" in seen["context"]["source_build_error"]
    assert result.pricing_gates["status"] == "UNKNOWN"
    assert result.pricing_gates["profitability_status"] == "UNKNOWN"
    assert "total_cost" not in result.pricing_diagnostics and "operational_price" not in result.pricing_diagnostics
    assert result.markup_layers is None
    assert outcome.has_errors is (intent == "CERTIFIED")


@pytest.mark.parametrize(
    ("layers", "reason"),
    [
        (
            {"COMB": {**_ZERO_LAYERS, "l": "3"}, "MO": {**_ZERO_LAYERS, "l": "1/100"}},
            "differs from the declared markup layers for MO",
        ),
        ({"COMB": {**_ZERO_LAYERS, "l": "-1"}}, "markup_layers.COMB.l must be nonnegative"),
        ({"COMB": {**_ZERO_LAYERS, "l": 3.0}}, "must be an exact decimal or rational string"),
        ({"COMB": {"l": "3"}}, "must declare exactly ac, rsg, df, l and taxes"),
        ({"COMB": None}, "must declare exactly ac, rsg, df, l and taxes"),
    ],
)
def test_n9_inconsistent_markup_layers_are_rejected(monkeypatch, layers: dict, reason: str) -> None:
    declared = {category: dict(_ZERO_LAYERS) for category in ("MO", "EQ", "MAT", "COMB", "IND")}
    _outcome, seen = _run_skill06_with(monkeypatch, {"markup_layers": {**declared, **layers}})
    assert reason in seen["context"]["source_build_error"]
    assert seen["result"].pricing_gates["status"] == "UNKNOWN"
    assert seen["result"].markup_layers is None
