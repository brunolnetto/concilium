"""Independent oracle: classification of a recorded not-evaluated cause (N11).

The recorded text (``pricing_diagnostics.reason``) is classified by an ordered
table of markers; the first row with a marker in the text wins, case-insensitive.
Stdlib only; written from the N11 table, not from production code.
"""

from __future__ import annotations

from typing import Any

VERSION = "formalism-not-evaluated-reason/1"

GENERIC = "missing p21_pricing_evidence"
TABLE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("site_indirects", "site-indirects", "site indirects"), "ESCOPO_INDIRETOS_CANTEIRO"),
    (("bdi_projeto_exato", "floating point", "exact form"), "BDI_PROJETO_NAO_EXATO"),
    (
        (
            "precificacao_exata",
            "tabela_bdi",
            "piso_bdi_regulatorio",
            "escopo_estoque",
            "faixa_margem_aceitavel",
            "regulatory bdi floor",
            "work type",
        ),
        "TERMOS_DE_PRECO_DO_PERFIL",
    ),
    (("markup layers", "markup_layers"), "CAMADAS_MARKUP_NAO_DECLARADAS"),
    (("p18_consumption_preview_enabled",), "LEDGERS_EXATOS_DESATIVADOS"),
)


class ReasonError(ValueError):
    pass


def classify_recorded_reason(case: dict[str, Any]) -> str:
    recorded = case.get("recorded")
    if not isinstance(recorded, str) or not recorded.strip():
        raise ReasonError("a recorded reason must be nonempty text")
    text = recorded.lower()
    if GENERIC in text:
        return "DECLARACAO_PRECO_AUSENTE" if case.get("unwitnessed_contracts") else "MOTIVO_NAO_REGISTRADO"
    for markers, code in TABLE:
        if any(marker in text for marker in markers):
            return code
    return "P21_NAO_AVALIADO"
