"""PlanningLoop: orchestration utility for iterative decision application.

This is a minimal implementation for v2.5: it applies DV2 (num_equipes)
to `run_cronograma`, then `run_equipes_e_alocacao` and `run_custos_indiretos`, collects
constraint violations and returns (canonical, feasible, violations).
"""

from typing import Any

from concilium.application.skills import load_skill_stage, run_cronograma, run_equipes_e_alocacao
from concilium.domain.models import (
    CanonicalModel,
    ConstraintViolation,
    DecisionVariables,
)

# NEP-041 F4: o estágio de indiretos vive no sub-pacote da skill unificada.
# O loop re-roda apenas indiretos após ajuste de cronograma — uso de estágio, não da skill.
run_custos_indiretos = load_skill_stage("06-resultado-financeiro", "_indiretos", "run_custos_indiretos")


def _convert_validacoes_to_violations(validacoes: list[Any]) -> list[ConstraintViolation]:
    out: list[ConstraintViolation] = []
    for v in validacoes:
        if getattr(v, "status", None) == "ERRO":
            out.append(
                ConstraintViolation(
                    code=v.codigo, status=v.status, magnitude=None, affected_items=[], remediation_hint=v.mensagem
                )
            )
    return out


def _dv_to_dict(decision_variables) -> dict:
    if isinstance(decision_variables, DecisionVariables):
        return decision_variables.model_dump()
    if isinstance(decision_variables, dict):
        return decision_variables
    return {}


def _build_cron_inputs(decision_variables, extra_inputs: dict) -> dict:
    dv_dict = _dv_to_dict(decision_variables)
    num_equipes_por_item = dv_dict.get("dv2_num_equipes") or {}
    cron_inputs = {"num_equipes_por_item": num_equipes_por_item}
    cron_inputs.update(extra_inputs.get("cronograma", {}))
    return cron_inputs


def _run_equipes_step(can, decision_variables, extra_inputs, catalogo, validacoes, violations):
    ed_inputs = {"decision_variables": decision_variables} if decision_variables is not None else {}
    ed_inputs.update(extra_inputs.get("equipes", {}))
    ed_res = run_equipes_e_alocacao(can, ed_inputs, catalogo or {})
    can = ed_res.canonical
    validacoes = list(validacoes) + list(ed_res.validacoes)
    violations = list(violations)
    violations.extend(_convert_validacoes_to_violations(ed_res.validacoes))
    return can, validacoes, violations


def _run_indiretos_step(can, decision_variables, extra_inputs, perfil, validacoes, violations):
    ind_inputs = {"decision_variables": decision_variables} if decision_variables is not None else {}
    ind_inputs.update(extra_inputs.get("indiretos", {}))
    ind_res = run_custos_indiretos(can, ind_inputs, perfil=perfil)
    can = ind_res.canonical
    validacoes = list(validacoes) + list(ind_res.validacoes)
    violations = list(violations)
    violations.extend(_convert_validacoes_to_violations(ind_res.validacoes))
    return can, validacoes, violations


def adjust_schedule(
    canonical_in: CanonicalModel,
    decision_variables: DecisionVariables | dict | None,
    catalogo: dict[str, Any] | None,
    perfil: dict[str, Any] | None,
    extra_inputs: dict[str, Any] | None = None,
) -> tuple[CanonicalModel, bool, list[ConstraintViolation]]:
    """Apply a simple planning loop: cronograma -> equipes -> indiretos.

    Returns (canonical, feasible, violations).
    - feasible: True when no ValidacaoItem with status 'ERRO' and no ConstraintViolation with status 'ERRO'.
    - violations: aggregated ConstraintViolation objects from skills and converted errors.
    """
    if extra_inputs is None:
        extra_inputs = {}
    if catalogo is None:
        catalogo = {}
    if perfil is None:
        perfil = {}

    cron_inputs = _build_cron_inputs(decision_variables, extra_inputs)
    cron_res = run_cronograma(canonical_in, cron_inputs, catalogo)
    can = cron_res.canonical
    validacoes = list(cron_res.validacoes)
    violations: list[ConstraintViolation] = list(getattr(can, "constraint_violations", []) or [])
    violations.extend(_convert_validacoes_to_violations(validacoes))

    can, validacoes, violations = _run_equipes_step(
        can, decision_variables, extra_inputs, catalogo, validacoes, violations
    )
    can, validacoes, violations = _run_indiretos_step(
        can, decision_variables, extra_inputs, perfil, validacoes, violations
    )

    violations.extend(list(getattr(can, "constraint_violations", []) or []))
    has_error = any(v.status == "ERRO" for v in validacoes) or any(v.status == "ERRO" for v in violations)
    return can, not has_error, violations


__all__ = ["adjust_schedule"]
