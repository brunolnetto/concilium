"""Skill 09 — Decision Log.

Registra justificativa de uma decisão técnica tomada pelo humano.
Persiste em decision_log.json. Não computa nada — apenas estrutura e valida.

Inputs (via dict 'inputs'):
    objective: str           — OBRIGATÓRIO
    considered_interventions: list[dict]  — OBRIGATÓRIO (pelo menos 1)
    selected_intervention: str|null  — OBRIGATÓRIO (pode ser null)
    justification: dict      — OBRIGATÓRIO
    decided_by: dict         — OBRIGATÓRIO; {type, id}
    decision_id: str         — opcional; gerado se ausente
    constraints: list[str]   — opcional
    expected_outcome: dict   — opcional; {margem, prazo_dias}
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem


def _rrd_validate_required_fields(inputs: dict, validacoes: list) -> None:
    for field in ("objective", "justification", "decided_by"):
        if not inputs.get(field):
            validacoes.append(
                ValidacaoItem(codigo="VAL-DEC-01", status="ERRO", mensagem=f"Campo obrigatório ausente: '{field}'")
            )


def _rrd_validate_rejected(considered: list, selected: Any, justification: dict, validacoes: list) -> None:
    rejected = [c for c in considered if c.get("variavel") != selected]
    if rejected and not justification.get("rejected_reasons"):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-DEC-03",
                status="AVISO",
                mensagem="Intervenções rejeitadas sem 'rejected_reasons' na justificativa",
            )
        )


def run_registro_decisoes(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    *_args: Any,
) -> SkillResult:
    """Valida e estrutura log de decisão.

    O artefato decision_log.json é persistido pelo runtime/CLI no diretório
    da versão do projeto. Esta skill apenas valida os inputs e retorna o
    registro estruturado via result.decision_log.
    """
    validacoes: list[ValidacaoItem] = []

    # VAL-DEC-01: selected_intervention deve estar explicitamente presente
    if "selected_intervention" not in inputs:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-DEC-01",
                status="ERRO",
                mensagem="'selected_intervention' obrigatório (pode ser null para 'não fazer nada')",
            )
        )

    # VAL-DEC-02: pelo menos uma intervenção considerada
    considered = inputs.get("considered_interventions", [])
    if not considered:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-DEC-02",
                status="ERRO",
                mensagem="'considered_interventions' deve ter pelo menos uma entrada",
            )
        )

    # Campos obrigatórios simples
    _rrd_validate_required_fields(inputs, validacoes)
    has_errors = any(v.status == "ERRO" for v in validacoes)
    if has_errors:
        return SkillResult(canonical_in, validacoes)

    # VAL-DEC-03: rejeitadas devem ter razões se houver > 1 alternativa
    selected = inputs["selected_intervention"]
    justification = inputs["justification"]
    _rrd_validate_rejected(considered, selected, justification, validacoes)

    entry = {
        "decision_id": inputs.get("decision_id", f"dec_{uuid4().hex[:8]}"),
        "project_version": canonical_in.projeto.id if canonical_in else "?",
        "context": {
            "objective": inputs["objective"],
            "constraints": inputs.get("constraints", []),
        },
        "considered_interventions": considered,
        "selected_intervention": selected,
        "justification": justification,
        "expected_outcome": inputs.get("expected_outcome", {}),
        "decided_by": inputs["decided_by"],
        "timestamp": datetime.now(UTC).isoformat(),
    }

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-DEC-01",
            status="OK",
            mensagem=f"Decisão registrada: {entry['decision_id']}",
        )
    )

    result = SkillResult(canonical_in, validacoes)
    result.decision_log = entry
    return result
