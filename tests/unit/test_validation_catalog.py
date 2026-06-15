"""Testes para ValidationCode + make_violation (v2.5)."""

from datetime import datetime

from concilium.domain.models.project.constraint_violation import ConstraintViolation
from concilium.domain.validations.catalog import ValidationCode, make_violation


def test_validation_code_enum_has_core_codes():
    """ValidationCode deve conter todos os códigos essenciais do pipeline."""
    required = [
        "VAL-POOL-01",
        "VAL-EXEC-100",
        "VAL-PRAZO",
        "VAL-SEQ-01",
        "VAL-SEQ-02",
        "VAL-MARGEM-01",
        "VAL-EAP-01",
        "VAL-IND-POL-01",
    ]
    codes = {c.value for c in ValidationCode}
    for req in required:
        assert req in codes, f"Código {req} ausente em ValidationCode"


def test_make_violation_produces_constraint_violation():
    """make_violation deve retornar ConstraintViolation válida."""
    viol = make_violation(ValidationCode.VAL_POOL_01, "ERRO")
    assert isinstance(viol, ConstraintViolation)
    assert viol.code == "VAL-POOL-01"
    assert viol.status == "ERRO"
    assert viol.affected_items == []
    assert isinstance(viol.timestamp, datetime)


def test_make_violation_with_all_params():
    """make_violation com todos os parâmetros opcionais."""
    viol = make_violation(
        ValidationCode.VAL_POOL_01,
        "AVISO",
        magnitude=1.5,
        items=["eap-01:2026-07", "eap-02:2026-07"],
        hint="Reduza equipes em julho",
    )
    assert viol.code == "VAL-POOL-01"
    assert viol.status == "AVISO"
    assert viol.magnitude == 1.5
    assert "eap-01:2026-07" in viol.affected_items
    assert "eap-02:2026-07" in viol.affected_items
    assert viol.remediation_hint == "Reduza equipes em julho"


def test_make_violation_accepts_string_code():
    """make_violation deve aceitar código como string literal."""
    viol = make_violation("VAL-CUSTOM-99", "OK")
    assert viol.code == "VAL-CUSTOM-99"
    assert viol.status == "OK"
