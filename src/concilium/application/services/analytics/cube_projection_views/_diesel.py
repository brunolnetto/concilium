"""Shared projection builders for analytical cube visualizations and API payloads.

Linhas de diesel temporal.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from ._indireto_shared import bucket_from_week_iso

FaceGranularity = Literal["semana", "mes", "bimestre", "trimestre", "semestre", "ano"]


def _resolve_diesel_temporal_rows(
    cubo: Any, granularidade: FaceGranularity, top_n: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    # Agregar por mês, empilhado pelas top atividades consumidoras de diesel
    per_atividade_por_bucket: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for celula in getattr(cubo, "celulas", None) or []:
        diesel_l = float(getattr(celula, "consumo_diesel_L", 0.0) or 0.0)
        if diesel_l > 0:
            bucket = bucket_from_week_iso(str(celula.semana_iso), granularidade)
            per_atividade_por_bucket[bucket][str(celula.atividade_id)] += diesel_l
    totais_por_atividade: dict[str, float] = defaultdict(float)
    for at_dict in per_atividade_por_bucket.values():
        for aid, v in at_dict.items():
            totais_por_atividade[aid] += v
    top_atividades = sorted(totais_por_atividade, key=lambda a: -totais_por_atividade[a])[:4]
    rows = []
    for bucket in sorted(per_atividade_por_bucket):
        for aid in top_atividades:
            rows.append(
                {
                    "periodo": bucket,
                    "atividade_id": aid,
                    "consumo_diesel_l": per_atividade_por_bucket[bucket].get(aid, 0.0),
                }
            )
    columns = [
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "atividade_id", "label": "Atividade", "dtype": "str", "role": "series"},
        {"id": "consumo_diesel_l", "label": "Consumo Diesel (L)", "dtype": "float", "role": "value"},
    ]
    return rows[:top_n], columns, "bar_stacked"


