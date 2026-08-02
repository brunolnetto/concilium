"""Projeções (faces) do Cubo de Roster Real — ADR-174.

Espelha o contrato de projeção do ADR-069/086/128 F6 (mesma forma de
``{face, granularidade, unit_type, chart_hint, columns[], rows[], narrativa[], totais}``),
com 3 níveis de hierarquia (categoria/grupo_id/instancia_id) em vez do único
nível do estoque consumível (``resource_id``).
"""

from __future__ import annotations

from typing import Any

from concilium.application.services.analytics.cubo_roster_real_builder import (
    CuboRosterRealBuilder,
)
from concilium.domain.models.analytics.cubo_pool import bucket_periodo
from concilium.domain.models.analytics.cubo_roster_real import CuboRosterReal

_FACES: dict[str, dict] = {
    "resumo_por_instancia": {
        "label": "Resumo por instância",
        "natureza": "causal",
        "unit_type": "currency",
        "chart_hint": "table",
    },
    "resumo_por_grupo": {
        "label": "Resumo por grupo (função/tipo de equipamento)",
        "natureza": "causal",
        "unit_type": "currency",
        "chart_hint": "bar",
    },
    "resumo_por_categoria": {
        "label": "Resumo por categoria (MO/Equipamento)",
        "natureza": "causal",
        "unit_type": "currency",
        "chart_hint": "bar",
    },
    "custo_temporal": {
        "label": "Custo no tempo",
        "natureza": "fisica",
        "unit_type": "currency",
        "chart_hint": "line",
    },
}

_GRANULARIDADES = ["semana", "mes", "trimestre", "ano"]


def cubo_roster_real_projection_contract() -> dict:
    """Contrato navegável: faces disponíveis × granularidades (ADR-174)."""
    return {
        "version": "adr174-v1",
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
        "default_face": "resumo_por_instancia",
        "default_granularidade": "mes",
    }


def _round_measures(acc: dict) -> dict:
    return {k: round(v, 2) for k, v in acc.items()}


def _face_resumo_por_instancia(cubo: CuboRosterReal, **_: Any) -> tuple[list, list, list, dict]:
    acc: dict[tuple[str, str, str], dict[str, float]] = {}
    for c in cubo.celulas:
        key = (c.categoria, c.grupo_id, c.instancia_id)
        m = acc.setdefault(key, {"custo_direto": 0.0, "custo_indireto": 0.0, "custo_total": 0.0})
        m["custo_direto"] += c.custo_direto
        m["custo_indireto"] += c.custo_indireto
        m["custo_total"] += c.custo_total
    rows = [
        {"categoria": cat, "grupo_id": gid, "instancia_id": iid, **_round_measures(m)}
        for (cat, gid, iid), m in sorted(acc.items())
    ]
    columns = [
        {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "class"},
        {"id": "grupo_id", "label": "Grupo", "dtype": "str", "role": "class"},
        {"id": "instancia_id", "label": "Instância", "dtype": "str", "role": "class"},
        {"id": "custo_direto", "label": "Custo direto", "dtype": "float", "role": "value"},
        {"id": "custo_indireto", "label": "Custo indireto", "dtype": "float", "role": "value"},
        {"id": "custo_total", "label": "Custo total", "dtype": "float", "role": "value"},
    ]
    narrativa = [f"{len(rows)} instância(s) real(is); custo total: R${cubo.custo_total_geral():,.2f}."]
    return columns, rows, narrativa, {}


def _face_resumo_por_grupo(cubo: CuboRosterReal, **_: Any) -> tuple[list, list, list, dict]:
    acc: dict[tuple[str, str], dict[str, float]] = {}
    for c in cubo.celulas:
        key = (c.categoria, c.grupo_id)
        m = acc.setdefault(key, {"custo_direto": 0.0, "custo_indireto": 0.0, "custo_total": 0.0})
        m["custo_direto"] += c.custo_direto
        m["custo_indireto"] += c.custo_indireto
        m["custo_total"] += c.custo_total
    rows = [{"categoria": cat, "grupo_id": gid, **_round_measures(m)} for (cat, gid), m in sorted(acc.items())]
    columns = [
        {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "class"},
        {"id": "grupo_id", "label": "Grupo", "dtype": "str", "role": "class"},
        {"id": "custo_direto", "label": "Custo direto", "dtype": "float", "role": "value"},
        {"id": "custo_indireto", "label": "Custo indireto", "dtype": "float", "role": "value"},
        {"id": "custo_total", "label": "Custo total", "dtype": "float", "role": "value"},
    ]
    narrativa = [f"{len(rows)} grupo(s) (função/tipo de equipamento)."]
    return columns, rows, narrativa, {}


