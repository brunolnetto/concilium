"""N11 (#206): the exact financial view classifies recorded causes as the oracle does,
and the causes production actually records land on their norm."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from concilium.application.scheduling import exact_financial_view as view_module
from concilium.application.scheduling.exact_pricing_declaration import (
    PricingDeclarationError,
    profile_pricing_terms,
)
from concilium.application.scheduling.pricing_report_adapter import parse_site_indirects_scope
from tests.reference_formalism.not_evaluated_reason_reference import classify_recorded_reason

ROOT = Path(__file__).resolve().parents[4]
VECTORS = json.loads(
    (ROOT / "tests/reference_formalism/vectors/economic_not_evaluated_reasons_v1.json").read_text(encoding="utf-8")
)["vectors"]
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
_UNWITNESSED = [{"code": "CONTRATO_SEM_TESTEMUNHA_P16", "message": "", "action": None, "detail": None}]


def _view_code(recorded: str, unwitnessed: bool = False) -> str:
    return view_module._recorded_reason(recorded, _UNWITNESSED if unwitnessed else [])["code"]


@pytest.mark.parametrize("case", [c for c in VECTORS if "expected" in c], ids=lambda c: c["case_id"])
def test_view_classification_matches_the_oracle_vector(case: dict) -> None:
    data = case["case"]
    assert _view_code(data["recorded"], bool(data.get("unwitnessed_contracts"))) == case["expected"]
    assert classify_recorded_reason(data) == case["expected"]


def test_recorded_text_is_always_kept_verbatim() -> None:
    reason = view_module._recorded_reason("catalog benchmark currency differs from resolved catalog metadata", [])
    assert reason["detail"] == "catalog benchmark currency differs from resolved catalog metadata"


def _profile_error(mutate, tipo_obra: str = "terraplenagem") -> str:
    profile = copy.deepcopy(PROFILE)
    mutate(profile)
    with pytest.raises(PricingDeclarationError) as raised:
        profile_pricing_terms(profile, tipo_obra)
    return str(raised.value)


@pytest.mark.parametrize(
    "produce",
    [
        lambda: _profile_error(lambda p: p.pop("precificacao_exata")),
        lambda: _profile_error(lambda p: p["precificacao_exata"]["tabela_bdi"]["linhas"].pop("servicos")),
        lambda: _profile_error(lambda p: p["precificacao_exata"].pop("piso_bdi_regulatorio")),
        lambda: _profile_error(lambda p: p["precificacao_exata"].pop("escopo_estoque")),
        lambda: _profile_error(lambda p: p.pop("faixa_margem_aceitavel")),
        lambda: _profile_error(lambda p: None, tipo_obra="edificacao"),
    ],
    ids=["no-block", "missing-row", "no-floor", "no-inventory-scope", "no-minimum-margin", "work-type-without-floor"],
)
def test_real_profile_gaps_are_classified_as_profile_pricing_terms(produce) -> None:
    """The texts profile_pricing_terms really raises — the ones Skill06 now persists."""
    recorded = produce()
    assert _view_code(recorded) == "TERMOS_DE_PRECO_DO_PERFIL", recorded
    assert classify_recorded_reason({"recorded": recorded}) == "TERMOS_DE_PRECO_DO_PERFIL"


def test_real_missing_site_scope_is_classified_as_n10() -> None:
    with pytest.raises(ValueError) as raised:
        parse_site_indirects_scope({})
    recorded = str(raised.value)
    assert _view_code(recorded) == classify_recorded_reason({"recorded": recorded}) == "ESCOPO_INDIRETOS_CANTEIRO"
