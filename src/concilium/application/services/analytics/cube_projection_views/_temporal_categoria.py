"""Shared projection builders for analytical cube visualizations and API payloads.

Linhas de categoria temporal (direto e indireto).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from ._bdi_pool import _iter_scaled_cubo_cells
from ._indireto_shared import _custo_indireto_por_periodo, _mob_eventos_por_periodo, bucket_from_week_iso

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


def _resolve_direto_temporal_categoria_rows(
    cubo: Any, canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    categories = ("MAO_OBRA", "EQUIP", "MAT", "COMB")
    cat_map = {
        "mao_obra": "MAO_OBRA",
        "equipamento": "EQUIP",
        "material": "MAT",
        "diesel": "COMB",
    }
    aggregated: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        comp = str(getattr(celula, "componente_bdi", "") or "")
        if comp != "custo_direto":
            continue
        cat_key = cat_map.get(str(getattr(celula, "categoria", "") or ""))
        if not cat_key:
            continue
        bucket = bucket_from_week_iso(str(getattr(celula, "semana_iso", "") or ""), granularidade)
        if bucket:
            aggregated[bucket][cat_key] += float(valor_cell)
    buckets = sorted(aggregated.keys())
    rows: list[dict[str, Any]] = []
    for bucket in buckets:
        for cat in categories:
            rows.append(
                {
                    "periodo": bucket,
                    "categoria_direto": cat,
                    "valor_rs": float(aggregated[bucket].get(cat, 0.0)),
                }
            )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "categoria_direto", "label": "Categoria Direta", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


def _indireto_categoria_from_atividade_id(aid: str) -> str:
    return aid.replace("IND-", "", 1).upper() if aid.startswith("IND-") else aid.upper()


def _accrue_indireto_temporal_cell(
    celula: Any,
    granularidade: FaceGranularity,
    categories: tuple[str, ...],
    aggregated: dict[str, dict[str, float]],
) -> None:
    nat = str(getattr(celula, "natureza", "") or "")
    comp = str(getattr(celula, "componente_bdi", "") or "")
    if nat != "indireto" or comp != "custo_direto":
        return
    cat = _indireto_categoria_from_atividade_id(str(getattr(celula, "atividade_id", "") or ""))
    if cat not in categories:
        return
    bucket = bucket_from_week_iso(str(getattr(celula, "semana_iso", "") or ""), granularidade)
    if bucket:
        aggregated[bucket][cat] += float(getattr(celula, "valor_rs", 0.0) or 0.0)


def _collect_indireto_temporal_cells(
    canonical: Any, granularidade: FaceGranularity, categories: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    aggregated: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cubo_obj = getattr(canonical, "cubo_analitico", None)
    cells = getattr(cubo_obj, "celulas", None) if cubo_obj is not None else None
    if cells:
        for celula in cells:
            _accrue_indireto_temporal_cell(celula, granularidade, categories, aggregated)
    return aggregated


def _rebalance_mob_by_eventos(
    aggregated: dict[str, dict[str, float]], canonical: Any, granularidade: FaceGranularity
) -> None:
    """Rebalanceia MOB por eventos reais do pool quando houver instâncias com
    mobilizações/desmobilizações intermediárias: evita falso sinal de concentração
    apenas no início/fim quando o indireto semanal veio agregado por driver de projeto.
    """
    if not canonical:
        return
    eventos_mob = _mob_eventos_por_periodo(canonical, granularidade)
    total_eventos = sum(eventos_mob.values())
    total_mob = sum(v.get("MOB", 0.0) for v in aggregated.values())
    if total_eventos > 0 and total_mob > 0.0 and len(eventos_mob) > 2:
        for b in list(aggregated.keys()):
            aggregated[b]["MOB"] = 0.0
        for bucket, n_evt in eventos_mob.items():
            aggregated[bucket]["MOB"] += total_mob * (float(n_evt) / float(total_eventos))


def _sum_indiretos_by_categoria(canonical: Any, categories: tuple[str, ...]) -> dict[str, float]:
    by_cat_total: dict[str, float] = {k: 0.0 for k in categories}
    for ind in getattr(canonical, "indiretos", None) or []:
        cat = str(getattr(ind, "categoria", "") or "").upper()
        if cat in by_cat_total:
            by_cat_total[cat] += float(getattr(ind, "custo_total", 0.0) or 0.0)
    return by_cat_total


def _category_shares_from_totals(by_cat_total: dict[str, float], categories: tuple[str, ...]) -> dict[str, float]:
    total_ind = sum(by_cat_total.values())
    if not by_cat_total:
        return {k: 1.0 / len(categories) for k in categories}
    return {k: (v / total_ind if total_ind > 0 else (1.0 / len(categories))) for k, v in by_cat_total.items()}


def _fallback_indireto_temporal_shares(
    aggregated: dict[str, dict[str, float]],
    canonical: Any,
    granularidade: FaceGranularity,
    categories: tuple[str, ...],
) -> None:
    """Fallback: se não houver células indiretas no cubo, distribui o indireto semanal
    por shares de categoria (ADM/TOP/LAB/QSMS/MOB) medidos em canonical.indiretos.
    """
    if aggregated or not canonical:
        return
    indireto_bucket = _custo_indireto_por_periodo(canonical, granularidade)
    by_cat_total = _sum_indiretos_by_categoria(canonical, categories)
    shares = _category_shares_from_totals(by_cat_total, categories)
    for bucket, total_bucket in indireto_bucket.items():
        for cat in categories:
            aggregated[bucket][cat] += float(total_bucket) * float(shares.get(cat, 0.0))


def _resolve_indireto_temporal_categoria_rows(
    canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    categories = ("ADM", "TOP", "LAB", "QSMS", "MOB")
    aggregated = _collect_indireto_temporal_cells(canonical, granularidade, categories)
    _rebalance_mob_by_eventos(aggregated, canonical, granularidade)
    _fallback_indireto_temporal_shares(aggregated, canonical, granularidade, categories)

    buckets = sorted(aggregated.keys())
    rows: list[dict[str, Any]] = []
    for bucket in buckets:
        for cat in categories:
            rows.append(
                {
                    "periodo": bucket,
                    "categoria_indireto": cat,
                    "valor_rs": float(aggregated[bucket].get(cat, 0.0)),
                }
            )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "categoria_indireto", "label": "Categoria Indireta", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


