"""Shared projection builders for analytical cube visualizations and API payloads.

Helpers compartilhados de custo indireto por período.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Literal

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


def _extract_cost_from_dict_entry(entry: dict[Any, Any]) -> float | None:
    """Extrai custo de um dict-entry, ou None se nenhum campo reconhecido estiver presente."""
    for key in ("custo_total", "custo_mensal_total", "custo_mensal", "valor", "custo"):
        if key in entry and isinstance(entry.get(key), (int, float)):
            return float(entry.get(key) or 0.0)
    qtd = float(entry.get("quantidade", 0.0) or 0.0)
    unit = float(entry.get("custo_unitario", 0.0) or 0.0)
    if qtd > 0.0 and unit > 0.0:
        return qtd * unit
    return None


def _extract_cost_from_entry(entry: Any) -> float:
    if isinstance(entry, dict):
        cost = _extract_cost_from_dict_entry(entry)
        if cost is not None:
            return cost
    return float(getattr(entry, "custo_total", 0.0) or 0.0)


def _indireto_list(ind: Any, attr: str) -> list[Any]:
    """Retorna a lista no atributo `attr` de um indireto, ou [] quando ausente/None."""
    return getattr(ind, attr, None) or []


def _mob_custo_total(mob: Any) -> float:
    return float(getattr(mob, "custo_total", 0.0) or 0.0)


def _decompose_indireto_costs(ind: Any) -> tuple[float, float, float]:
    """Decompoe um indireto em (mao_obra, equipamento, verbas), rebalanceados por custo_total."""
    mao = sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "funcoes"))
    eq = sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "equipamentos"))
    verbas = sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "verbas_mensais"))
    verbas += sum(_extract_cost_from_entry(x) for x in _indireto_list(ind, "verbas_fixas"))
    verbas += sum(_mob_custo_total(mob) for mob in _indireto_list(ind, "mobilizacoes"))
    sub = mao + eq + verbas
    custo_total = float(getattr(ind, "custo_total", 0.0) or 0.0)
    if sub > 0.0 and custo_total > 0.0:
        factor = custo_total / sub
        mao *= factor
        eq *= factor
        verbas *= factor
    elif custo_total > 0.0:
        verbas += custo_total
    return mao, eq, verbas


def _build_indireto_component_totals(canonical: Any) -> dict[str, float]:
    """Agrupa indiretos em mao_obra, equipamento e verbas."""
    totals = {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 0.0}
    for ind in getattr(canonical, "indiretos", None) or []:
        mao, eq, verbas = _decompose_indireto_costs(ind)
        totals["mao_obra"] += mao
        totals["equipamento"] += eq
        totals["verbas"] += verbas
    return totals


def _indireto_component_shares(canonical: Any) -> dict[str, float]:
    totals = _build_indireto_component_totals(canonical)
    total = totals["mao_obra"] + totals["equipamento"] + totals["verbas"]
    if total <= 0.0:
        return {"mao_obra": 0.0, "equipamento": 0.0, "verbas": 1.0}
    return {k: float(v) / total for k, v in totals.items()}


def _custo_indireto_por_periodo(canonical: Any, granularidade: FaceGranularity) -> dict[str, float]:
    """Mapeia canonical.indiretos_semanal para buckets por granularidade.

    O campo IndiretoSemanal.semana é um índice (offset 0-based) na lista de semanas ISO
    ordenadas do cronograma. Aqui reconstruímos a lista de semanas para fazer o mapeamento.
    """
    acts = []
    cronograma = getattr(canonical, "cronograma", None)
    if cronograma:
        acts = getattr(cronograma, "scheduled_activities", None) or []
    if not acts:
        return {}
    semanas_set: set[str] = set()
    for act in acts:
        for wk in getattr(act, "distribuicao_semanal", None) or {}:
            semanas_set.add(wk)
    semanas_sorted = sorted(semanas_set)
    result: dict[str, float] = defaultdict(float)
    for ind in getattr(canonical, "indiretos_semanal", None) or []:
        offset = ind.semana
        if 0 <= offset < len(semanas_sorted):
            bucket = bucket_from_week_iso(semanas_sorted[offset], granularidade)
            result[bucket] += ind.custo_semanal
    return dict(result)


def _mob_eventos_por_periodo(canonical: Any, granularidade: FaceGranularity) -> dict[str, int]:
    """Conta eventos de mobilização/desmobilização por bucket temporal a partir das instâncias."""
    result: dict[str, int] = defaultdict(int)
    for inst in getattr(canonical, "instancias_recurso", None) or []:
        for key in ("semana_mobilizacao", "semana_desmobilizacao"):
            semana_iso = str(getattr(inst, key, "") or "")
            if not semana_iso:
                continue
            bucket = bucket_from_week_iso(semana_iso, granularidade)
            result[bucket] += 1
    return dict(result)


def bucket_from_week_iso(week_iso: str, granularidade: FaceGranularity) -> str:
    if granularidade == "semana":
        return week_iso
    year_str, week_str = week_iso.split("-W", 1)
    anchor = date.fromisocalendar(int(year_str), int(week_str), 1)
    if granularidade == "mes":
        return f"{anchor.year:04d}-{anchor.month:02d}"
    if granularidade == "bimestre":
        bimestre = ((anchor.month - 1) // 2) + 1
        return f"{anchor.year:04d}-B{bimestre}"
    if granularidade == "trimestre":
        trimestre = ((anchor.month - 1) // 3) + 1
        return f"{anchor.year:04d}-T{trimestre}"
    if granularidade == "semestre":
        semestre = ((anchor.month - 1) // 6) + 1
        return f"{anchor.year:04d}-S{semestre}"
    if granularidade == "ano":
        return f"{anchor.year:04d}"
    raise ValueError(f"Granularidade inválida: {granularidade}")


