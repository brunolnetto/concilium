"""Skill 05 — custo MO/EQ por atividade a partir das testemunhas exatas P16.

Quando TODA a equipe padrão de uma atividade (equipamentos e funções) está
coberta por contratos com testemunha P16 exata, o custo contratual da atividade
deixa de vir do modelo legado (instâncias tarifadas, partição e reescala, MO como
resíduo) e passa a ser exatamente o que o ledger P16 cobra: K ativo das semanas
que a atividade possui + standby/MOB/DEMOB alocados pelas partições persistidas.
É a mesma grandeza que o P17-C reconcilia, de modo que o diagnóstico da Skill06,
os relatórios e o certificado falam do mesmo custo.

Cobertura parcial NÃO é completada nem zerada: a atividade mantém o legado e
recebe um AVISO nomeando os recursos sem contrato exato (o P17-C continuará NOGO).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction

from concilium.application.scheduling.skill06_p17_cost_reconciliation import (
    exact_activity_contractual_costs,
    exactly_covered_activities,
)
from concilium.domain.models.canonical import EquipeDireta, RecursoContrato, ResumoUtilizacaoContrato, ValidacaoItem


def aplicar_custo_exato_p16(
    equipes: Sequence[EquipeDireta],
    contratos: Sequence[RecursoContrato],
    validacoes: list[ValidacaoItem],
) -> None:
    witnessed = [c for c in contratos if c.p16_global_assignment]
    if not witnessed:
        return
    try:
        exact = exact_activity_contractual_costs(witnessed)
    except ValueError as exc:
        validacoes.append(ValidacaoItem(
            codigo="VAL-P16-CUSTO-EXATO",
            status="AVISO",
            mensagem=f"Testemunhas P16 inconsistentes; custo legado mantido: {exc}",
        ))
        return

    covered, missing = exactly_covered_activities(equipes, witnessed)
    for equipe in equipes:
        item_id = equipe.item_id
        if item_id not in exact:
            continue
        if item_id not in covered:
            validacoes.append(ValidacaoItem(
                codigo="VAL-P16-COBERTURA-PARCIAL",
                status="AVISO",
                mensagem=(
                    f"Item {item_id}: equipe sem contrato P16 exato para "
                    f"{', '.join(missing.get(item_id, []))}; custo legado mantido."
                ),
            ))
            continue
        mo, eq = exact[item_id]["MO"], exact[item_id]["EQ"]
        equipe.custo_inst_mo = round(float(mo), 2)
        equipe.custo_inst_eq = round(float(eq), 2)
        equipe.custo_total = round(
            equipe.custo_inst_mo + equipe.custo_inst_eq
            + float(equipe.custo_inst_comb or 0.0) + float(equipe.custo_inst_mat or 0.0),
            2,
        )
        validacoes.append(ValidacaoItem(
            codigo="VAL-P16-CUSTO-EXATO",
            status="OK",
            mensagem=f"Item {item_id}: custo MO/EQ derivado das testemunhas P16 exatas (MO={mo}, EQ={eq}).",
        ))


def resumo_alinhado_a_testemunha_p16(
    resumo: ResumoUtilizacaoContrato, witness: Mapping[str, object]
) -> ResumoUtilizacaoContrato:
    """Utilization summary consistent with the exact P16 witness (audited by V3).

    The legacy summary assumes every contracted unit is present for the whole
    contract; P16 brings units in only when demand needs them. Active and
    standby machine-weeks and the standby cost come from the witness; the rate
    and status are recomputed from them. Instance-level legacy detail is kept.
    """
    demand, standby = witness.get("demand"), witness.get("standby")
    costs = witness.get("costs")
    if not isinstance(demand, list) or not isinstance(standby, list) or not isinstance(costs, Mapping):
        raise ValueError(f"{resumo.contrato_id}: P16 witness lacks demand/standby/costs")
    used, idle = sum(demand), sum(standby)
    available = resumo.machine_weeks_disponiveis
    rate = round(used / available * 100, 1) if available > 0 else 100.0
    status = "OK" if rate >= 65.0 else "AVISO" if rate >= 35.0 else "CRITICO"
    return resumo.model_copy(update={
        "machine_weeks_usados": used,
        "machine_weeks_standby": idle,
        "custo_standby_total": round(float(Fraction(str(costs.get("standby")))), 2),
        "taxa_utilizacao_pct": rate,
        "status_utilizacao": status,
    })
