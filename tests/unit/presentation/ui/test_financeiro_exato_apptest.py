"""#206 W3-A: version pages rendered headless with Streamlit's AppTest (no browser, API stubbed).

The screens show the markup layers and the gate states, or "não avaliado" with
the reasons; no legacy number and no margin semaphore.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

from concilium.application.scheduling.exact_financial_view import (  # noqa: E402
    build_exact_financial_view,
    exact_deltas,
)

# Imported here so that the (slow, package-wide) first import is not charged to an AppTest script run.
from concilium.presentation.ui.organisms.layout import (  # noqa: E402, F401
    _ops_audit_compare,
    _version_summary_detail,
)
from tests.support.exact_financial import canonical, contract, evaluated_resultado, unknown_resultado  # noqa: E402

# Each script run takes several seconds (repo convention: `slow`); the logic is covered
# fast in test_financeiro_exato_helpers.py.
pytestmark = pytest.mark.slow

_SUMMARY_API = "concilium.presentation.ui.organisms.layout._version_summary_detail.api_call"
_COMPARE_API = "concilium.presentation.ui.organisms.layout._ops_audit_compare.api_call"
GO = {
    "status": "CURRENT", "recorded_decision": "GO", "effective_decision": "GO", "project_go": True,
    "scope": "RFP", "reasons": [], "gates": [{"gate_id": "V1", "status": "PASS", "reason": None}],
}
LEGACY_SUMMARY = {
    "preco_venda_total": 987654.0, "custo_total": 876543.0, "margem_pct": 0.1125, "status_margem": "VERDE",
}


def _view(result: Any, **kwargs: Any) -> dict:
    return json.loads(json.dumps(build_exact_financial_view(canonical(result, **kwargs))))


def _fake_api(summary: dict, certificate: dict | None = None, compare: dict | None = None):
    run = {"run_id": "r1", "version": "v1", "status": "OK", "started_at": "2026-01-01T10:00:00", "summary": summary}

    def api_call(method: str, path: str, **_kwargs: Any) -> dict:
        if path.endswith("/runs"):
            return {"items": [run]}
        if path.endswith("/runs/r1"):
            return {**run, "formalism_certificate": certificate}
        if path.endswith("/compare"):
            return compare or {}
        return {}

    return api_call


def _summary_app() -> None:
    from concilium.presentation.ui.organisms.layout._version_summary_detail import (
        render_version_detail,
        render_version_summary,
    )

    project = {"project_id": "p1", "versions": ["v1"], "current_version": "v1"}
    render_version_summary("http://api", project, "ana")
    render_version_detail("http://api", project, "ana")


def _compare_app() -> None:
    from concilium.presentation.ui.organisms.layout._ops_audit_compare import _do_compare

    _do_compare("p1", "v1", "v2", "http://api", "ana")


def _page_text(at: AppTest) -> str:
    parts = [str(e.value) for kind in ("markdown", "caption", "warning", "info", "error") for e in at.get(kind)]
    parts += [f"{m.label}={m.value}" for m in at.metric]
    parts += [e.value.to_csv() for e in at.dataframe]
    return "\n".join(parts)


def _run(monkeypatch, app, target: str, api) -> AppTest:
    monkeypatch.setattr(target, api)
    at = AppTest.from_function(app, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def test_evaluated_run_shows_layers_and_gate_states_without_margin(monkeypatch) -> None:
    summary = {"financeiro_exato": _view(evaluated_resultado()), "pe_deficit_items": 0, "pe_alerta_items": 0}
    at = _run(monkeypatch, _summary_app, _SUMMARY_API, _fake_api(summary, GO))
    text = _page_text(at)

    for expected in ("Custo total=R$ 25,50", "Overhead=R$ 2,02", "Lucro=R$ 4,28", "Tributos=R$ 0,00", "Preço=R$ 31,80"):
        assert expected in text
    for expected in ("Piso regulatório de BDI", "Camada de lucro", "Gates de preço (P21)", "Certificado P23", "159/5"):
        assert expected in text
    assert "aproximados" in text
    for forbidden in ("Margem", "margem", "VERDE", "VERMELHO", "não avaliado"):
        assert forbidden not in text
    assert not at.warning


@pytest.mark.parametrize("legacy_only", [False, True])
def test_not_evaluated_run_shows_reasons_and_no_legacy_number(monkeypatch, legacy_only: bool) -> None:
    exact = _view(unknown_resultado(), contracts=[contract("c-eq", witnessed=False)], p18=None)
    summary = dict(LEGACY_SUMMARY) if legacy_only else {**LEGACY_SUMMARY, "financeiro_exato": exact}
    at = _run(monkeypatch, _summary_app, _SUMMARY_API, _fake_api(summary))
    text = _page_text(at)

    assert "não avaliado" in text and "Como resolver" in text
    assert ("Reexecute o pipeline" in text) if legacy_only else ("N8" in text and "c-eq" in text)
    for forbidden in ("987", "876", "11,25", "11.25", "VERDE", "Margem", "Custo total=", "Preço="):
        assert forbidden not in text
    assert at.warning


def test_compare_shows_exact_deltas_or_not_evaluated(monkeypatch) -> None:
    left = _view(evaluated_resultado())
    right = json.loads(json.dumps(left))
    right["cost"]["total"] = "53/2"
    compare = {"deltas": {"pe_deficit_items": 0.0, "financeiro_exato": exact_deltas(left, right)}}
    at = _run(monkeypatch, _compare_app, _COMPARE_API, _fake_api({}, compare=compare))
    at.button[0].click().run()
    assert not at.exception, at.exception
    text = _page_text(at)
    assert "Custo total" in text and "R$ 1,00" in text and "Delta margem" not in text and not at.warning

    compare = {"deltas": {"pe_deficit_items": 0.0, "financeiro_exato": exact_deltas(left, _view(unknown_resultado()))}}
    at = _run(monkeypatch, _compare_app, _COMPARE_API, _fake_api({}, compare=compare))
    at.button[0].click().run()
    assert not at.exception, at.exception
    text = _page_text(at)
    assert "não avaliado" in text and "versão direita" in text and "R$" not in text
