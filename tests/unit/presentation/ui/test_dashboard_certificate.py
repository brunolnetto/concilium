"""P23 consumer contract for the dashboard: GO only from the shared projection."""

from __future__ import annotations

import pytest

from concilium.presentation.ui.templates import dashboard_page as d

CURRENT_GO = {
    "status": "CURRENT",
    "recorded_decision": "GO",
    "effective_decision": "GO",
    "project_go": True,
    "scope": "RFP",
    "reasons": [],
    "gates": [{"gate_id": "V1", "status": "PASS", "reason": None}],
}


def test_current_go_is_presented_as_certified() -> None:
    assert d._rdt_certificate_is_current_go(CURRENT_GO)
    assert d._rdt_certificate_cards(CURRENT_GO)[0]["value"] == "GO certificado"


@pytest.mark.parametrize(
    "certificate",
    [
        # Historical GO whose sources changed after issuance.
        {**CURRENT_GO, "status": "INVALIDATED", "effective_decision": "NOT_CERTIFIABLE", "project_go": False},
        # Listing projection: recorded GO but not revalidated.
        {**CURRENT_GO, "status": "NOT_REVALIDATED", "effective_decision": "NOT_CERTIFIABLE", "project_go": False},
        # Inconsistent payload must not be trusted on any single field.
        {**CURRENT_GO, "project_go": False},
        {**CURRENT_GO, "status": "INVALIDATED"},
        {**CURRENT_GO, "effective_decision": "NOGO"},
        {**CURRENT_GO, "project_go": "true"},
        None,
        {},
        "GO",
    ],
)
def test_anything_but_current_go_is_not_certified(certificate: object) -> None:
    assert not d._rdt_certificate_is_current_go(certificate)
    assert d._rdt_certificate_cards(certificate)[0]["value"].startswith("Não certificado")


def test_missing_certificate_reports_not_evaluated() -> None:
    cards = {c["label"]: c["value"] for c in d._rdt_certificate_cards(None)}
    assert cards["Certificação formal"] == "Não certificado (NOT_CERTIFIABLE)"
    assert cards["Situação do certificado"] == "NOT_EVALUATED"


def test_gate_rows_reflect_projection_without_reinterpretation() -> None:
    cert = {
        **CURRENT_GO,
        "gates": [
            {"gate_id": "V1", "status": "PASS", "reason": None},
            {"gate_id": "V6", "status": "UNKNOWN", "reason": "search incomplete"},
            "junk",
        ],
    }
    assert d._rdt_certificate_gate_rows(cert) == [
        {"gate": "V1", "status": "PASS", "motivo": "-"},
        {"gate": "V6", "status": "UNKNOWN", "motivo": "search incomplete"},
    ]
    assert d._rdt_certificate_gate_rows({"gates": None}) == []
