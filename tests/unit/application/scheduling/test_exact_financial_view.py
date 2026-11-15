"""#206 W3-A: one exact financial view, derived only from the exact evidence."""
from __future__ import annotations

import json
from fractions import Fraction as F
from types import SimpleNamespace

import pytest

from concilium.application.scheduling import exact_financial_view as efv
from concilium.application.scheduling.exact_financial_view import (
    AVALIADO,
    NAO_AVALIADO,
    build_exact_financial_view,
    compact_view,
    exact_deltas,
    reason_lines,
    text_lines,
    view_from_summary,
    with_certificate,
)
from tests.support.exact_financial import (
    canonical,
    contract,
    evaluated_resultado,
    typed_context,
    unknown_resultado,
)

LEGACY_KEYS = ("venda", "custo", "resultado_financeiro", "margem_pct", "status_margem")


def _codes(view: dict) -> list[str]:
    return [reason["code"] for reason in view["reasons"]]


# ── evaluated ────────────────────────────────────────────────────────────────


def test_evaluated_view_carries_the_exact_layers_and_gate_states() -> None:
    view = build_exact_financial_view(canonical(evaluated_resultado()))

    assert view["status"] == AVALIADO and view["reasons"] == []
    assert view["currency"] == "BRL"
    assert view["cost"] == {"total": "51/2", "direct": "33/2", "indirect": "9"}
    assert view["price"] == "159/5"
    assert view["layers"] == {"cost": "51/2", "overhead": "81/40", "profit": "171/40", "taxes": "0", "price": "159/5"}
    assert view["profit_layer_share"] == "57/424"
    assert view["minimum_profit_margin"] == "0"
    assert view["catalog_benchmark"] == "25"
    assert view["bdi_on_catalog"] == "34/125" == view["regulatory_bdi_rate"]
    assert view["regulatory_bdi_floor"] == "1/10"
    assert view["by_category"]["EQ"] == {
        "cost": "14", "overhead": "7/5", "profit": "7/5", "taxes": "0", "price": "84/5",
    }
    assert set(view["by_category"]) == {"MO", "EQ", "MAT", "COMB", "IND"}
    assert view["bdi_rate_by_category"]["MO"] == "1/10"
    assert view["bdi_floor_by_category"]["MO"] == "1/4"
    assert view["categories_below_floor"] == ["MO"]
    assert view["site_indirects"]["scope_status"] == "NO_SITE_INDIRECTS"
    assert view["site_indirects"]["cost"] is None  # no site indirects: null, not a computed zero
    assert view["gates"]["status"] == "PASS"
    assert view["gates"]["regulatory_status"] == "PASS" and view["gates"]["profitability_status"] == "PASS"
    assert view["certificate"] is None


def test_layers_reconstruct_the_price_exactly() -> None:
    layers = build_exact_financial_view(canonical(evaluated_resultado()))["layers"]
    assert F(layers["cost"]) + F(layers["overhead"]) + F(layers["profit"]) + F(layers["taxes"]) == F(layers["price"])


def test_failed_gates_keep_the_view_evaluated_and_list_their_reasons() -> None:
    result = evaluated_resultado(regulatory_floor=F(1, 2), minimum_profit_margin=F(1, 5))
    view = build_exact_financial_view(canonical(result))

    assert view["status"] == AVALIADO
    assert view["gates"]["status"] == "FAIL"
    assert view["gates"]["regulatory_status"] == "FAIL" and view["gates"]["profitability_status"] == "FAIL"
    assert view["gates"]["reasons"] == [
        "operational BDI on the regulatory basis is below its floor",
        "profit-layer share of the price is below the explicit minimum",
    ]


def test_view_never_exposes_a_margin_semaphore_or_price_minus_cost_margin() -> None:
    view = build_exact_financial_view(canonical(evaluated_resultado()))
    dumped = json.dumps(view)
    for forbidden in ("status_margem", "margem_pct", "realized_margin", "VERDE", "AMARELO", "VERMELHO"):
        assert forbidden not in dumped
    # (P - C)/P = 63/318 is not the margin; the criterion is the profit layer's share.
    assert str((F(159, 5) - F(51, 2)) / F(159, 5)) not in dumped


def test_view_is_json_serializable_and_values_are_exact_strings() -> None:
    view = build_exact_financial_view(canonical(evaluated_resultado()))
    assert json.loads(json.dumps(view)) == view

    def _no_float(node: object) -> None:
        assert not isinstance(node, float)
        if isinstance(node, dict):
            for value in node.values():
                _no_float(value)
        elif isinstance(node, list):
            for value in node:
                _no_float(value)

    _no_float(view)


