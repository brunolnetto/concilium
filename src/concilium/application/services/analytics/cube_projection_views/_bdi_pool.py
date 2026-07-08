"""Shared projection builders for analytical cube visualizations and API payloads.

Multiplicadores de BDI e partição/escala de pool.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


FACE_UNIT_TYPES: dict[str, str] = {
    "tempo_natureza": "currency_brl",
    "tempo_componente": "currency_brl",
    "direto_temporal_categoria": "currency_brl",
    "indireto_temporal_categoria": "currency_brl",
    "categoria_componente": "currency_brl",
    "atividade_componente": "currency_brl",
    "diesel_temporal": "volume_liters",
    "abc_curva": "currency_brl",
    "s_curve_custo": "currency_brl",
    "recursos_ativos_tempo": "count",
}


_OVERHEAD_COMPONENTS = frozenset({"overhead_ac", "overhead_df", "overhead_r", "overhead_cr"})


_TRIBUTO_COMPONENTS = frozenset({"tributo_cofins", "tributo_iss", "tributo_pis", "tributo_cssl", "tributo_ir"})


def _normalize_bdi_component(component: str) -> str:
    """Normaliza componentes BDI para buckets de visualizacao estaveis."""
    if component in _OVERHEAD_COMPONENTS:
        return "Overhead BDI"
    if component in _TRIBUTO_COMPONENTS:
        return "Tributos"
    if component == "margem_l":
        return "Lucro (L)"
    if component in {"custo_direto", "custo_indireto"}:
        return "Custo operacional"
    return component


def _build_bdi_multipliers_from_cubo(cubo: Any) -> dict[str, float]:
    """Extrai multiplicadores implicitos de BDI a partir da composicao real do cubo.

    Os multiplicadores sao razoes sobre custo_operacional, mantendo o comportamento
    deterministico com base no proprio dataset do projeto.
    """
    totals: dict[str, float] = defaultdict(float)
    for celula in getattr(cubo, "celulas", None) or []:
        norm = _normalize_bdi_component(str(getattr(celula, "componente_bdi", "")))
        totals[norm] += float(getattr(celula, "valor_rs", 0.0) or 0.0)
    base = float(totals.get("Custo operacional", 0.0))
    if base <= 0.0:
        return {"Overhead BDI": 0.0, "Lucro (L)": 0.0, "Tributos": 0.0}
    return {
        "Overhead BDI": float(totals.get("Overhead BDI", 0.0)) / base,
        "Lucro (L)": float(totals.get("Lucro (L)", 0.0)) / base,
        "Tributos": float(totals.get("Tributos", 0.0)) / base,
    }


def _split_operational_cost_with_bdi(base_cost: float, multipliers: dict[str, float]) -> dict[str, float]:
    """Decompoe um custo operacional em custo+overhead+lucro+tributos."""
    base = float(base_cost or 0.0)
    return {
        "Custo operacional": base,
        "Overhead BDI": base * float(multipliers.get("Overhead BDI", 0.0)),
        "Lucro (L)": base * float(multipliers.get("Lucro (L)", 0.0)),
        "Tributos": base * float(multipliers.get("Tributos", 0.0)),
    }


def _build_pool_particao_by_item(canonical: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    if not canonical:
        return result
    for contrato in getattr(canonical, "contratos_recurso", None) or []:
        for part in getattr(contrato, "particao_por_item", None) or []:
            item_id = str(getattr(part, "item_id", "") or "")
            if not item_id:
                continue
            result[item_id] = result.get(item_id, 0.0) + float(getattr(part, "custo_total_particionado", 0.0) or 0.0)
    return result


def _accumulate_direto_base_by_item(cubo: Any) -> dict[str, float]:
    """Soma valor_rs de custo_direto (exceto material) por atividade_id."""
    base_by_item: dict[str, float] = defaultdict(float)
    for celula in getattr(cubo, "celulas", None) or []:
        if str(getattr(celula, "componente_bdi", "")) != "custo_direto":
            continue
        if str(getattr(celula, "categoria", "")) == "material":
            continue
        item_id = str(getattr(celula, "atividade_id", "") or "")
        if not item_id:
            continue
        base_by_item[item_id] += float(getattr(celula, "valor_rs", 0.0) or 0.0)
    return base_by_item


def _build_pool_scaling_by_item(canonical: Any, cubo: Any) -> dict[str, float]:
    """Escala custos diretos por item para aderir ao custo particionado de pool.

    A escala é aplicada apenas para categorias pool-driven (mao_obra/equipamento/diesel),
    preservando material sem ajuste forçado por partição.
    """
    particao = _build_pool_particao_by_item(canonical)
    if not particao:
        return {}
    base_by_item = _accumulate_direto_base_by_item(cubo)
    scaling: dict[str, float] = {}
    for item_id, alvo in particao.items():
        base = float(base_by_item.get(item_id, 0.0))
        if base > 0.0 and alvo > 0.0:
            scaling[item_id] = alvo / base
    return scaling


def _iter_scaled_cubo_cells(canonical: Any, cubo: Any):
    """Itera células diretas do cubo aplicando escala de pool particionado por atividade.

    Filtra exclusivamente natureza='direto' — células indiretas (IND-*) têm seu
    próprio canal de leitura via _iter_indireto_cubo_cells.
    """
    scaling = _build_pool_scaling_by_item(canonical, cubo)
    for celula in getattr(cubo, "celulas", None) or []:
        if str(getattr(celula, "natureza", "direto") or "direto") != "direto":
            continue
        valor = float(getattr(celula, "valor_rs", 0.0) or 0.0)
        item_id = str(getattr(celula, "atividade_id", "") or "")
        categoria = str(getattr(celula, "categoria", "") or "")
        if categoria != "material":
            valor *= float(scaling.get(item_id, 1.0))
        yield celula, valor


def _iter_indireto_cubo_cells(cubo: Any):
    """Itera células indiretas (natureza='indireto') do cubo enriquecido."""
    for celula in getattr(cubo, "celulas", None) or []:
        if str(getattr(celula, "natureza", "") or "") == "indireto":
            yield celula, float(getattr(celula, "valor_rs", 0.0) or 0.0)