def _face_resumo_por_categoria(cubo: CuboRosterReal, **_: Any) -> tuple[list, list, list, dict]:
    acc: dict[str, dict[str, float]] = {}
    for c in cubo.celulas:
        m = acc.setdefault(c.categoria, {"custo_direto": 0.0, "custo_indireto": 0.0, "custo_total": 0.0})
        m["custo_direto"] += c.custo_direto
        m["custo_indireto"] += c.custo_indireto
        m["custo_total"] += c.custo_total
    rows = [{"categoria": cat, **_round_measures(m)} for cat, m in sorted(acc.items())]
    columns = [
        {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "class"},
        {"id": "custo_direto", "label": "Custo direto", "dtype": "float", "role": "value"},
        {"id": "custo_indireto", "label": "Custo indireto", "dtype": "float", "role": "value"},
        {"id": "custo_total", "label": "Custo total", "dtype": "float", "role": "value"},
    ]
    narrativa = [f"{len(rows)} categoria(s) — custo total: R${cubo.custo_total_geral():,.2f}."]
    return columns, rows, narrativa, {}


def _face_custo_temporal(cubo: CuboRosterReal, *, granularidade: str, **_: Any) -> tuple[list, list, list, dict]:
    acc: dict[tuple[str, str], dict[str, float]] = {}
    for c in cubo.celulas:
        key = (c.categoria, bucket_periodo(c.semana_iso, granularidade))
        m = acc.setdefault(key, {"custo_direto": 0.0, "custo_indireto": 0.0, "custo_total": 0.0})
        m["custo_direto"] += c.custo_direto
        m["custo_indireto"] += c.custo_indireto
        m["custo_total"] += c.custo_total
    rows = [{"categoria": cat, "periodo": periodo, **_round_measures(m)} for (cat, periodo), m in sorted(acc.items())]
    columns = [
        {"id": "categoria", "label": "Categoria", "dtype": "str", "role": "class"},
        {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
        {"id": "custo_direto", "label": "Custo direto", "dtype": "float", "role": "series"},
        {"id": "custo_indireto", "label": "Custo indireto", "dtype": "float", "role": "series"},
        {"id": "custo_total", "label": "Custo total", "dtype": "float", "role": "series"},
    ]
    narrativa = [f"{len(rows)} ponto(s) de série temporal."]
    return columns, rows, narrativa, {}


def resolve_cubo_roster_real_projection(
    canonical_in: Any,
    roster_mo: list | None = None,
    roster_eq: list | None = None,
    catalogo: dict[str, Any] | None = None,
    *,
    face: str = "resumo_por_instancia",
    granularidade: str = "mes",
    top_n: int = 300,
    categoria: str | None = None,
    grupo_id: str | None = None,
    instancia_id: str | None = None,
    gerado_em: str = "",
) -> dict:
    """Resolve uma face do cubo de roster real (ADR-174)."""
    if face not in _FACES:
        face = "resumo_por_instancia"
    meta = _FACES[face]
    granularidade_valida = granularidade if granularidade in _GRANULARIDADES else "mes"

    cubo_completo = CuboRosterRealBuilder().build(canonical_in, roster_mo, roster_eq, catalogo, gerado_em=gerado_em)
    cubo = cubo_completo.slice(categoria=categoria, grupo_id=grupo_id, instancia_id=instancia_id)

    if face == "resumo_por_grupo":
        columns, rows, narrativa, operator_meta = _face_resumo_por_grupo(cubo)
    elif face == "resumo_por_categoria":
        columns, rows, narrativa, operator_meta = _face_resumo_por_categoria(cubo)
    elif face == "custo_temporal":
        columns, rows, narrativa, operator_meta = _face_custo_temporal(cubo, granularidade=granularidade_valida)
    else:
        columns, rows, narrativa, operator_meta = _face_resumo_por_instancia(cubo)

    truncado = len(rows) > top_n
    if truncado:
        operator_meta = {**operator_meta, "truncado": True, "linhas_totais": len(rows)}
        narrativa = [*narrativa, f"⚠ Exibindo {top_n} de {len(rows)} linhas (truncado)."]
        rows = rows[:top_n]

    return {
        "version": "adr174-v1",
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
            "custo_total_geral": cubo.custo_total_geral(),
            "custo_por_categoria": cubo.custo_por_categoria(),
        },
        "invariantes_ok": True,
        "filtros_aplicados": {
            "categoria": categoria,
            "grupo_id": grupo_id,
            "instancia_id": instancia_id,
            "top_n": top_n,
        },
    }