# ── never reads the legacy fields ────────────────────────────────────────────


class _NoLegacy:
    """A resultado that raises when any legacy float field is read."""

    def __init__(self, result: object) -> None:
        self._result = result

    def __getattr__(self, name: str) -> object:
        if name in LEGACY_KEYS:
            raise AssertionError(f"the exact view read the legacy field {name}")
        return getattr(self._result, name)


@pytest.mark.parametrize("build", [evaluated_resultado, unknown_resultado])
def test_view_does_not_depend_on_the_legacy_fields(build) -> None:
    absurd = build_exact_financial_view(canonical(build()))
    sane = build_exact_financial_view(canonical(build(legacy={
        "venda": SimpleNamespace(total_com_bdi=31.8),
        "custo": SimpleNamespace(total=25.5),
        "resultado_financeiro": 6.3,
        "margem_pct": 0.198,
        "status_margem": "VERMELHO",
    })))
    untouched = build_exact_financial_view(canonical(_NoLegacy(build())))
    without = build_exact_financial_view(canonical(SimpleNamespace(
        pricing_diagnostics=build().pricing_diagnostics,
        pricing_gates=build().pricing_gates,
        markup_layers=build().markup_layers,
    )))
    assert absurd == sane == untouched == without


def test_view_reads_a_canonical_json_mapping_like_the_model() -> None:
    result = evaluated_resultado()
    as_json = {
        "resultado": {
            "pricing_diagnostics": dict(result.pricing_diagnostics),
            "pricing_gates": dict(result.pricing_gates),
            "markup_layers": result.markup_layers,
            "margem_pct": 99.0,
        },
        "contratos_recurso": [],
    }
    assert build_exact_financial_view(as_json) == build_exact_financial_view(canonical(result))


def test_module_source_names_no_legacy_accessor() -> None:
    source = open(efv.__file__, encoding="utf-8").read()
    code = source.split('"""', 2)[2]  # skip the module docstring, which names what is never read
    for accessor in ('"venda"', '"custo"', '"resultado_financeiro"', '"margem_pct"', '"status_margem"',
                     ".venda", ".custo", ".margem_pct", ".status_margem", ".resultado_financeiro"):
        assert accessor not in code


# ── not evaluated: each reason derivable from the canonical ──────────────────


def test_no_canonical_and_no_result() -> None:
    assert _codes(build_exact_financial_view(None)) == ["SEM_CANONICO"]
    view = build_exact_financial_view(SimpleNamespace(resultado=None))
    assert view["status"] == NAO_AVALIADO and _codes(view) == ["RESULTADO_AUSENTE"]


def test_pool_contracts_without_p16_witness_are_named_n8() -> None:
    view = build_exact_financial_view(canonical(
        unknown_resultado(),
        contracts=[
            contract("c-b", witnessed=False), contract("c-a", witnessed=False), contract("c-ok", witnessed=True),
        ],
        p18=None,
    ))
    assert _codes(view) == ["CONTRATO_SEM_TESTEMUNHA_P16", "DECLARACAO_PRECO_AUSENTE"]
    first = view["reasons"][0]
    assert first["detail"] == "c-a, c-b"
    assert "N8" in first["message"] and "contract_terms" in first["action"]
    assert view["reasons"][1]["detail"].startswith("missing p21_pricing_evidence")


def test_no_pool_contracts_at_all() -> None:
    view = build_exact_financial_view(canonical(unknown_resultado(), contracts=[], p18=None))
    assert _codes(view) == ["SEM_CONTRATOS_DE_POOL", "DECLARACAO_PRECO_AUSENTE"]


def test_witnessed_pool_without_p18_record() -> None:
    view = build_exact_financial_view(canonical(unknown_resultado(), p18=None))
    assert _codes(view) == ["CONSUMO_P18_AUSENTE", "DECLARACAO_PRECO_AUSENTE"]


def test_missing_declaration_with_complete_ledgers_says_the_cause_is_not_recorded() -> None:
    """The specific VAL-P21-NAO-AVALIADO gaps are not persisted on the canonical."""
    view = build_exact_financial_view(canonical(unknown_resultado()))
    assert _codes(view) == ["MOTIVO_NAO_REGISTRADO"]
    reason = view["reasons"][0]
    assert "motivo não registrado" in reason["message"]
    assert "VAL-P21-NAO-AVALIADO" in reason["action"]
    assert reason["detail"] == "missing p21_pricing_evidence with authoritative P20 ledger and explicit bases"


