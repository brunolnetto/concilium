"""Projeções (faces) do Cubo de Pool Instancial — ADR-086 Fases 3-4.

Contrato de projeção, filtros/slicing e resolve_cubo_pool_projection.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.services.analytics.cubo_pool_builder import (
    CuboPoolInstancialBuilder,
    validar_invariantes_cubo_pool,
)

from ._faces_causais import _face_cadeia_perpetuacao, _face_causa_custo, _face_economia_pool
from ._faces_fisicas import (
    _face_atividade_instancia,
    _face_ciclo_vida,
    _face_custo_estado_componente,
    _face_utilizacao_temporal,
)
from ._shared import _FACES, _GRANULARIDADES, _GRANULARIDADES_VALIDAS, _baseline_homogenea_por_item


def cubo_pool_projection_contract() -> dict:
    """Contrato navegável: faces disponíveis × granularidades × naturezas (ADR-086 D6.1)."""
    return {
        "version": "adr086-v1",
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
        "naturezas": ["fisica", "causal", "estrutural"],
        "default_face": "instancia_ciclo_vida",
        "default_granularidade": "mes",
    }


def _slice_cubo_por_filtros(cubo, face: str, atividade_id: str | None, instancia_id: str | None):
    """Aplica filtros opcionais de atividade/instância via slice do cubo."""
    if not (atividade_id or instancia_id):
        return cubo
    tipo = inst_num = None
    if instancia_id and "-" in instancia_id:
        tipo, _, num = instancia_id.rpartition("-")
        inst_num = int(num) if num.isdigit() else None
    return cubo.slice(
        atividade_id=atividade_id if face in ("atividade_instancia",) else None,
        tipo_id=tipo,
        instancia_numero=inst_num,
    )


def _truncar_rows_projection(
    rows: list,
    narrativa: list,
    operator_meta: dict,
    top_n: int,
) -> tuple[list, list, dict]:
    truncado = len(rows) > top_n
    if truncado:
        operator_meta = {**operator_meta, "truncado": True, "linhas_totais": len(rows)}
        narrativa = [*narrativa, f"⚠ Exibindo {top_n} de {len(rows)} linhas (truncado)."]
        rows = rows[:top_n]
    return rows, narrativa, operator_meta


def resolve_cubo_pool_projection(
    canonical_in: Any,
    *,
    face: str = "instancia_ciclo_vida",
    granularidade: str = "mes",
    top_n: int = 300,
    atividade_id: str | None = None,
    instancia_id: str | None = None,
    gerado_em: str = "",
) -> dict:
    """Resolve uma face do cubo de pool. Retorna o contrato de projeção (ADR-086 D4/D5)."""
    if face not in _FACES:
        face = "instancia_ciclo_vida"
    meta = _FACES[face]
    granularidade_valida = _GRANULARIDADES_VALIDAS.get(granularidade, "mes")

    cubo = CuboPoolInstancialBuilder().build(canonical_in, gerado_em=gerado_em)
    contratos = list(getattr(canonical_in, "contratos_recurso", None) or [])
    cadeias = list(getattr(canonical_in, "cadeias_perpetuacao", None) or [])

    cubo = _slice_cubo_por_filtros(cubo, face, atividade_id, instancia_id)

    # Baseline homogênea por item: planejamento sem BDI quando disponível; fallback
    # operacional apenas para projetos/fixtures sem planejamento consolidado.
    baseline_por_item, baseline_source_by_item = _baseline_homogenea_por_item(canonical_in)

    dispatch = {
        "utilizacao_temporal": _face_utilizacao_temporal,
        "custo_estado_componente": _face_custo_estado_componente,
        "instancia_ciclo_vida": _face_ciclo_vida,
        "atividade_instancia": _face_atividade_instancia,
        "causa_custo": _face_causa_custo,
        "economia_pool": _face_economia_pool,
        "cadeia_perpetuacao": _face_cadeia_perpetuacao,
    }
    columns, rows, narrativa, operator_meta = dispatch[face](
        cubo,
        contratos,
        cadeias,
        granularidade=granularidade_valida,
        atividade_id=atividade_id,
        top_n=top_n,
        baseline_por_item=baseline_por_item,
        baseline_source_by_item=baseline_source_by_item,
    )

    rows, narrativa, operator_meta = _truncar_rows_projection(rows, narrativa, operator_meta, top_n)

    # Invariantes de honestidade (H1/H3)
    violacoes = validar_invariantes_cubo_pool(cubo, contratos)

    return {
        "version": "adr086-v1",
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
            "custo_total_pool": cubo.custo_total,
            "custo_por_estado": cubo.custo_por_estado(),
            "custo_por_componente": cubo.custo_por_componente(),
            "semanas_por_estado": cubo.semanas_por_estado(),
        },
        "invariantes_ok": not violacoes,
        "invariantes_violacoes": violacoes,
        "filtros_aplicados": {"atividade_id": atividade_id, "instancia_id": instancia_id, "top_n": top_n},
    }


