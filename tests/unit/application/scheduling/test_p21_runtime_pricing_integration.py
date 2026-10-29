"""P21-C: the canonical report exposes one shared, fail-closed pricing gate."""
from __future__ import annotations

from concilium.application.scheduling.pricing_report_adapter import (
    apply_pricing_report_evidence,
)
from concilium.domain.models.canonical import Resultado


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
