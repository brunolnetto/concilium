"""Renderizador nativo ReportLab para relatório financeiro."""

from ._fallback import (
    _draw_fallback_content,
    _draw_fallback_resultado,
    _render_fallback_pdf,
)
from ._flowables_charts import (
    _build_charts_flowables,
)
from ._flowables_summary import (
    _build_distribuicao_flowables,
    _build_header_flowables,
    _build_recomendacoes_flowables,
    _build_resultado_financeiro_flowables,
    _build_viabilidade_flowables,
    _collect_recomendacoes,
    _collect_recs_from_list,
    _collect_recs_from_section,
    _distribuicao_totais,
)
from ._flowables_tables import (
    _build_eap_flowables,
    _build_mob_flowables,
    _eap_row_values,
    _mob_row_values,
)
from ._render import (
    render_financial_report_pdf,
)
from ._styles import (
    _build_report_styles,
    _import_reportlab_widgets,
    _split_relatorio_sections,
)
from ._text_helpers import (
    _CHART_CAPTIONS,
    _CHART_LABELS,
    _br_estado_approx,
    _brl,
    _chart_caption,
    _chart_label,
    _fmt_cpu_descricao,
    _fmt_localizacao,
    _fmt_tipo_id,
    _pct,
    _safe_text,
)

__all__ = [
    "_CHART_CAPTIONS",
    "_CHART_LABELS",
    "_br_estado_approx",
    "_brl",
    "_build_charts_flowables",
    "_build_distribuicao_flowables",
    "_build_eap_flowables",
    "_build_header_flowables",
    "_build_mob_flowables",
    "_build_recomendacoes_flowables",
    "_build_report_styles",
    "_build_resultado_financeiro_flowables",
    "_build_viabilidade_flowables",
    "_chart_caption",
    "_chart_label",
    "_collect_recomendacoes",
    "_collect_recs_from_list",
    "_collect_recs_from_section",
    "_distribuicao_totais",
    "_draw_fallback_content",
    "_draw_fallback_resultado",
    "_eap_row_values",
    "_fmt_cpu_descricao",
    "_fmt_localizacao",
    "_fmt_tipo_id",
    "_import_reportlab_widgets",
    "_mob_row_values",
    "_pct",
    "_render_fallback_pdf",
    "_safe_text",
    "_split_relatorio_sections",
    "render_financial_report_pdf",
]
