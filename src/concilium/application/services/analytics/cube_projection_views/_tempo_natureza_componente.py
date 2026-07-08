"""Shared projection builders for analytical cube visualizations and API payloads.

Linhas de tempo por natureza e componente.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from ._bdi_pool import (
    _build_bdi_multipliers_from_cubo,
    _iter_scaled_cubo_cells,
    _normalize_bdi_component,
    _split_operational_cost_with_bdi,
)
from ._indireto_shared import _custo_indireto_por_periodo, bucket_from_week_iso

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


def _accrue_tempo_natureza_cell(
    c: Any,
    granularidade: FaceGranularity,
    direto_por_bucket: dict[str, float],
    indireto_por_bucket: dict[str, float],
) -> None:
    nat = str(getattr(c, "natureza", "") or "")
    comp = str(getattr(c, "componente_bdi", "") or "")
    val = float(getattr(c, "valor_rs", 0.0) or 0.0)
    bucket = bucket_from_week_iso(str(getattr(c, "semana_iso", "") or ""), granularidade)
    if not bucket:
        return
    if nat == "direto" and comp == "custo_direto":
        direto_por_bucket[bucket] += val
    elif nat == "indireto" and comp == "custo_direto":
        indireto_por_bucket[bucket] += val


def _accumulate_tempo_natureza_from_cubo(
    cubo_obj: Any, granularidade: FaceGranularity
) -> tuple[dict[str, float], dict[str, float]]:
    """Acumula custo direto/indireto por bucket a partir das células do cubo_analitico."""
    direto_por_bucket: dict[str, float] = defaultdict(float)
    indireto_por_bucket: dict[str, float] = defaultdict(float)
    for c in cubo_obj.celulas:
        _accrue_tempo_natureza_cell(c, granularidade, direto_por_bucket, indireto_por_bucket)
    return direto_por_bucket, indireto_por_bucket


def _accumulate_tempo_natureza_from_scurve(
    canonical: Any, granularidade: FaceGranularity
) -> tuple[dict[str, float], dict[str, float]]:
    """Fallback: acumula custo direto/indireto por bucket via SCurveBuilder quando cubo não está disponível."""
    from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

    direto_por_bucket: dict[str, float] = defaultdict(float)
    indireto_por_bucket: dict[str, float] = defaultdict(float)
    s_curve = SCurveBuilder().build(canonical)
    for agg in s_curve.agregacao_semanal:
        bucket = bucket_from_week_iso(str(agg.semana_iso), granularidade)
        direto_por_bucket[bucket] += float(agg.custo_direto_semana or 0.0)
        indireto_por_bucket[bucket] += float(agg.custo_indireto_semana or 0.0)
    return direto_por_bucket, indireto_por_bucket


def _resolve_tempo_natureza_rows(
    canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Usar cubo_analitico enriquecido (fonte primária analítica).
    # O cubo tem cells natureza='direto' (escalonadas ao PUxQ) e natureza='indireto'
    # adicionadas pelo enriquecimento financeiro do CuboAnaliticoBuilder.
    # Filtramos componente_bdi='custo_direto' para não somar os overlays de BDI.
    cubo_obj = getattr(canonical, "cubo_analitico", None)
    if cubo_obj is not None and getattr(cubo_obj, "celulas", None):
        direto_por_bucket, indireto_por_bucket = _accumulate_tempo_natureza_from_cubo(cubo_obj, granularidade)
    else:
        direto_por_bucket, indireto_por_bucket = _accumulate_tempo_natureza_from_scurve(canonical, granularidade)

    all_buckets = sorted(set(direto_por_bucket) | set(indireto_por_bucket))
    rows = [{"periodo": b, "natureza": "direto", "valor_rs": direto_por_bucket.get(b, 0.0)} for b in all_buckets] + [
        {"periodo": b, "natureza": "indireto", "valor_rs": indireto_por_bucket.get(b, 0.0)} for b in all_buckets
    ]
    rows.sort(key=lambda row: (str(row["periodo"]), str(row["natureza"])))
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "natureza", "label": "Natureza", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


def _resolve_tempo_componente_rows(
    cubo: Any, canonical: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    aggregated: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        bucket = bucket_from_week_iso(str(celula.semana_iso), granularidade)
        comp = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        aggregated[bucket][comp] += float(valor_cell)
    # Adicionar custo_indireto de canonical.indiretos_semanal com o mesmo breakdown BDI.
    if canonical:
        bdi_multipliers = _build_bdi_multipliers_from_cubo(cubo)
        indireto_por_bucket = _custo_indireto_por_periodo(canonical, granularidade)
        for bucket, custo in indireto_por_bucket.items():
            for comp_name, comp_value in _split_operational_cost_with_bdi(custo, bdi_multipliers).items():
                aggregated[bucket][comp_name] += comp_value
    rows: list[dict[str, Any]] = []
    for periodo, comp_dict in aggregated.items():
        for componente, valor in comp_dict.items():
            rows.append({"periodo": periodo, "componente_bdi": componente, "valor_rs": float(valor)})
    rows.sort(key=lambda row: (str(row["periodo"]), -float(row["valor_rs"])))
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "componente_bdi", "label": "Componente BDI", "dtype": "str", "role": "series"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "line"


