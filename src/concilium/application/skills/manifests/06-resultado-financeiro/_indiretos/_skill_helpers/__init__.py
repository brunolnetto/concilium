"""Skill 06 (_indiretos) — Indiretos (ADR-009, ADR-023 §D4).

Dimensiona custos indiretos com granularidade semanal.
ADR-023 §D4: também emite IndiretoComBdi com BDI-INDIRETO aplicado sobre cada categoria.

Categorias suportadas: ADM, TOP, LAB, QSMS, MOB.

Drivers:
  permanencia: custo_fixo_mensal ÷ 4.33 × n_semanas (TOP, ADM, LAB, QSMS)
  one_time:    custo_fixo_total alocado nas semanas 0 e final (MOB)

Inputs (no dict 'inputs'):
    composicoes_indireto: dict[categoria, dict] — opcional, override por categoria
    dados_mobilizacao:    dict — formato item a item (mobilizações/baixadas) para categoria
                          MOB, anterior ao schema categorias_config (ver _custo_mob_composicional)
    perc_encargos:        float — default 0.92
    categorias_config:    list[dict] — lista de IndirectoCategoria serializadas (ADR-009 novo)
    tabela_bdi:           TabelaBdi serializada — para bdi_indireto (ADR-023 §D4); opcional
"""

from ._breakdown import (  # ty: ignore[unresolved-import]
    _breakdown_mob,
    _breakdown_permanencia_default,
    _breakdown_permanencia_override,
    _build_semanal_breakdown,
)
from ._categoria import _as_categoria_indireto, _build_categoria_from_dict  # ty: ignore[unresolved-import]
from ._dimensionamento import (  # ty: ignore[unresolved-import]
    _bcfd_enrich_mo_itens,
    _composicao_default_por_categoria,
    _dimensionar_automatico,
    _meses_entre,
    _parse_component,
    _semanas_projeto,
)
from ._mob import (  # ty: ignore[unresolved-import]
    _accrue_desmobilizacao_fase,
    _accrue_mobilizacao_fase,
    _accrue_operacao_fase,
    _count_pessoas_diretas,
    _custo_mob_composicional,
    _distribuir_mob_fases,
    _extract_dv4_policy,
    _extract_overrides,
    _get_pipeline_blocked,
    _process_mob_categoria,
)
from ._resolucao import (  # ty: ignore[unresolved-import]
    _apply_bdi_to_indiretos,
    _apply_dv4_scale_to_categoria,
    _build_indireto_from_cat_obj,
    _resolve_categoria_comp,
    _sub_custos_indireto,
    _validate_dv4_policy,
    _validate_razao_indireto_direto,
)

__all__ = [
    "_bcfd_enrich_mo_itens",
    "_composicao_default_por_categoria",
    "_dimensionar_automatico",
    "_meses_entre",
    "_parse_component",
    "_semanas_projeto",
    "_accrue_desmobilizacao_fase",
    "_accrue_mobilizacao_fase",
    "_accrue_operacao_fase",
    "_apply_bdi_to_indiretos",
    "_apply_dv4_scale_to_categoria",
    "_as_categoria_indireto",
    "_breakdown_mob",
    "_breakdown_permanencia_default",
    "_breakdown_permanencia_override",
    "_build_categoria_from_dict",
    "_build_indireto_from_cat_obj",
    "_build_semanal_breakdown",
    "_count_pessoas_diretas",
    "_custo_mob_composicional",
    "_distribuir_mob_fases",
    "_extract_dv4_policy",
    "_extract_overrides",
    "_get_pipeline_blocked",
    "_process_mob_categoria",
    "_resolve_categoria_comp",
    "_sub_custos_indireto",
    "_validate_dv4_policy",
    "_validate_razao_indireto_direto",
]
