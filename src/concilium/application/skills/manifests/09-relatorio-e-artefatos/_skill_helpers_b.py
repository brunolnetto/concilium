"""Skill 07 — Adapter de Saída (gera JSON + Excel .xlsm).

Skill 07 produz o output principal:
1. JSON estruturado (para validação, logs, API)
2. Excel .xlsm auditável (para stakeholders, relatórios)

Estrutura Excel gerada:
  - RESUMO: metadados do projeto + indicadores financeiros
  - PLANEJAMENTO: itens da EAP com preços, BDI, subtotais
  - EQUIPES: composição, custos e ponto de equilíbrio
  - INDIRETOS: custos indiretos por categoria
  - RESULTADO: resultado financeiro consolidado
"""

import math
from typing import Any

from concilium.domain.models.canonical import CanonicalModel

from ._skill_helpers_a import _week_to_month


def _mdc_accumulate_act(act: Any, cost_per_unit: dict, result: dict) -> None:
    """Accumulates monthly cost for one scheduled activity."""
    cpu = cost_per_unit.get(act.activity_id, 0.0)
    if cpu <= 0:
        return
    for week_key, dist in act.distribuicao_semanal.items():
        qtd = float(getattr(dist, "qtd_executada", 0.0) or 0.0)
        if qtd <= 0:
            continue
        ym = _week_to_month(week_key)
        if ym in result:
            result[ym] += cpu * qtd


def _monthly_direct_costs(canonical_in: CanonicalModel, project_months: list) -> dict:
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not project_months or not canonical_in.cronograma or not canonical_in.planejamento:
        return result
    cost_per_unit: dict[str, float] = {}
    for p in canonical_in.planejamento:
        total = p.subtotal.sem_bdi.total if p.subtotal else 0.0
        qty = p.quantitativo or 1.0
        cost_per_unit[p.item_id] = total / qty if qty > 0 else 0.0
    for act in canonical_in.cronograma.scheduled_activities:
        _mdc_accumulate_act(act, cost_per_unit, result)
    return result


def _monthly_indirect_costs(canonical_in: CanonicalModel, project_months: list) -> dict:
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not project_months:
        return result
    n = len(project_months)
    for ind in canonical_in.indiretos:
        if ind.categoria == "MOB":
            result[project_months[0]] += ind.custo_total
            continue
        perm = int(ind.permanencia_meses or n)
        meses_ativos = project_months[: min(perm, n)]
        if meses_ativos:
            por_mes = ind.custo_total / len(meses_ativos)
            for ym in meses_ativos:
                result[ym] += por_mes
    return result


def _cash_flow_rows(canonical_in: CanonicalModel, project_months: list) -> list[dict]:
    if not project_months or canonical_in.resultado is None:
        return []
    n = len(project_months)
    venda_total = canonical_in.resultado.venda.total_com_bdi
    parcela_base = math.floor(venda_total / n) if n else 0
    residuo = venda_total - parcela_base * (n - 1)
    all_months = project_months + [_next_month(project_months[-1])]
    receitas = [0.0] + [float(parcela_base)] * (n - 1) + [float(residuo)]
    direct = _monthly_direct_costs(canonical_in, project_months)
    indirect = _monthly_indirect_costs(canonical_in, project_months)
    rows: list[dict] = []
    despesa_acumulada = 0.0
    receita_acumulada = 0.0
    for idx, ym in enumerate(all_months):
        despesa = direct.get(ym, 0.0) + indirect.get(ym, 0.0)
        receita = receitas[idx]
        despesa_acumulada += despesa
        receita_acumulada += receita
        rows.append(
            {
                "mes_label": _fmt_mes(ym),
                "despesa": despesa,
                "receita": receita,
                "saldo": receita - despesa,
                "exposicao": despesa_acumulada - receita_acumulada,
            }
        )
    return rows
