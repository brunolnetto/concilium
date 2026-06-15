"""Catálogo centralizado de validações — v2.5.

Centraliza todos os códigos de validação do sistema e fornece um
helper factory `make_violation()` para criação consistente de
ConstraintViolation.

Usage::

    from concilium.domain.validations.catalog import ValidationCode, make_violation

    viol = make_violation(
        ValidationCode.VAL_POOL_01,
        "ERRO",
        magnitude=2.0,
        items=["eap-01:2026-07"],
        hint="Reduza num_equipes em Julho ou amplie o pool",
    )
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from concilium.domain.models.project.constraint_violation import ConstraintViolation

ConstraintStatus = Literal["OK", "AVISO", "ERRO"]


class ValidationCode(StrEnum):
    """Todos os 19+ códigos de validação do pipeline Concilium.

    Prefixo  Significado
    -------  -----------------------------------------------------------
    VAL-EAP  Estrutura da EAP / escopo
    VAL-SEQ  Sequenciamento / DAG
    VAL-REC  Declaração de recursos
    VAL-CRON Cronograma / distribuição mensal
    VAL-POOL Pool de recursos / capacidade
    VAL-EQUIP Ponto de equilíbrio de equipes
    VAL-MARG Margem financeira
    VAL-IND  Custos indiretos
    VAL-MARGEM Margem consolidada
    """

    # ── Hard constraints (C1–C5) ──────────────────────────────────────
    # C1: 100% execução de cada atividade
    VAL_EXEC_100 = "VAL-EXEC-100"

    # C2: Prazo total <= contrato
    VAL_PRAZO = "VAL-PRAZO"

    # C3: Uso de recursos <= pool disponível
    VAL_POOL_01 = "VAL-POOL-01"

    # C4: DAG sem ciclos + caminho crítico <= prazo
    VAL_SEQ_01 = "VAL-SEQ-01"  # Ciclo detectado no DAG
    VAL_SEQ_02 = "VAL-SEQ-02"  # Caminho crítico excede prazo contratual

    # C5: Indiretos regulatórios satisfeitos
    VAL_IND_REG = "VAL-IND-REG"

    # ── EAP / escopo ──────────────────────────────────────────────────
    VAL_EAP_01 = "VAL-EAP-01"  # Cada item EAP referencia CPU existente
    VAL_EAP_02 = "VAL-EAP-02"  # Quantitativos positivos
    VAL_EAP_03 = "VAL-EAP-03"  # item_id únicos

    # ── Soft constraints (C6–C9) ──────────────────────────────────────
    # C6: Margem dentro da faixa alvo
    VAL_MARGEM_01 = "VAL-MARGEM-01"

    # C7: Equilíbrio custo fixo × custo de venda CPU
    VAL_EQUIP_01 = "VAL-EQUIP-01"

    # C8: Razão indireto/direto aceitável
    VAL_INDIRETO_RATIO = "VAL-INDIRETO-RATIO"

    # C9: Continuidade do cronograma (sem lacunas)
    VAL_CONTINUIDADE = "VAL-CONTINUIDADE"

    # ── Recursos (DV-REC) ─────────────────────────────────────────────
    VAL_REC_01 = "VAL-REC-01"  # Tipo de recurso referencia insumo no catálogo
    VAL_REC_02 = "VAL-REC-02"  # Quantidades devem ser inteiros positivos

    # ── Política de indiretos (DV4) ───────────────────────────────────
    VAL_IND_POL_01 = "VAL-IND-POL-01"  # indirect_policy deve ser "lean"|"standard"|"robust"

    # ── Adapter / Relatório ───────────────────────────────────────────
    VAL_ADAPTER_PRECONDICAO = "VAL-ADAPTER-PRECONDICAO"
    VAL_ADAPTER_01 = "VAL-ADAPTER-01"

    # ── Criticality ───────────────────────────────────────────────────
    VAL_CRIT_PRECONDICAO = "VAL-CRIT-PRECONDICAO"
    VAL_CRIT_01 = "VAL-CRIT-01"

    # ── Cronograma ────────────────────────────────────────────────────
    VAL_CRON_01 = "VAL-CRON-01"
    VAL_CRON_02 = "VAL-CRON-02"

    # ── Escopo / Resolução semântica (v1.0 Semantic Layer) ────────────
    VAL_SCOPE_PARSE_01 = "VAL-SCOPE-PARSE-01"  # SemanticParseError em item de escopo
    VAL_SCOPE_NOCANDIDATE = "VAL-SCOPE-NOCANDIDATE"  # Nenhum candidato CPU elegível
    VAL_SCOPE_REVIEW = "VAL-SCOPE-REVIEW"  # Confiança MEDIUM/LOW (requer revisão humana)
    VAL_SCOPE_LLM = "VAL-SCOPE-LLM"  # Item resolvido via LLM fallback (auditável)


def make_violation(
    code: ValidationCode | str,
    status: ConstraintStatus,
    magnitude: float | None = None,
    items: list[str] | None = None,
    hint: str | None = None,
) -> ConstraintViolation:
    """Factory para criação consistente de ConstraintViolation.

    Args:
        code:      Código da validação (ValidationCode ou string literal).
        status:    "OK" | "AVISO" | "ERRO".
        magnitude: Quanto acima/abaixo do limite (opcional).
        items:     Lista de atividades/períodos afetados (opcional).
        hint:      Sugestão de remediação legível (opcional).

    Returns:
        ConstraintViolation pronto para ser anexado a canonical ou SkillResult.

    Example::

        make_violation(
            ValidationCode.VAL_POOL_01,
            "ERRO",
            magnitude=2.0,
            items=["eap-01:2026-07"],
            hint="Reduza num_equipes em Julho ou amplie o pool",
        )
    """
    code_str = code.value if isinstance(code, ValidationCode) else str(code)
    return ConstraintViolation(
        code=code_str,
        status=status,
        magnitude=magnitude,
        affected_items=items or [],
        remediation_hint=hint,
        timestamp=datetime.now(UTC),
    )


__all__ = ["ValidationCode", "make_violation", "ConstraintStatus"]
