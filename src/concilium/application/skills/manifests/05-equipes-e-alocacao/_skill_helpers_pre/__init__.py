"""ADR-078: Pré-processamento Estrutural de Compartilhamento de Recursos.

Funções puras e pipeline de construção do RelatorioOportunidades.

Expõe:
  _gap_max_economico          — gap_r^max a partir de custos mob/demob/idle
  _eta_perpetuacao            — índice de eficiência η ∈ [0, 1]
  _sobreposicao_bundle        — ov_vector + Ω para um par de equipes
  _delta_c_pot                — ΔC potencial para um par (i, j, r)
  _build_pre_processamento_compartilhamento  — pipeline completo

Referência: docs/product/4-research/recursos.md
            docs/engineering/0-architecture/adrs/ADR-078-*.md
"""

from ._cpm import _cpm_early_start, _cpm_late_finish, _gap_coberto_por_recurso  # ty: ignore[unresolved-import]
from ._deteccao_paralelo import (  # ty: ignore[unresolved-import]
    _detectar_oportunidades_paralelo,
    _dop_avaliar_par,
    _dop_contexto_tipo,
    _dop_delay_viola_float,
    _dop_oportunidades_para_tipo,
    _dop_ordem_temporal,
)
from ._metrics import (  # ty: ignore[unresolved-import]
    _GAP_MAX_INFINITO,
    _UNIDADE_SEM_IDLE,
    _delta_c_pot,
    _eta_perpetuacao,
    _gap_max_economico,
    _sobreposicao_bundle,
    _week_to_idx,
)
from ._pipeline import (  # ty: ignore[unresolved-import]
    _bppc_append_validacoes,
    _bppc_atualizar_contratos,
    _bppc_build_activity_resources,
    _bppc_build_gap_max_lookup,
    _bppc_oportunidades_por_tipo,
    _bppc_par_oportunidade,
    _build_pre_processamento_compartilhamento,
)

__all__ = [
    "_GAP_MAX_INFINITO",
    "_UNIDADE_SEM_IDLE",
    "_bppc_append_validacoes",
    "_bppc_atualizar_contratos",
    "_bppc_build_activity_resources",
    "_bppc_build_gap_max_lookup",
    "_bppc_oportunidades_por_tipo",
    "_bppc_par_oportunidade",
    "_build_pre_processamento_compartilhamento",
    "_cpm_early_start",
    "_cpm_late_finish",
    "_delta_c_pot",
    "_detectar_oportunidades_paralelo",
    "_dop_avaliar_par",
    "_dop_contexto_tipo",
    "_dop_delay_viola_float",
    "_dop_oportunidades_para_tipo",
    "_dop_ordem_temporal",
    "_eta_perpetuacao",
    "_gap_coberto_por_recurso",
    "_gap_max_economico",
    "_sobreposicao_bundle",
    "_week_to_idx",
]
