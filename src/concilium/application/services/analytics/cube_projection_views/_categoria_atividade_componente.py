"""Shared projection builders for analytical cube visualizations and API payloads.

Linhas de categoria e atividade por componente.
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
from ._indireto_shared import _decompose_indireto_costs

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


def _accrue_indireto_categoria_componente(
    ind: Any, bdi_multipliers: dict[str, float], aggregated_cat: dict[str, dict[str, float]]
) -> None:
    mao, eq, verbas = _decompose_indireto_costs(ind)
    for cat_key, cat_cost in (("mao_obra", mao), ("equipamento", eq), ("verbas", verbas)):
        if cat_cost <= 0.0:
            continue
        for comp_name, comp_val in _split_operational_cost_with_bdi(cat_cost, bdi_multipliers).items():
            aggregated_cat[f"indireto.{cat_key}"][comp_name] += comp_val


def _resolve_categoria_componente_rows(
    cubo: Any, canonical: Any, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Agrupa por {direto,indireto}.{categoria} com o mesmo breakdown de componentes.
    # Direto: células do cubo com natureza='direto' (via _iter_scaled_cubo_cells).
    # Indireto: lido de canonical.indiretos decomposto em mao_obra/equipamento/verbas.
    aggregated_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    bdi_multipliers = _build_bdi_multipliers_from_cubo(cubo)
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        natureza_key = f"direto.{str(getattr(celula, 'categoria', '') or '')}"
        agg_comp = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        aggregated_cat[natureza_key][agg_comp] += float(valor_cell)
    # Indiretos de canonical.indiretos, decompostos em mao_obra/equipamento/verbas
    if canonical:
        for ind in getattr(canonical, "indiretos", None) or []:
            _accrue_indireto_categoria_componente(ind, bdi_multipliers, aggregated_cat)
    rows = [
        {"categoria": natureza_key, "componente_bdi": comp, "valor_rs": float(valor)}
        for natureza_key, comp_dict in aggregated_cat.items()
        for comp, valor in comp_dict.items()
    ]
    rows.sort(key=lambda row: -float(row["valor_rs"]))
    columns = [
        {"id": "categoria", "label": "Natureza.Categoria", "dtype": "str", "role": "y"},
        {"id": "componente_bdi", "label": "Componente", "dtype": "str", "role": "x"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "heatmap"


def _accrue_indireto_atividade_componente(
    ind: Any, bdi_multipliers: dict[str, float], aggregated_atv: dict[str, dict[str, float]]
) -> None:
    cat = str(getattr(ind, "categoria", "") or "")
    custo_total_ind = float(getattr(ind, "custo_total", 0.0) or 0.0)
    if not cat or custo_total_ind <= 0.0:
        return
    ind_key = f"indireto.{cat}"
    for comp_name, comp_val in _split_operational_cost_with_bdi(custo_total_ind, bdi_multipliers).items():
        aggregated_atv[ind_key][comp_name] += comp_val


def _resolve_atividade_componente_rows(
    cubo: Any, canonical: Any, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Chave composta {direto,indireto}.{atividade} com breakdown simétrico de componentes.
    # Direto: células cubo natureza='direto' → chave direto.eap-1_X
    # Indireto: células cubo natureza='indireto' → chave indireto.IND-{cat}
    aggregated_atv: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    bdi_multipliers = _build_bdi_multipliers_from_cubo(cubo)
    for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
        natureza_key = f"direto.{str(getattr(celula, 'atividade_id', '') or '')}"
        agg_comp = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        aggregated_atv[natureza_key][agg_comp] += float(valor_cell)
    # Indiretos de canonical.indiretos usando ind.categoria como chave
    if canonical:
        for ind in getattr(canonical, "indiretos", None) or []:
            _accrue_indireto_atividade_componente(ind, bdi_multipliers, aggregated_atv)
    rows = [
        {"atividade_id": natureza_key, "componente_bdi": comp, "valor_rs": float(valor)}
        for natureza_key, comp_dict in aggregated_atv.items()
        for comp, valor in comp_dict.items()
    ]
    rows.sort(key=lambda row: -float(row["valor_rs"]))
    columns = [
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "y"},
        {"id": "componente_bdi", "label": "Componente", "dtype": "str", "role": "x"},
        {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "heatmap"


