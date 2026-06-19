from __future__ import annotations

import math
from typing import Any

from concilium.domain.models.canonical import CanonicalModel

from .helpers import _fmt_mes, _project_months, _week_to_month


def _mdc_accumulate_act(act, cost_per_unit: dict, result: dict) -> None:
    """Accumulate direct costs for one scheduled activity into result dict."""
    cpu = cost_per_unit.get(act.activity_id, 0.0)
    if cpu <= 0:
        return
    for week_key, dist in act.distribuicao_semanal.items():
        qtd = getattr(dist, "qtd_executada", 0.0)
        if qtd <= 0:
            continue
        ym = _week_to_month(week_key)
        if ym in result:
            result[ym] += cpu * qtd


def _monthly_direct_costs(
    canonical: CanonicalModel,
    project_months: list[tuple[int, int]],
) -> dict[tuple[int, int], float]:
    """Despesa direta por mês: custo catálogo (s/BDI) distribuído
    proporcionalmente à quantidade executada por semana.
    """
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not canonical.cronograma or not canonical.planejamento:
        return result

    cost_per_unit: dict[str, float] = {}
    for p in canonical.planejamento:
        total = p.subtotal.sem_bdi.total if p.subtotal else 0.0
        qty = p.quantitativo or 1.0
        cost_per_unit[p.item_id] = total / qty if qty > 0 else 0.0

    for act in canonical.cronograma.scheduled_activities:
        _mdc_accumulate_act(act, cost_per_unit, result)

    return result


def _monthly_indirect_costs(
    canonical: CanonicalModel,
    project_months: list[tuple[int, int]],
) -> dict[tuple[int, int], float]:
    """Despesa indireta por mês.

    MOB: concentrado no mês 1 (mobilização) e ignorado no final (simplificação).
    ADM/TOP/LAB/QSMS: distribuídos uniformemente pelos meses de permanência.
    """
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    n = len(project_months)
    if n == 0:
        return result

    for ind in canonical.indiretos:
        if ind.categoria == "MOB":
            result[project_months[0]] += ind.custo_total
        else:
            perm = int(ind.permanencia_meses or n)
            meses_ativos = project_months[: min(perm, n)]
            if meses_ativos:
                por_mes = ind.custo_total / len(meses_ativos)
                for ym in meses_ativos:
                    result[ym] += por_mes

    return result


def _next_month(ym: tuple[int, int]) -> tuple[int, int]:
    """Retorna o mês seguinte ao dado."""
    year, month = ym
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _cash_flow(
    canonical: CanonicalModel,
) -> list[dict[str, Any]]:
    """Retorna lista de registros mensais de fluxo de caixa.

    Esquema de receita (n = duração do projeto em meses):
      • Mês 1          : receita = 0           (empresa inicia sem recebimento)
      • Meses 2 .. n   : receita = floor(M/n)  cada
      • Mês n+1        : receita = M − floor(M/n)×(n−1)  (resíduo, mês extra pós-execução)

    Total verificado: 0 + (n−1)×floor(M/n) + (M − floor(M/n)×(n−1)) = M ✓

    Exposição = despesa_acumulada − receita_acumulada.
    Positivo -> empresa desembolsou mais do que recebeu (necessidade de capital de giro).
    """
    project_months = _project_months(canonical)
    n = len(project_months)
    if n == 0 or canonical.resultado is None:
        return []

    M = canonical.resultado.venda.total_com_bdi
    parcela_base = math.floor(M / n)
    residuo = M - parcela_base * (n - 1)

    # Meses de execução + 1 mês extra para o resíduo
    all_months = project_months + [_next_month(project_months[-1])]

    # Receita por posição: índice 0 = mês 1 (zero), índices 1..n-1 = parcela_base, índice n = resíduo
    receitas: list[float] = [0.0] + [float(parcela_base)] * (n - 1) + [float(residuo)]

    direct = _monthly_direct_costs(canonical, project_months)
    indirect = _monthly_indirect_costs(canonical, project_months)

    rows = []
    acum_despesa = 0.0
    acum_receita = 0.0
    for i, ym in enumerate(all_months):
        despesa = direct.get(ym, 0.0) + indirect.get(ym, 0.0)
        receita = receitas[i]
        saldo = receita - despesa
        acum_despesa += despesa
        acum_receita += receita
        rows.append(
            {
                "mes_label": _fmt_mes(ym),
                "mes_ym": ym,
                "despesa": despesa,
                "receita": receita,
                "despesa_acumulada": acum_despesa,
                "receita_acumulada": acum_receita,
                "saldo": saldo,
                "saldo_atual": acum_receita - acum_despesa,  # = -(exposição)
                "exposicao_acumulada": acum_despesa - acum_receita,
            }
        )
    return rows


def _monthly_qty_by_item(
    canonical: CanonicalModel,
    project_months: list[tuple[int, int]],
) -> dict[str, dict[tuple[int, int], float]]:
    """Para cada activity_id, qtd executada por mês."""
    result: dict[str, dict[tuple[int, int], float]] = {}
    if not canonical.cronograma:
        return result
    for act in canonical.cronograma.scheduled_activities:
        per_month: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
        for week_key, dist in act.distribuicao_semanal.items():
            ym = _week_to_month(week_key)
            if ym in per_month:
                per_month[ym] += getattr(dist, "qtd_executada", 0.0)
        result[act.activity_id] = per_month
    return result
