"""#206 W3-A: UI logic of the exact financial view — layers and gate states, no margin semaphore."""

from __future__ import annotations

import json

from concilium.application.scheduling.exact_financial_view import build_exact_financial_view, exact_deltas
from concilium.presentation.ui.helpers import financeiro_exato as fx
from tests.support.exact_financial import canonical, contract, evaluated_resultado, unknown_resultado

GO = {
    "status": "CURRENT", "recorded_decision": "GO", "effective_decision": "GO", "project_go": True,
    "scope": "RFP", "reasons": [], "gates": [{"gate_id": "V1", "status": "PASS", "reason": None}],
}


def _summary(result) -> dict:
    # What the UI receives: the run summary after a JSON round trip through the API.
    return json.loads(json.dumps({"financeiro_exato": build_exact_financial_view(canonical(result))}))


def test_evaluated_summary_shows_the_markup_layers() -> None:
    view = fx.summary_view(_summary(evaluated_resultado()))
    assert fx.is_evaluated(view)
    assert fx.layer_cards(view) == [
        {"label": "Custo total", "value": "R$ 25,50"},
        {"label": "Overhead", "value": "R$ 2,02"},
        {"label": "Lucro", "value": "R$ 4,28"},
        {"label": "Tributos", "value": "R$ 0,00"},
        {"label": "Preço", "value": "R$ 31,80"},
    ]
    exact = {row["grandeza"]: row["valor exato"] for row in fx.exact_rows(view)}
    assert exact["Custo total"] == "51/2" and exact["Preço"] == "159/5"
    assert exact["Participação do lucro no preço"] == "57/424"
    assert exact["Indiretos de canteiro (NO_SITE_INDIRECTS)"] == "-"
    categories = {row["categoria"]: row for row in fx.category_rows(view)}
    assert set(categories) == {"MO", "EQ", "MAT", "COMB", "IND"}
    assert categories["EQ"]["preço (exato)"] == "84/5" and categories["EQ"]["BDI"] == "20,00%"


def test_gate_states_replace_the_margin_semaphore() -> None:
    view = fx.summary_view(_summary(evaluated_resultado()))
    rows = fx.gate_rows(view, GO)
    states = {row["gate"]: row["status"] for row in rows}
    assert states == {
        "Piso regulatório de BDI": "PASS",
        "Camada de lucro": "PASS",
        "Gates de preço (P21)": "PASS",
        "Piso de BDI por categoria": "ABAIXO",
        "Certificado P23": "GO",
        "P23 V1": "PASS",
    }
    text = json.dumps([fx.layer_cards(view), rows, fx.category_rows(view), fx.exact_rows(view)], ensure_ascii=False)
    for forbidden in ("Margem", "margem", "VERDE", "AMARELO", "VERMELHO", "🟢", "🟡", "🔴"):
        assert forbidden not in text


def test_certificate_go_requires_the_current_consistent_projection() -> None:
    view = fx.summary_view(_summary(evaluated_resultado()))
    for stale in ({**GO, "status": "INVALIDATED"}, {**GO, "project_go": "true"}, {**GO, "effective_decision": "NOGO"}):
        states = {row["gate"]: row["status"] for row in fx.gate_rows(view, stale)}
        assert states["Certificado P23"] != "GO"
    assert not [row for row in fx.gate_rows(view, None) if row["gate"].startswith(("Certificado", "P23"))]


def test_not_evaluated_summary_shows_reasons_and_no_number() -> None:
    summary = json.loads(json.dumps({"financeiro_exato": build_exact_financial_view(
        canonical(unknown_resultado(), contracts=[contract("c-eq", witnessed=False)], p18=None)
    )}))
    view = fx.summary_view(summary)
    assert not fx.is_evaluated(view)
    assert fx.layer_cards(view) == [] and fx.category_rows(view) == [] and fx.exact_rows(view) == []
    assert fx.gate_rows(view) == []
    lines = fx.not_evaluated_lines(view)
    assert len(lines) == 2 and "N8" in lines[0] and "c-eq" in lines[0] and "Como resolver" in lines[0]
    assert fx.run_row_cells(summary) == {
        "Custo": "não avaliado", "Preço": "não avaliado", "Gates de preço": "não avaliado",
    }


def test_legacy_summary_is_never_displayed() -> None:
    """A run recorded before the exact view: its legacy floats are not shown, not even labelled."""
    legacy = {"preco_venda_total": 1_000_000.0, "custo_total": 800_000.0, "margem_pct": 0.2, "status_margem": "VERDE"}
    view = fx.summary_view(legacy)
    assert not fx.is_evaluated(view)
    assert fx.run_row_cells(legacy) == {
        "Custo": "não avaliado", "Preço": "não avaliado", "Gates de preço": "não avaliado",
    }
    shown = json.dumps([fx.layer_cards(view), fx.not_evaluated_lines(view), fx.gate_rows(view)], ensure_ascii=False)
    assert "800" not in shown and "1.000.000" not in shown and "VERDE" not in shown
    assert "Reexecute o pipeline" in shown


def test_run_row_cells_for_an_evaluated_run() -> None:
    assert fx.run_row_cells(_summary(evaluated_resultado())) == {
        "Custo": "R$ 25,50", "Preço": "R$ 31,80", "Gates de preço": "PASS",
    }


def test_delta_rows_are_exact_with_display_approximations() -> None:
    left = build_exact_financial_view(canonical(evaluated_resultado()))
    right = json.loads(json.dumps(left))
    right["cost"]["total"] = "53/2"
    right["profit_layer_share"] = "67/424"
    deltas = {"pe_deficit_items": 0.0, "financeiro_exato": exact_deltas(left, right)}

    assert fx.delta_not_evaluated_lines(deltas) == []
    rows = {row["indicador"]: row for row in fx.delta_rows(deltas)}
    assert rows["Custo total"] == {"indicador": "Custo total", "delta": "R$ 1,00", "delta (exato)": "1"}
    assert rows["Participação do lucro no preço"]["delta (exato)"] == "5/212"
    assert rows["Participação do lucro no preço"]["delta"] == "2,36 p.p."
    assert "Margem" not in json.dumps(list(rows), ensure_ascii=False)


def test_delta_against_a_not_evaluated_version_shows_reasons_per_side() -> None:
    left = build_exact_financial_view(canonical(evaluated_resultado()))
    right = build_exact_financial_view(canonical(unknown_resultado()))
    deltas = {"financeiro_exato": exact_deltas(left, right)}
    lines = fx.delta_not_evaluated_lines(deltas)
    assert len(lines) == 1 and lines[0].startswith("versão direita:") and "motivo não registrado" in lines[0]
    assert {row["delta"] for row in fx.delta_rows(deltas)} == {"não avaliado"}
    # A compare payload recorded before the exact deltas existed (legacy float deltas only).
    assert fx.delta_not_evaluated_lines({"custo_total": 5.0, "margem_pct": 0.1}) == [
        "Comparação sem financeiro exato: motivo não registrado."
    ]
