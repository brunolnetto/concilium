"""Gate de aprovação de plano — issue #121 (fase 2).

As validações que sinalizam inconsistência entre preço de venda e custo
operacional (`VAL-COB-NEG`, `VAL-PROD-04`, `VAL-PROD-VS-PU`,
`VAL-GAP-CATALOGO-OPERACIONAL`, `VAL-STALE-UPSTREAM`) são deliberadamente
`AVISO`, não `ERRO` — promovê-las a `ERRO` bloquearia as skills 07-15 e
impediria a geração do próprio relatório financeiro que o gestor usa para
diagnosticar o problema (ver `domain/services/validador_cobertura_item.py`).

O bloqueio certo não é na execução das skills — é na aprovação da versão, o
momento em que o resultado passa a ser tratado como definitivo. Este módulo
segue o mesmo padrão de `catalog_draft_lifecycle.assert_pode_aprovar`: uma
função pura que levanta uma exceção de governança, chamada pela tool MCP
antes de qualquer mutação.
"""

from __future__ import annotations

from typing import Any

_BLOCKING_AVISO_CODES = frozenset(
    {
        "VAL-COB-NEG",
        "VAL-PROD-04",
        "VAL-PROD-VS-PU",
        "VAL-GAP-CATALOGO-OPERACIONAL",
        "VAL-STALE-UPSTREAM",
    }
)


class PlanoApprovalGateError(ValueError):
    """Aprovação bloqueada por inconsistência não resolvida entre venda e custo operacional."""


def _latest_invocation_per_skill(invocations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduz o log de invocações à última entrada de cada skill (uma skill pode ter rodado mais de uma vez)."""
    latest: dict[str, dict[str, Any]] = {}
    for entry in invocations:
        skill = entry.get("skill")
        if skill:
            latest[skill] = entry
    return latest


def _collect_flags(latest_by_skill: dict[str, dict[str, Any]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Retorna (erros, avisos_bloqueantes) como listas de (skill, codigo)."""
    erros: list[tuple[str, str]] = []
    avisos: list[tuple[str, str]] = []
    for skill, entry in latest_by_skill.items():
        for item in entry.get("validacoes") or []:
            codigo = item.get("codigo")
            status = item.get("status")
            if status == "ERRO":
                erros.append((skill, codigo))
            elif status == "AVISO" and codigo in _BLOCKING_AVISO_CODES:
                avisos.append((skill, codigo))
    return erros, avisos


def assert_pode_aprovar_plano(plano_store: Any, justificativa_override: str | None = None) -> None:
    """Bloqueia aprovar_versao quando a última execução de alguma skill sinaliza
    inconsistência não resolvida entre preço de venda e custo operacional.

    ERRO em qualquer skill bloqueia sempre — não há escape (nada impede aprovar
    com ERRO pendente hoje, isto é uma rede de segurança independente do issue).

    Os AVISOs de _BLOCKING_AVISO_CODES bloqueiam, a menos que
    `justificativa_override` seja uma string não vazia (após strip) — o
    chamador (tool MCP) é responsável por registrar essa justificativa no
    audit trail.
    """
    invocations = plano_store.read_invocations()
    latest_by_skill = _latest_invocation_per_skill(invocations)
    erros, avisos = _collect_flags(latest_by_skill)

    if erros:
        detalhe = ", ".join(f"{codigo} ({skill})" for skill, codigo in erros)
        raise PlanoApprovalGateError(
            f"Aprovação bloqueada: há validações de status ERRO pendentes ({detalhe}). "
            "Corrija e reexecute a cadeia antes de aprovar."
        )

    if avisos and not (justificativa_override or "").strip():
        detalhe = ", ".join(f"{codigo} ({skill})" for skill, codigo in avisos)
        raise PlanoApprovalGateError(
            f"Aprovação bloqueada: sinais de inconsistência entre venda e custo operacional "
            f"não resolvidos ({detalhe}). Corrija os dados, ou aprove com "
            "justificativa_override preenchido para registrar a decisão consciente no audit trail."
        )
