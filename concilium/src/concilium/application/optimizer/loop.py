"""PlanningLoop: orchestration utility for iterative decision application.

This is a minimal implementation for v2.5: it applies DV2 (num_equipes)
to `run_cronograma`, then `run_equipes_e_alocacao` and `run_custos_indiretos`, collects
constraint violations and returns (canonical, feasible, violations).
"""

from typing import Any

from concilium.application.skills import run_cronograma, run_custos_indiretos, run_equipes_e_alocacao
from concilium.domain.models import (
    CanonicalModel,
    ConstraintViolation,
    DecisionVariables,
)


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

    # Prepare inputs for cronograma from decision variables
    dv_dict: dict = {}
    if isinstance(decision_variables, DecisionVariables):
        dv_dict = decision_variables.model_dump()
    elif isinstance(decision_variables, dict):
        dv_dict = decision_variables

    num_equipes_por_item = dv_dict.get("dv2_num_equipes") or {}
    cron_inputs = {"num_equipes_por_item": num_equipes_por_item}
    cron_inputs.update(extra_inputs.get("cronograma", {}))

    # Run cronograma
    cron_res = run_cronograma(canonical_in, cron_inputs, catalogo)
    can = cron_res.canonical
    validacoes = list(cron_res.validacoes)

    # Collect structured violations that cronograma may have appended
    violations: list[ConstraintViolation] = list(getattr(can, "constraint_violations", []) or [])

    # Convert any ERRO validacoes to ConstraintViolation
    violations.extend(_convert_validacoes_to_violations(validacoes))

    # Run equipes_diretas (pass-through decision variables in inputs)
    ed_inputs = {"decision_variables": decision_variables} if decision_variables is not None else {}
    ed_inputs.update(extra_inputs.get("equipes", {}))
    ed_res = run_equipes_e_alocacao(can, ed_inputs, catalogo or {})
    can = ed_res.canonical
    validacoes.extend(ed_res.validacoes)
    violations.extend(_convert_validacoes_to_violations(ed_res.validacoes))

    # Run indiretos
    ind_inputs = {"decision_variables": decision_variables} if decision_variables is not None else {}
    ind_inputs.update(extra_inputs.get("indiretos", {}))
    ind_res = run_custos_indiretos(can, ind_inputs, perfil=perfil)
    can = ind_res.canonical
    validacoes.extend(ind_res.validacoes)
    violations.extend(_convert_validacoes_to_violations(ind_res.validacoes))

    # Also include any constraint_violations attached to final canonical
    violations.extend(list(getattr(can, "constraint_violations", []) or []))

    # Determine feasibility
    has_error = any(v.status == "ERRO" for v in validacoes) or any(v.status == "ERRO" for v in violations)
    feasible = not has_error

    return can, feasible, violations


__all__ = ["adjust_schedule"]
