"""Projeções (faces) do Cubo de Estoque Consumível — ADR-128 F6.

Espelha o contrato de projeção do ADR-069/ADR-086 (mesma forma de
``{face, granularidade, unit_type, chart_hint, columns[], rows[], narrativa[], totais}``),
escalado para só 4 faces (consumíveis não têm dimensão instância/contrato/cadeia).
"""

from __future__ import annotations

from typing import Any

from concilium.application.services.analytics.cubo_estoque_consumivel_builder import (
    CuboEstoqueConsumivelBuilder,
)
from concilium.domain.models.analytics.cubo_estoque_consumivel import CuboEstoqueConsumivel
from concilium.domain.models.analytics.cubo_pool import bucket_periodo

_FACES: dict[str, dict] = {
    "resumo_por_recurso": {
        "label": "Resumo por recurso",
        "natureza": "causal",
        "unit_type": "count",
        "chart_hint": "table",
    },
    "estoque_temporal": {
        "label": "Estoque no tempo",
        "natureza": "fisica",
        "unit_type": "count",
        "chart_hint": "line",
    },
    "fluxo_componente": {
        "label": "Fluxo por componente",
        "natureza": "fisica",
        "unit_type": "count",
        "chart_hint": "bar_stacked",
    },
    "causa_atraso": {
        "label": "Causa do atraso",
        "natureza": "causal",
        "unit_type": "count",
        "chart_hint": "table",
    },
}

_GRANULARIDADES = ["semana", "mes", "trimestre", "ano"]


def cubo_estoque_consumivel_projection_contract() -> dict:
    """Contrato navegável: faces disponíveis × granularidades (ADR-128 F6)."""
    return {
        "version": "adr128-f6-v1",
        "faces": {
            name: {
                "label": m["label"],
                "natureza": m["natureza"],
                "unit_type": m["unit_type"],
                "chart_hint": m["chart_hint"],
            }
            for name, m in _FACES.items()
        },
        "granularidades": _GRANULARIDADES,
        "naturezas": ["fisica", "causal"],
        "default_face": "resumo_por_recurso",
        "default_granularidade": "mes",
    }


def _face_resumo_por_recurso(canonical_in: Any, **_: Any) -> tuple[list, list, list, dict]:
    resumos = list(getattr(canonical_in, "resumo_estoque_consumiveis", None) or [])
    rows = [
        {
            "resource_id": r.resource_id,
            "status_estoque": r.status_estoque,
            "estoque_inicial": r.estoque_inicial,
            "estoque_medio": r.estoque_medio,
            "estoque_minimo": r.estoque_minimo,
            "estoque_final": r.estoque_final,
            "overflow_total": r.overflow_total,
            "delay_total_semanas": r.delay_total_semanas,
            "n_atividades_atrasadas": r.n_atividades_atrasadas,
        }
        for r in resumos
    ]
    columns = [
        {"id": "resource_id", "label": "Recurso", "dtype": "str", "role": "class"},
        {"id": "status_estoque", "label": "Status", "dtype": "str", "role": "value"},
        {"id": "estoque_medio", "label": "Estoque médio", "dtype": "float", "role": "value"},
        {"id": "estoque_minimo", "label": "Estoque mínimo", "dtype": "float", "role": "value"},
        {"id": "overflow_total", "label": "Excedente descartado", "dtype": "float", "role": "value"},
        {"id": "delay_total_semanas", "label": "Semanas de atraso", "dtype": "int", "role": "value"},
    ]
    n_criticos = sum(1 for r in resumos if r.status_estoque == "CRITICO")
    n_avisos = sum(1 for r in resumos if r.status_estoque == "AVISO")
    narrativa = [f"{len(resumos)} recurso(s) consumível(is) restrito(s); {n_avisos} em AVISO, {n_criticos} em CRITICO."]
    return columns, rows, narrativa, {}


def _face_estoque_temporal(cubo: CuboEstoqueConsumivel, *, granularidade: str, resource_id: str | None, **_: Any):
    celulas = cubo.celulas if resource_id is None else cubo.slice(resource_id=resource_id).celulas
    buckets: dict[tuple[str, str], list[float]] = {}
    for c in celulas:
        key = (c.resource_id, bucket_periodo(c.semana_iso, granularidade))
        buckets.setdefault(key, []).append(c.estoque_nivel)
    rows = [
        {"resource_id": rid, "periodo": periodo, "estoque_nivel_medio": round(sum(vals) / len(vals), 2)}
        for (rid, periodo), vals in sorted(buckets.items())
    ]
    columns = [
        {"id": "resource_id", "label": "Recurso", "dtype": "str", "role": "class"},
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "estoque_nivel_medio", "label": "Estoque médio", "dtype": "float", "role": "series"},
    ]
    narrativa = [f"{len(rows)} ponto(s) de série, estado por semana: {cubo.semanas_por_estado()}."]
    return columns, rows, narrativa, {}


