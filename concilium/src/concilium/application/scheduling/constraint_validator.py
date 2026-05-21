"""ADR-006 — ConstraintValidator: planning-phase hard constraint checks.

Returns ConstraintViolation objects (non-raising) so that violations
can be surfaced to the engineer for preventive replanning.

Checks:
  C2 — deadline:   makespan_weeks must not exceed contract duration
  C3 — resources:  no week may exceed pool capacity (reads conflitos_pico)
  F1 — budget:     total indiretos must not exceed budget_indiretos (optional)
"""

from __future__ import annotations

from concilium.domain.models.canonical import CanonicalModel
from concilium.domain.models.constraint_violation import ConstraintViolation


class ConstraintValidator:
    """Validates a CanonicalModel against hard planning constraints (ADR-006).

    Unlike ScheduleValidator (which raises assertions for algorithm use),
    this class returns ConstraintViolation objects — enabling the ADR-006
    preventive replan loop: validate -> identify violation -> generate options
    -> engineer decides -> recalculate -> validate again.
    """

    def validate(
        self,
        canonical: CanonicalModel,
        budget_indiretos: float | None = None,
    ) -> list[ConstraintViolation]:
        """Run all enabled hard-constraint checks.

        Args:
            canonical: Current project canonical model.
            budget_indiretos: Optional budget ceiling for indirect costs (R$).
                              If None, F1 check is skipped.

        Returns:
            List of ConstraintViolation objects (empty if all constraints pass).
        """
        violations: list[ConstraintViolation] = []
        violations.extend(self._check_deadline(canonical))
        violations.extend(self._check_resource_pool(canonical))
        if budget_indiretos is not None:
            violations.extend(self._check_budget(canonical, budget_indiretos))
        return violations

    def _check_deadline(self, canonical: CanonicalModel) -> list[ConstraintViolation]:
        """C2 — schedule makespan must not exceed contract duration."""
        cronograma = canonical.cronograma
        if cronograma is None or not cronograma.scheduled_activities:
            return []

        data_inicio = canonical.projeto.data_inicio
        data_termino = canonical.projeto.data_termino
        contract_weeks = int((data_termino - data_inicio).days / 7)

        makespan = cronograma.makespan_weeks
        if makespan > contract_weeks:
            excesso = makespan - contract_weeks
            return [
                ConstraintViolation(
                    code="VAL-SCHED-WEEKLY-03",
                    status="ERRO",
                    magnitude=float(excesso),
                    affected_items=["cronograma"],
                    remediation_hint=(
                        f"Cronograma precisa de {makespan} semanas mas prazo contratual é "
                        f"{contract_weeks} semanas (excesso: {excesso} sem). "
                        "Opções: estender prazo, adicionar recursos ou reduzir escopo."
                    ),
                )
            ]
        return []

    def _check_resource_pool(self, canonical: CanonicalModel) -> list[ConstraintViolation]:
        """C3 — resource demands must not exceed pool in any week (reads conflitos_pico)."""
        violations: list[ConstraintViolation] = []
        for conflito in canonical.conflitos_pico:
            violations.append(
                ConstraintViolation(
                    code="VAL-SCHED-WEEKLY-05",
                    status="ERRO",
                    magnitude=float(conflito.excedente),
                    affected_items=list(conflito.atividades_conflitantes),
                    remediation_hint=(
                        f"Recurso '{conflito.tipo_nome}': demanda "
                        f"{conflito.quantidade_necessaria:.0f} excede pool "
                        f"{conflito.quantidade_disponivel} em {conflito.excedente:.0f} unidades. "
                        "Opções: ampliar pool OU adiar atividades conflitantes."
                    ),
                )
            )
        return violations

    def _check_budget(
        self,
        canonical: CanonicalModel,
        budget_indiretos: float,
    ) -> list[ConstraintViolation]:
        """F1 — total indirect costs must not exceed budget_indiretos."""
        total = sum(i.custo_total for i in canonical.indiretos)
        if total > budget_indiretos:
            excesso = total - budget_indiretos
            return [
                ConstraintViolation(
                    code="VAL-INDIRETOS-04",
                    status="ERRO",
                    magnitude=float(excesso),
                    affected_items=["indiretos"],
                    remediation_hint=(
                        f"Custo indireto total R$ {total:,.2f} excede orçamento "
                        f"R$ {budget_indiretos:,.2f} em R$ {excesso:,.2f}. "
                        "Opções: reduzir prazo (reduz permanência) ou reduzir escopo."
                    ),
                )
            ]
        return []
