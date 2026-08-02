"""ADR-173 F6 — Wiring real do roster de MO (ADR-154→160) em skill-05.

`aplicar_roster_custo_real_mo`/`roster_cobre_composicao_mo` (ADR-156,
`domain/services/financial/roster_custo_mo_substituicao.py`) existiam desde a
ADR-156 mas nunca eram chamadas por nenhum orquestrador real — só testes. Esta
função é o wiring: recebe `inputs["roster_mo"]` (lista de dicts crua, vinda de
`Escopo.roster_mo` via propagação genérica de `Runtime.run_skill_on_plano`,
ADR-173 D4/P7) e aplica substituição integral por função a cada
`RecursoContrato`, sem tocar contratos cujo roster não cobre integralmente a
composição — mesma disciplina de sempre (nunca substituição parcial).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import RecursoContrato
from concilium.domain.services.financial.roster_custo_mo import parse_roster_mo
from concilium.domain.services.financial.roster_custo_mo_substituicao import (
    aplicar_roster_custo_real_mo,
)


def aplicar_roster_a_contratos(
    contratos_recurso: list[RecursoContrato],
    roster_mo_raw: list[dict[str, Any]] | None,
) -> list[RecursoContrato]:
    """Aplica `aplicar_roster_custo_real_mo` a cada contrato, com o roster
    parseado de `inputs["roster_mo"]`. Retorna a mesma lista (novos objetos via
    `model_copy`) quando `roster_mo_raw` é vazio/None — sem custo de parsing
    nem substituição, comportamento idêntico ao atual (degradação segura)."""
    roster = parse_roster_mo(roster_mo_raw)
    if not roster:
        return contratos_recurso
    return [aplicar_roster_custo_real_mo(contrato, roster) for contrato in contratos_recurso]
