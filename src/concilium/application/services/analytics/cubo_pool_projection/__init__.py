"""Projeções (faces) do Cubo de Pool Instancial — ADR-086 Fases 3-4.

Espelha o contrato de projeção do ADR-069 (CuboAnalitico):
``{face, granularidade, unit_type, chart_hint, columns[], rows[], operator_meta, totais, narrativa[]}``.

Separação rígida (ADR-086 H4):
  - Faces **físicas** (do CuboPoolInstancial): o que cada slot fez — nunca imputam idle/mob a atividade.
    - Faces **causais/estruturais** (de CustoParticionadoItem / CadeiaPerpetuacao): a quem imputamos,
        sempre com baseline homogênea explícita ao lado.

Cada face inclui ``narrativa``: frases descritivas geradas dos próprios dados, com caveats explícitos.
"""

from ._dispatch import (
    _slice_cubo_por_filtros,
    _truncar_rows_projection,
    cubo_pool_projection_contract,
    resolve_cubo_pool_projection,
)
from ._faces_causais import (
    _CausaCustoRow,
    _face_cadeia_perpetuacao,
    _face_causa_custo,
    _face_economia_pool,
    _iter_particoes,
    _narrativa_economia_pool,
    _row_economia_pool,
    _rows_economia_pool,
)
from ._faces_fisicas import (
    _face_atividade_instancia,
    _face_ciclo_vida,
    _face_custo_estado_componente,
    _face_utilizacao_temporal,
)
from ._shared import (
    _COMP_LABEL,
    _ESTADO_LABEL,
    _FACES,
    _GRANULARIDADES,
    _GRANULARIDADES_VALIDAS,
    _autonomo_total_por_item,
    _baseline_from_equipes_diretas,
    _baseline_from_planejamento,
    _baseline_homogenea_por_item,
    _count_mob_demob_por_periodo,
    _fmt,
    _planejamento_sem_bdi_total,
)

__all__ = [
    "_COMP_LABEL",
    "_CausaCustoRow",
    "_ESTADO_LABEL",
    "_FACES",
    "_GRANULARIDADES",
    "_GRANULARIDADES_VALIDAS",
    "_autonomo_total_por_item",
    "_baseline_from_equipes_diretas",
    "_baseline_from_planejamento",
    "_baseline_homogenea_por_item",
    "_count_mob_demob_por_periodo",
    "_face_atividade_instancia",
    "_face_cadeia_perpetuacao",
    "_face_causa_custo",
    "_face_ciclo_vida",
    "_face_custo_estado_componente",
    "_face_economia_pool",
    "_face_utilizacao_temporal",
    "_fmt",
    "_iter_particoes",
    "_narrativa_economia_pool",
    "_planejamento_sem_bdi_total",
    "_row_economia_pool",
    "_rows_economia_pool",
    "_slice_cubo_por_filtros",
    "_truncar_rows_projection",
    "cubo_pool_projection_contract",
    "resolve_cubo_pool_projection",
]
