"""Semântica RFX de procurement — ADR-115 (camada de contexto e validação).

`ProcurementIntent` e `PipelineProfile` são definidos em
`application.skills.phase_classifier` (co-localizados com `PipelineMode` e já
conectados ao core da pipeline). Este módulo NÃO redefine o enum — reusa-o e
adiciona a camada voltada a MCP/CLI (D6):

- `ProcurementContext`: bloco serializável (`to_dict`) com método de custo,
  estágio, pergunta central e entregáveis (D3).
- `validate_procurement_baseline`: stub de validação de pré-condições por intent.

Fluxo canônico: RFI (exploração) → RFP (técnico-econômico) → aprovação do cliente.
O RFP aprovado segue diretamente para o cliente — não existe etapa intermediária RFQ.

Princípio (D6): o CORE resolve caminho/modo; CLI/API/MCP passam o intent e
recebem o contexto. A seleção de nós não fica acoplada às tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from concilium.application.skills.phase_classifier import (
    PipelineMode,
    ProcurementIntent,
    get_pipeline_profile_for_intent,
)

__all__ = [
    "ProcurementIntent",
    "ProcurementContext",
    "resolve_procurement_context",
    "validate_procurement_baseline",
]


# ── Entregáveis lógicos por intenção (D3 — contrato, não nomes de arquivo) ────

_RFI_DELIVERABLES = [
    "baseline_escopo_eap",
    "custo_preliminar_catalogo_puxq",
    "prazo_custo_preliminares",
    "alertas_qualidade_dados",
]

# RFP = tudo do RFI + análise operacional (D3)
_RFP_DELIVERABLES = _RFI_DELIVERABLES + [
    "cronograma_operacional",
    "efeitos_praticabilidade_climatica",
    "custo_componentes_nao_produtivos",
    "diagnostico_criticidade",
    "avaliacao_intervencoes",
    "registro_decisao",
    "bundle_relatorios",
]

# Metadados de negócio por intenção (D2)
_INTENT_META: dict[ProcurementIntent, dict] = {
    ProcurementIntent.RFI: {
        "estagio": "Exploração inicial",
        "pergunta_central": "O que é viável no mercado para este escopo?",
        "metodo_custo": "Precificação de catálogo (PU × Q) — preliminar",
        "requires_baseline": False,
        "deliverables": _RFI_DELIVERABLES,
    },
    ProcurementIntent.RFP: {
        "estagio": "Due diligence e seleção",
        "pergunta_central": "Qual solução entrega melhor valor total?",
        "metodo_custo": "Custo operacional (cronograma, clima, não-produtivo) — auditável",
        "requires_baseline": False,
        "deliverables": _RFP_DELIVERABLES,
    },
}


@dataclass(frozen=True)
class ProcurementContext:
    """Contexto resolvido a partir de uma intenção de procurement (ADR-115 D5/D6)."""

    intent: ProcurementIntent
    caminho: str  # nome do caminho nativo da pipeline (= PipelineProfile.path_name)
    pipeline_mode: PipelineMode
    estagio: str
    pergunta_central: str
    metodo_custo: str
    requires_baseline: bool
    deliverables: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serializa para bloco `procurement_context` (consumido por MCP — D6)."""
        return {
            "intent": self.intent.value,
            "caminho": self.caminho,
            "pipeline_mode": self.pipeline_mode.value,
            "estagio": self.estagio,
            "pergunta_central": self.pergunta_central,
            "metodo_custo": self.metodo_custo,
            "requires_baseline": self.requires_baseline,
            "deliverables": list(self.deliverables),
        }


def resolve_procurement_context(intent: ProcurementIntent | str) -> ProcurementContext:
    """Resolve o contexto de procurement a partir da intenção (ADR-115 D5).

    Delega caminho/modo ao perfil do core (`get_pipeline_profile_for_intent`)
    e enriquece com método de custo, estágio e contrato de entregáveis (D3).
    Aceita o enum ou a string ('rfi'|'rfp', case-insensitive).
    """
    profile = get_pipeline_profile_for_intent(intent)
    meta = _INTENT_META[profile.intent]
    return ProcurementContext(
        intent=profile.intent,
        caminho=profile.path_name,
        pipeline_mode=profile.mode,
        estagio=meta["estagio"],
        pergunta_central=meta["pergunta_central"],
        metodo_custo=meta["metodo_custo"],
        requires_baseline=meta["requires_baseline"],
        deliverables=list(meta["deliverables"]),
    )


def validate_procurement_baseline(intent: ProcurementIntent | str, baseline_ref: str | None) -> None:
    """Valida pré-condições de baseline por intenção (ADR-115 D4/D6).

    RFI e RFP não exigem baseline prévia.
    Função mantida para compatibilidade de assinatura com callers existentes.
    """
    # Nenhuma intenção ativa exige baseline — chamada é no-op para RFI/RFP.
    _ = resolve_procurement_context(intent)  # valida que o intent é reconhecido