def test_missing_site_indirects_scope_is_named_n10() -> None:
    context = typed_context()
    del context["site_indirects_scope"]
    view = build_exact_financial_view(canonical(unknown_resultado({"p20_financial_sources": context})))
    assert _codes(view) == ["ESCOPO_INDIRETOS_CANTEIRO"]
    assert "N10" in view["reasons"][0]["message"]
    assert "site-indirects scope" in view["reasons"][0]["detail"]


def test_missing_markup_layers_are_named_n9() -> None:
    context = typed_context()
    del context["markup_layers"]
    view = build_exact_financial_view(canonical(unknown_resultado({"p20_financial_sources": context})))
    assert _codes(view) == ["CAMADAS_MARKUP_NAO_DECLARADAS"]
    assert "N9" in view["reasons"][0]["message"]


@pytest.mark.parametrize(
    ("recorded", "code"),
    [
        # Skill06 source_build_error texts (06-resultado-financeiro/skill.py).
        ("inputs.bdi_perfil declares project tax/profit terms in floating point; the exact price needs them "
         "as exact strings in bdi_projeto_exato (nothing is converted)", "BDI_PROJETO_NAO_EXATO"),
        ("bdi_projeto_exato requires the exact ledgers (p18_consumption_preview_enabled=true)",
         "BDI_PROJETO_NAO_EXATO"),
        ("P21 pricing evidence requires p18_consumption_preview_enabled=true", "LEDGERS_EXATOS_DESATIVADOS"),
        ("site indirects declared both as a Skill06 input and inside p21_pricing_evidence",
         "ESCOPO_INDIRETOS_CANTEIRO"),
        ("p21_pricing_evidence.site_indirects_scope is required", "ESCOPO_INDIRETOS_CANTEIRO"),
        ("NO_INVENTORY scope conflicts with supplied P19 journals", "P21_NAO_AVALIADO"),
    ],
)
def test_recorded_reason_is_shown_verbatim_with_its_norm(recorded: str, code: str) -> None:
    result = SimpleNamespace(
        pricing_diagnostics={"schema": "x", "status": "UNKNOWN", "reason": recorded},
        pricing_gates={"status": "UNKNOWN"},
        markup_layers=None,
    )
    view = build_exact_financial_view(canonical(result))
    assert _codes(view) == [code]
    assert view["reasons"][0]["detail"] == recorded


def test_canonical_without_any_pricing_record_says_the_cause_is_not_recorded() -> None:
    result = SimpleNamespace(pricing_diagnostics={}, pricing_gates={}, markup_layers=None)
    view = build_exact_financial_view(canonical(result))
    assert view["status"] == NAO_AVALIADO and _codes(view) == ["MOTIVO_NAO_REGISTRADO"]


@pytest.mark.parametrize(
    "damage",
    [
        lambda r: setattr(r, "markup_layers", None),  # canonical older than N9
        lambda r: r.pricing_diagnostics.__setitem__("total_cost", 25.5),  # a float is not exact evidence
        lambda r: r.pricing_diagnostics.__setitem__("operational_price", "31.8.0"),
        lambda r: r.markup_layers["by_category"].pop("IND"),
        lambda r: setattr(r, "pricing_gates", {}),
    ],
)
def test_incomplete_or_inexact_evidence_fails_closed(damage) -> None:
    result = evaluated_resultado()
    damage(result)
    view = build_exact_financial_view(canonical(result))
    assert view["status"] == NAO_AVALIADO
    assert _codes(view) == ["EVIDENCIA_EXATA_INCOMPLETA"]
    assert "cost" not in view and "price" not in view and "layers" not in view


def test_not_evaluated_view_carries_no_number() -> None:
    view = build_exact_financial_view(canonical(unknown_resultado()))
    assert set(view) == {"schema", "status", "reasons", "certificate"}
    assert all(line and "Como resolver" in line for line in reason_lines(view))


# ── certificate, summary, deltas, text ───────────────────────────────────────


def test_certificate_decision_is_attached_when_supplied() -> None:
    certificate = {
        "status": "CURRENT", "recorded_decision": "GO", "effective_decision": "GO", "project_go": True,
        "scope": "RFP", "reasons": [], "evaluation_sha256": "abc",
        "gates": [{"gate_id": "V1", "status": "PASS", "reason": None, "observed": {"x": 1}}],
    }
    view = build_exact_financial_view(canonical(evaluated_resultado()), certificate)
    assert view["certificate"] == {
        "status": "CURRENT", "decision": "GO", "effective_decision": "GO", "recorded_decision": "GO",
        "project_go": True, "scope": "RFP", "reasons": [],
        "gates": [{"gate_id": "V1", "status": "PASS", "reason": None}],
    }
    assert with_certificate(build_exact_financial_view(canonical(evaluated_resultado())), certificate) == view
    # project_go is never inferred from a truthy non-boolean.
    for inconsistent in ({"project_go": "true"}, {"status": "INVALIDATED"}, {"effective_decision": "NOGO"}):
        shown = build_exact_financial_view(None, {**certificate, **inconsistent})["certificate"]
        assert shown["decision"] != "GO"
    assert build_exact_financial_view(None, {**certificate, "project_go": "true"})["certificate"]["project_go"] is False
    assert build_exact_financial_view(None, {**certificate, "status": "INVALIDATED"})["certificate"]["decision"] == (
        "NOT_CERTIFIABLE"
    )
    text = "\n".join(text_lines(view))
    assert "Certificado P23: GO (CURRENT)" in text


