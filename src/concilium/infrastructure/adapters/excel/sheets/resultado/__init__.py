"""Excel sheets — resultado."""

from ._bdi import (
    render_bdi,
)
from ._cashflow import (
    _xl_cashflow_metrics_block,
    _xl_cashflow_render_row,
    _xl_cashflow_row_styling,
    render_fluxo_caixa,
)
from ._cronograma import (
    _rcr_build_qty_by_item,
    _rcr_render_item_row,
    render_cronograma_res,
)
from ._diretos import (
    _xl_dr_com_vals,
    _xl_dr_sem_vals,
    _xl_dr_totals_row,
    _xl_dr_write_cell,
    _xl_dr_write_data_row,
    render_diretos_res,
)
from ._equilibrio import (
    render_equilibrio,
)
from ._indiretos import (
    _rir_build_lookups,
    _rir_render_cat_row,
    _rir_render_kpis,
    _rir_render_total_row,
    render_indiretos_res,
)
from ._referencia import (
    _build_referencia_bridge_rows,
    _build_referencia_clima_n4_nota,
    _build_referencia_items,
    _ref_sv,
    _render_referencia_bridge_rows,
    _render_referencia_items_rows,
    render_referencia,
)
from ._resultado_ml import (
    _compute_resultado_alavancas,
    _xl_resultado_cap_giro_rows,
    _xl_resultado_custo_composicao,
    _xl_resultado_indirect_cats,
    _xl_resultado_ref,
    render_resultado_ml,
)

__all__ = [
    "_build_referencia_bridge_rows",
    "_build_referencia_clima_n4_nota",
    "_build_referencia_items",
    "_compute_resultado_alavancas",
    "_rcr_build_qty_by_item",
    "_rcr_render_item_row",
    "_ref_sv",
    "_render_referencia_bridge_rows",
    "_render_referencia_items_rows",
    "_rir_build_lookups",
    "_rir_render_cat_row",
    "_rir_render_kpis",
    "_rir_render_total_row",
    "_xl_cashflow_metrics_block",
    "_xl_cashflow_render_row",
    "_xl_cashflow_row_styling",
    "_xl_dr_com_vals",
    "_xl_dr_sem_vals",
    "_xl_dr_totals_row",
    "_xl_dr_write_cell",
    "_xl_dr_write_data_row",
    "_xl_resultado_cap_giro_rows",
    "_xl_resultado_custo_composicao",
    "_xl_resultado_indirect_cats",
    "_xl_resultado_ref",
    "render_bdi",
    "render_cronograma_res",
    "render_diretos_res",
    "render_equilibrio",
    "render_fluxo_caixa",
    "render_indiretos_res",
    "render_referencia",
    "render_resultado_ml",
]
