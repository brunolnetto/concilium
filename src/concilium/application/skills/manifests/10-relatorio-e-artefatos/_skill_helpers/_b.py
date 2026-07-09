"""Skill 10 — Adapter de Saída (gera JSON + Excel .xlsm).

Skill 10 produz o output principal:
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

from concilium.domain.models.canonical import CanonicalModel

from ._cash_flow import _fmt_mes, _week_to_month  # ty: ignore[unresolved-import]


def _getstr(obj, attr: str, default: str = "") -> str:
    return str(getattr(obj, attr, default) or default)


def _getfloat(obj, attr: str) -> float:
    return float(getattr(obj, attr, 0.0) or 0.0)


def _add_part_cost(particao: dict, contrato) -> None:
    for part in getattr(contrato, "particao_por_item", None) or []:
        item_id = _getstr(part, "item_id")
        if not item_id:
            continue
        particao[item_id] = particao.get(item_id, 0.0) + _getfloat(part, "custo_total_particionado")


def _build_particao_by_item(canonical_in: CanonicalModel) -> dict[str, float]:
    particao: dict[str, float] = {}
    for contrato in canonical_in.contratos_recurso or []:
        _add_part_cost(particao, contrato)
    return particao


def _build_equipe_by_item(canonical_in: CanonicalModel) -> dict:
    return {str(eq.item_id): eq for eq in (canonical_in.equipes_diretas or []) if getattr(eq, "item_id", None)}


def _build_sched_by_item(canonical_in: CanonicalModel) -> dict:
    cronograma = getattr(canonical_in, "cronograma", None)
    if not cronograma:
        return {}
    sched: dict = {}
    for sa in getattr(cronograma, "scheduled_activities", None) or []:
        aid = _getstr(sa, "activity_id")
        if aid:
            sched[aid] = sa
    return sched


def _build_pesos_semana(dist, result: dict) -> dict:
    pesos: dict = {}
    for wk, d in dist.items():
        peso = _getfloat(d, "num_equipes")
        if peso <= 0.0:
            continue
        ym = _week_to_month(str(wk))
        if ym in result:
            pesos[ym] = pesos.get(ym, 0.0) + peso
    return pesos


def _resolve_item_cost(particao_by_item: dict, item_id: str, eq) -> float:
    custo = float(particao_by_item.get(item_id, 0.0) or 0.0)
    if custo <= 0.0:
        custo = _getfloat(eq, "custo_total")
    return custo


def _apply_pesos_to_result(result: dict, pesos_semana: dict, custo_item: float, project_months: list) -> None:
    soma_pesos = sum(pesos_semana.values())
    if soma_pesos <= 0.0:
        result[project_months[0]] += custo_item
        return
    for ym, peso in pesos_semana.items():
        result[ym] += custo_item * (peso / soma_pesos)


def _distribute_item_cost(
    result: dict, item_id: str, eq, particao_by_item: dict, sched_by_item: dict, project_months: list
) -> None:
    custo_item = _resolve_item_cost(particao_by_item, item_id, eq)
    if custo_item <= 0.0:
        return
    sa = sched_by_item.get(item_id)
    dist = getattr(sa, "distribuicao_semanal", None) if sa is not None else None
    if not dist:
        result[project_months[0]] += custo_item
        return
    pesos_semana = _build_pesos_semana(dist, result)
    _apply_pesos_to_result(result, pesos_semana, custo_item, project_months)


def _distribute_indirect(result: dict, ind, project_months: list, n: int) -> None:
    if ind.categoria == "MOB":
        result[project_months[0]] += ind.custo_total
        return
    perm = int(ind.permanencia_meses or n)
    meses_ativos = project_months[: min(perm, n)]
    if meses_ativos:
        por_mes = ind.custo_total / len(meses_ativos)
        for ym in meses_ativos:
            result[ym] += por_mes


def _monthly_direct_costs(canonical_in: CanonicalModel, project_months: list) -> dict:
    """Custo direto operacional por mês com base em partição de pool por item.

    Regra: para cada atividade, usar custo_total_particionado (ADR-071 D3) quando
    disponível; fallback para equipe.custo_total. O total do item é distribuído nas
    semanas ativas proporcionalmente a num_equipes (intensidade instancial).
    """
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not project_months:
        return result
    particao_by_item = _build_particao_by_item(canonical_in)
    equipe_by_item = _build_equipe_by_item(canonical_in)
    sched_by_item = _build_sched_by_item(canonical_in)
    for item_id, eq in equipe_by_item.items():
        _distribute_item_cost(result, item_id, eq, particao_by_item, sched_by_item, project_months)
    return result


def _monthly_indirect_costs(canonical_in: CanonicalModel, project_months: list) -> dict:
    result: dict[tuple[int, int], float] = {ym: 0.0 for ym in project_months}
    if not project_months:
        return result
    n = len(project_months)
    for ind in canonical_in.indiretos:
        _distribute_indirect(result, ind, project_months, n)
    return result


def _cash_flow_rows(canonical_in: CanonicalModel, project_months: list) -> list[dict]:
    if not project_months or canonical_in.resultado is None:
        return []
    n = len(project_months)
    venda_total = canonical_in.resultado.venda.total_com_bdi
    parcela_base = math.floor(venda_total / n) if n else 0
    residuo = venda_total - parcela_base * (n - 1)
    # Receita distribuída uniformemente a partir do primeiro mês
    receitas = [float(parcela_base)] * (n - 1) + [float(residuo)]
    direct = _monthly_direct_costs(canonical_in, project_months)
    indirect = _monthly_indirect_costs(canonical_in, project_months)
    rows: list[dict] = []
    despesa_acumulada = 0.0
    receita_acumulada = 0.0
    for idx, ym in enumerate(project_months):
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