def test_view_from_summary_never_reads_legacy_summary_keys() -> None:
    legacy = {"preco_venda_total": 1e6, "custo_total": 8e5, "margem_pct": 0.2, "status_margem": "VERDE"}
    view = view_from_summary(legacy)
    assert view["status"] == NAO_AVALIADO and _codes(view) == ["RESUMO_ANTERIOR_AO_FINANCEIRO_EXATO"]
    assert _codes(view_from_summary({})) == ["SEM_RESUMO"] == _codes(view_from_summary(None))
    stored = build_exact_financial_view(canonical(evaluated_resultado()))
    assert view_from_summary({"financeiro_exato": stored, **legacy}) == stored


def test_exact_deltas_are_right_minus_left_as_exact_strings() -> None:
    left = build_exact_financial_view(canonical(evaluated_resultado()))
    right = json.loads(json.dumps(left))
    right["cost"]["total"] = "53/2"
    right["price"] = "160/5"
    right["profit_layer_share"] = "1/8"
    deltas = exact_deltas(left, right)

    assert deltas["status"] == AVALIADO and deltas["reasons"] == []
    assert deltas["deltas"]["custo_total"] == "1"
    assert deltas["deltas"]["preco"] == "1/5"
    assert deltas["deltas"]["participacao_lucro_no_preco"] == str(F(1, 8) - F(57, 424))
    assert deltas["deltas"]["camada_lucro"] == "0"
    assert set(deltas["deltas"]) == set(efv.DELTA_FIELDS)


def test_deltas_against_a_not_evaluated_side_are_none_not_a_difference_from_zero() -> None:
    left = build_exact_financial_view(canonical(evaluated_resultado()))
    right = build_exact_financial_view(canonical(unknown_resultado()))
    deltas = exact_deltas(left, right)

    assert deltas["status"] == NAO_AVALIADO
    assert all(value is None for value in deltas["deltas"].values())
    assert [(r["side"], r["code"]) for r in deltas["reasons"]] == [("right", "MOTIVO_NAO_REGISTRADO")]


def test_compact_view() -> None:
    compact = compact_view(build_exact_financial_view(canonical(evaluated_resultado())))
    assert compact["status"] == AVALIADO and compact["cost_total"] == "51/2" and compact["price"] == "159/5"
    assert compact["gates"] == {"status": "PASS", "regulatory_status": "PASS", "profitability_status": "PASS"}
    not_evaluated = compact_view(build_exact_financial_view(canonical(unknown_resultado())))
    assert set(not_evaluated) == {"status", "reasons"} and not_evaluated["reasons"]


def test_text_rendering_shows_layers_and_gates_or_not_evaluated_with_reasons() -> None:
    text = "\n".join(text_lines(build_exact_financial_view(canonical(evaluated_resultado()))))
    for expected in (
        "Custo total:   25,50", "Overhead:", "Lucro:", "13,44% do preço", "Tributos:", "Preço:         31,80",
        "Gates de preço: PASS", "Categorias abaixo do piso de BDI: MO", "aproximados",
    ):
        assert expected in text
    assert "Margem" not in text and "VERDE" not in text

    text = "\n".join(text_lines(build_exact_financial_view(canonical(unknown_resultado()))))
    assert text.startswith("Financeiro exato: não avaliado")
    assert "motivo não registrado" in text and "Como resolver" in text
    assert "Custo" not in text and "Preço:" not in text and "Lucro" not in text


def test_display_helpers_only_accept_exact_strings() -> None:
    assert efv.display_float("51/2") == 25.5
    assert efv.display_float(25.5) is None and efv.display_float("abc") is None and efv.display_float(None) is None
    assert efv.format_money("2469/2") == "1.234,50" and efv.format_money(1234.5) == "—"
    assert efv.format_percent("57/424") == "13,44%" and efv.format_percent(None) == "—"
