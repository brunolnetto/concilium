"""P13-B: parity of typed selectors across normative representations, runtime and oracle.

This test reads documents but does not import production scheduling/financial code.
"""
from __future__ import annotations

from pathlib import Path

from concilium.domain.models.canonical._estoque_consumiveis import (
    RecursoConsumivelCanonical,
)
from concilium.domain.models.canonical._pool_recursos import RecursoContrato

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/product/5-specifications/formulario_longo"

CONTRACTS = {"FULL_RATE_STANDBY", "DISCOUNTED_STANDBY", "EXPLICIT_OFF_HIRE"}
CONSUMPTION = {
    "OUTPUT_PROPORTIONAL", "OUTPUT_WITH_MEASURED_LOSS", "HOURLY_WITH_MEASURED_IDLE",
}


def test_normative_regime_selectors_have_document_parity() -> None:
    for name in (
        "FORMALISMO_LONGO.md",
        "FORMALISMO_RESUMIDO.md",
        "formulario_longo.tex",
        "P13B_TIPAGEM_REGIMES_CONSUMO.md",
    ):
        body = (DOCS / name).read_text(encoding="utf-8")
        for selector in CONTRACTS | CONSUMPTION:
            assert selector in body, f"{name}: missing selector {selector}"
        assert "NOT_EVALUATED" in body
    doc = (DOCS / "P13B_TIPAGEM_REGIMES_CONSUMO.md").read_text(encoding="utf-8")
    for gate in ("NOT_PROJECT_GO", "CONTRACTUAL_ACTIVE", "CONTRACTUAL_IDLE",
                 "CONSUMABLE_ACQUISITION", "MOBILIZATION_EVENT", "DEMOBILIZATION_EVENT",
                 "INVENTORY_HOLDING"):
        assert gate in doc


def test_canonical_opt_in_has_no_free_legacy_commercial_default() -> None:
    contract_fields = RecursoContrato.model_fields
    consumable_fields = RecursoConsumivelCanonical.model_fields
    assert contract_fields["regime_economico_p13"].default is None
    assert contract_fields["origem_regime_p13"].default is None
    assert contract_fields["moeda_regime_p13"].default is None
    assert consumable_fields["regime_consumo_p13"].default is None
    assert consumable_fields["origem_taxa_consumo_p13"].default is None
    assert consumable_fields["origem_preco_consumo_p13"].default is None
