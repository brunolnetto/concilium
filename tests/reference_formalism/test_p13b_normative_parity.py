"""P13-B: parity of typed selectors across normative representations, runtime and oracle.

This test reads documents without importing any production code.
"""
from __future__ import annotations

from pathlib import Path

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


