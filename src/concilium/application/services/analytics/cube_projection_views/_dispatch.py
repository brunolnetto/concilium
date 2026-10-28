"""Shared projection builders for analytical cube visualizations and API payloads.

Dispatch de faces e montagem do payload.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Literal

from ._bdi_pool import FACE_UNIT_TYPES
from ._categoria_atividade_componente import _resolve_atividade_componente_rows, _resolve_categoria_componente_rows
from ._diesel import _resolve_diesel_temporal_rows
from ._indireto_shared import bucket_from_week_iso
from ._tempo_natureza_componente import _resolve_tempo_componente_rows, _resolve_tempo_natureza_rows
from ._temporal_categoria import _resolve_direto_temporal_categoria_rows, _resolve_indireto_temporal_categoria_rows

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


def _require_integral_count(value: object, field: str) -> int:
    """Reject fractional headcount/equipment counts rather than silently truncating."""
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative integer count")
    if isinstance(value, int):
        count = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        count = int(value)
    else:
        raise ValueError(f"{field} must be a nonnegative integer count")
    if count < 0:
        raise ValueError(f"{field} must be a nonnegative integer count")
    return count


def resolve_cubo_projection_rows(
    cubo: Any,
    face: str,
    granularidade: FaceGranularity,
    top_n: int,
    canonical: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    if face == "direto_temporal_categoria":
        return _resolve_direto_temporal_categoria_rows(cubo, canonical, granularidade, top_n)

    if face == "indireto_temporal_categoria":
        return _resolve_indireto_temporal_categoria_rows(canonical, granularidade, top_n)

    if face == "tempo_natureza":
        return _resolve_tempo_natureza_rows(canonical, granularidade, top_n)

    if face == "tempo_componente":
        return _resolve_tempo_componente_rows(cubo, canonical, granularidade, top_n)

    if face == "categoria_componente":
        return _resolve_categoria_componente_rows(cubo, canonical, top_n)

    if face == "atividade_componente":
        return _resolve_atividade_componente_rows(cubo, canonical, top_n)

    if face == "diesel_temporal":
        return _resolve_diesel_temporal_rows(cubo, granularidade, top_n)

    raise ValueError(f"Face de projeção não suportada: {face}")


def resolve_abc_curva_rows(
    canonical: Any,
    top_n: int,
    threshold_a: float,
    threshold_b: float,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
    from concilium.domain.services.analytics.curva_abc_builder import CurvaABCBuilder

    curva = CurvaABCBuilder().build(canonical)
    rows: list[dict[str, Any]] = []
    for item in list(curva.itens)[:top_n]:
        classe = (
            "A"
            if item.pct_custo_acumulado <= threshold_a
            else ("B" if item.pct_custo_acumulado <= threshold_b else "C")
        )
        rows.append(
            {
                "insumo_id": item.insumo_id,
                "descricao": item.descricao,
                "categoria": item.categoria.lower(),
                "custo_total_rs": float(item.custo_total),
                "pct_custo": float(item.pct_custo),
                "pct_custo_acumulado": float(item.pct_custo_acumulado),
                "classe_abc": classe,
            }
        )
    columns = [
        {"id": "insumo_id", "label": "Insumo", "dtype": "str", "role": "x"},
        {"id": "descricao", "label": "Descrição", "dtype": "str", "role": "label"},
        {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "series"},
        {"id": "custo_total_rs", "label": "Custo Total (R$)", "dtype": "float", "role": "value"},
        {"id": "pct_custo", "label": "% Custo", "dtype": "float", "role": "value_aux"},
        {"id": "pct_custo_acumulado", "label": "% Acumulado", "dtype": "float", "role": "line"},
        {"id": "classe_abc", "label": "Classe ABC", "dtype": "str", "role": "class"},
    ]
    class_counts = {"A": 0, "B": 0, "C": 0}
    for row in rows:
        class_counts[str(row["classe_abc"])] += 1
    operator_meta = {
        "thresholds": {"a": threshold_a, "b": threshold_b},
        "class_counts": class_counts,
        "coverage_a": max((float(row["pct_custo_acumulado"]) for row in rows if row["classe_abc"] == "A"), default=0.0),
    }
    return rows, columns, "bar", FACE_UNIT_TYPES["abc_curva"], operator_meta


def resolve_s_curve_rows(
    canonical: Any,
    granularidade: FaceGranularity,
    top_n: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
    from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

    s_curve = SCurveBuilder().build(canonical)
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: {"custo_semanal_rs": 0.0, "custo_acumulado_rs": 0.0})
    for idx, semana_iso in enumerate(s_curve.semanas_iso):
        bucket = bucket_from_week_iso(semana_iso, granularidade)
        grouped[bucket]["custo_semanal_rs"] += float(s_curve.custo_semanal[idx])
        grouped[bucket]["custo_acumulado_rs"] += float(s_curve.custo_semanal[idx])
    rows: list[dict[str, Any]] = []
    acumulado = 0.0
    for bucket in sorted(grouped.keys()):
        custo = float(grouped[bucket]["custo_semanal_rs"])
        acumulado += custo
        rows.append(
            {
                "periodo": bucket,
                "custo_semanal_rs": custo,
                "custo_acumulado_rs": round(acumulado, 2),
                "pct_acumulado": round(acumulado / float(s_curve.total_projeto), 6)
                if s_curve.total_projeto > 0
                else 0.0,
            }
        )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "custo_semanal_rs", "label": "Custo no Período (R$)", "dtype": "float", "role": "value"},
        {"id": "custo_acumulado_rs", "label": "Custo Acumulado (R$)", "dtype": "float", "role": "line"},
        {"id": "pct_acumulado", "label": "% Acumulado", "dtype": "float", "role": "line_aux"},
    ]
    return (
        rows[:top_n],
        columns,
        "line",
        FACE_UNIT_TYPES["s_curve_custo"],
        {"total_projeto_rs": float(s_curve.total_projeto)},
    )


def resolve_recursos_ativos_rows(
    canonical: Any,
    granularidade: FaceGranularity,
    top_n: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str, str, dict[str, Any]]:
    from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

    s_curve = SCurveBuilder().build(canonical)
    grouped: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "n_equipes_totais": 0,
            "n_equipamentos_unicos": 0,
            "equipamentos_unidades_ativas": 0,
        }
    )
    for agg in s_curve.agregacao_semanal:
        bucket = bucket_from_week_iso(str(agg.semana_iso), granularidade)
        n_equipes = _require_integral_count(agg.n_equipes_totais, "n_equipes_totais")
        n_equipamentos_unicos = _require_integral_count(
            agg.n_equipamentos_unicos, "n_equipamentos_unicos"
        )
        unidades_ativas = sum(
            _require_integral_count(units, f"equipamentos_ativos[{equip_id!r}]")
            for equip_id, units in agg.equipamentos_ativos.items()
        )
        grouped[bucket]["n_equipes_totais"] += n_equipes
        grouped[bucket]["n_equipamentos_unicos"] = max(
            grouped[bucket]["n_equipamentos_unicos"], n_equipamentos_unicos
        )
        grouped[bucket]["equipamentos_unidades_ativas"] += unidades_ativas
    rows = [
        {
            "periodo": bucket,
            "n_equipes_totais": vals["n_equipes_totais"],
            "n_equipamentos_unicos": vals["n_equipamentos_unicos"],
            "equipamentos_unidades_ativas": vals["equipamentos_unidades_ativas"],
        }
        for bucket, vals in sorted(grouped.items())
    ]
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "n_equipes_totais", "label": "Nº Equipes", "dtype": "int", "role": "value"},
        {"id": "n_equipamentos_unicos", "label": "Equipamentos Únicos", "dtype": "int", "role": "value"},
        {
            "id": "equipamentos_unidades_ativas",
            "label": "Unidades de Equipamento Ativas",
            "dtype": "int",
            "role": "value",
        },
    ]
    operator_meta = {
        "aggregation_rule": "sum(n_equipes, unidades) + max(equipamentos_unicos) por bucket",
        "n_periodos": len(rows),
    }
    return rows[:top_n], columns, "line", FACE_UNIT_TYPES["recursos_ativos_tempo"], operator_meta


def build_cube_projection_payload(
    *,
    canonical: Any,
    cubo: Any,
    face: str,
    granularidade: FaceGranularity,
    top_n: int,
    abc_threshold_a: float = 0.80,
    abc_threshold_b: float = 0.95,
) -> dict[str, Any]:
    if face == "abc_curva":
        rows, columns, chart_hint, unit_type, operator_meta = resolve_abc_curva_rows(
            canonical, top_n, abc_threshold_a, abc_threshold_b
        )
    elif face == "s_curve_custo":
        rows, columns, chart_hint, unit_type, operator_meta = resolve_s_curve_rows(canonical, granularidade, top_n)
    elif face == "recursos_ativos_tempo":
        rows, columns, chart_hint, unit_type, operator_meta = resolve_recursos_ativos_rows(
            canonical, granularidade, top_n
        )
    else:
        rows, columns, chart_hint = resolve_cubo_projection_rows(cubo, face, granularidade, top_n, canonical=canonical)
        unit_type = FACE_UNIT_TYPES[face]
        operator_meta = {}
    return {
        "face": face,
        "granularidade": granularidade,
        "rows": rows,
        "columns": columns,
        "chart_hint": chart_hint,
        "unit_type": unit_type,
        "operator_meta": operator_meta,
    }


