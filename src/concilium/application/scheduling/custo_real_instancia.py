"""ADR-158 D2 — Custo real por instância: timeline analítica prod/idle/off.

Combina `project_ocupacao_semanal` (ADR-152, status prod/idle/off por instância)
com as taxas médias reais de MO/EQ do contrato (ADR-156/157, pós
`aplicar_roster_custo_real_mo`/`_eq`), seguindo a mesma assimetria prod/idle do
`LifecycleEngine` (ADR-085/106): MO integral em ambos (CLT); EQ reduzido (só
locação) em idle.

Sem atribuição de indivíduo/ativo real a um slot específico — todas as instâncias
de um tipo usam a mesma taxa média real, exatamente como o sistema calibrado já
faz hoje. O pool RCPSP permanece fungível; `identidade_fisica_id` (ADR-153)
permanece dormente e não é necessária para este cálculo.
"""

from __future__ import annotations

from concilium.application.scheduling.pool_timelapse import project_ocupacao_semanal
from concilium.domain.models.canonical import InstanciaRecurso


def custo_real_instancia_semanal(
    instancia: InstanciaRecurso,
    cus_mo_real: float,
    cus_eq_real: float,
    cus_eq_idle_real: float,
) -> dict[str, float]:
    """Custo real por semana de uma instância, seguindo a assimetria prod/idle/off:

        "prod" -> cus_mo_real + cus_eq_real       (taxa ativa cheia)
        "idle" -> cus_mo_real + cus_eq_idle_real  (MO integral, EQ reduzido)
        "off"  -> 0.0

    `cus_mo_real`/`cus_eq_real` são as taxas médias reais do contrato inteiro
    (`RecursoContrato.custo_unit_semanal_mo`/`_eq` pós substituição, ADR-156/157) —
    não há atribuição de indivíduo/ativo a slot específico.
    """
    ocupacao = project_ocupacao_semanal(instancia)
    custo: dict[str, float] = {}
    for semana, status in ocupacao.items():
        if status == "prod":
            custo[semana] = round(cus_mo_real + cus_eq_real, 2)
        elif status == "idle":
            custo[semana] = round(cus_mo_real + cus_eq_idle_real, 2)
        else:
            custo[semana] = 0.0
    return custo