def _face_fluxo_componente(cubo: CuboEstoqueConsumivel, *, granularidade: str, resource_id: str | None, **_: Any):
    celulas = cubo.celulas if resource_id is None else cubo.slice(resource_id=resource_id).celulas
    buckets: dict[tuple[str, str], dict[str, float]] = {}
    for c in celulas:
        key = (c.resource_id, bucket_periodo(c.semana_iso, granularidade))
        acc = buckets.setdefault(key, {"consumo": 0.0, "producao": 0.0, "reabastecimento": 0.0, "overflow": 0.0})
        acc["consumo"] += c.consumo
        acc["producao"] += c.producao
        acc["reabastecimento"] += c.reabastecimento_externo
        acc["overflow"] += c.overflow
    rows = [
        {"resource_id": rid, "periodo": periodo, **{k: round(v, 2) for k, v in acc.items()}}
        for (rid, periodo), acc in sorted(buckets.items())
    ]
    columns = [
        {"id": "resource_id", "label": "Recurso", "dtype": "str", "role": "class"},
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "consumo", "label": "Consumo", "dtype": "float", "role": "series"},
        {"id": "producao", "label": "Produção interna", "dtype": "float", "role": "series"},
        {"id": "reabastecimento", "label": "Reabastecimento externo", "dtype": "float", "role": "series"},
        {"id": "overflow", "label": "Excedente descartado", "dtype": "float", "role": "series"},
    ]
    narrativa = [f"Consumo total: {cubo.consumo_total()}; produção interna total: {cubo.producao_total()}."]
    return columns, rows, narrativa, {}


def _face_causa_atraso(canonical_in: Any, *, resource_id: str | None, **_: Any):
    cronograma = getattr(canonical_in, "cronograma", None)
    delays = list(getattr(cronograma, "estoque_delays", None) or [])
    if resource_id is not None:
        delays = [d for d in delays if d.resource_id == resource_id]
    rows = [{"resource_id": d.resource_id, "activity_id": d.activity_id, "delay_weeks": d.delay_weeks} for d in delays]
    columns = [
        {"id": "resource_id", "label": "Recurso", "dtype": "str", "role": "class"},
        {"id": "activity_id", "label": "Atividade", "dtype": "str", "role": "class"},
        {"id": "delay_weeks", "label": "Semanas de atraso", "dtype": "int", "role": "value"},
    ]
    total_semanas = sum(d.delay_weeks for d in delays)
    narrativa = [f"{len(delays)} atividade(s) atrasada(s) por consumível, {total_semanas} semana(s) no total."]
    return columns, rows, narrativa, {}


def resolve_cubo_estoque_consumivel_projection(
    canonical_in: Any,
    *,
    face: str = "resumo_por_recurso",
    granularidade: str = "mes",
    top_n: int = 300,
    resource_id: str | None = None,
    gerado_em: str = "",
) -> dict:
    """Resolve uma face do cubo de estoque consumível (ADR-128 F6)."""
    if face not in _FACES:
        face = "resumo_por_recurso"
    meta = _FACES[face]
    granularidade_valida = granularidade if granularidade in _GRANULARIDADES else "mes"

    cubo = CuboEstoqueConsumivelBuilder().build(canonical_in, gerado_em=gerado_em)

    if face == "resumo_por_recurso":
        columns, rows, narrativa, operator_meta = _face_resumo_por_recurso(canonical_in)
    elif face == "estoque_temporal":
        columns, rows, narrativa, operator_meta = _face_estoque_temporal(
            cubo, granularidade=granularidade_valida, resource_id=resource_id
        )
    elif face == "fluxo_componente":
        columns, rows, narrativa, operator_meta = _face_fluxo_componente(
            cubo, granularidade=granularidade_valida, resource_id=resource_id
        )
    else:
        columns, rows, narrativa, operator_meta = _face_causa_atraso(canonical_in, resource_id=resource_id)

    truncado = len(rows) > top_n
    if truncado:
        operator_meta = {**operator_meta, "truncado": True, "linhas_totais": len(rows)}
        narrativa = [*narrativa, f"⚠ Exibindo {top_n} de {len(rows)} linhas (truncado)."]
        rows = rows[:top_n]

    return {
        "version": "adr128-f6-v1",
        "face": face,
        "natureza": meta["natureza"],
        "granularidade": granularidade_valida,
        "unit_type": meta["unit_type"],
        "chart_hint": meta["chart_hint"],
        "columns": columns,
        "rows": rows,
        "narrativa": narrativa,
        "operator_meta": operator_meta,
        "totais": {
            "overflow_total": cubo.overflow_total(),
            "consumo_total": cubo.consumo_total(),
            "producao_total": cubo.producao_total(),
            "semanas_por_estado": cubo.semanas_por_estado(),
        },
        "invariantes_ok": True,
        "filtros_aplicados": {"resource_id": resource_id, "top_n": top_n},
    }
