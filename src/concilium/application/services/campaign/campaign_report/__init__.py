"""ADR-070 — Campaign report generation.

Three public functions:
- serialize_campaign_report(bundle, cube) -> dict
- render_campaign_report_md(report) -> str
- render_campaign_report_pdf(report, md_text) -> bytes | None
"""

from ._helpers import _fmt_f2, _fmt_f3, _fmt_int, _fmt_pct, _safe, _vetor_EF_dict, _vetor_O_dict
from ._insights import (
    _derive_insights,
    _insight_best_lever,
    _insight_composicao_custo,
    _insight_fallback_viabilidade,
    _insight_paralelismo,
    _insight_paralelismo_from_cenarios,
    _insight_paralelismo_from_resumos,
    _marginal_range,
    _shares_de,
)
from ._markdown import (
    _md_cenarios_lines,
    _md_cubo_lines,
    _md_faces_lines,
    _md_header_lines,
    _md_insights_lines,
    _md_marginal_effects_lines,
    _md_shortlist_lines,
    _pareto_mark,
    render_campaign_report_md,
)
from ._pdf import render_campaign_report_pdf
from ._serialize import serialize_campaign_report

__all__ = [
    "_derive_insights",
    "_fmt_f2",
    "_fmt_f3",
    "_fmt_int",
    "_fmt_pct",
    "_insight_best_lever",
    "_insight_composicao_custo",
    "_insight_fallback_viabilidade",
    "_insight_paralelismo",
    "_insight_paralelismo_from_cenarios",
    "_insight_paralelismo_from_resumos",
    "_marginal_range",
    "_md_cenarios_lines",
    "_md_cubo_lines",
    "_md_faces_lines",
    "_md_header_lines",
    "_md_insights_lines",
    "_md_marginal_effects_lines",
    "_md_shortlist_lines",
    "_pareto_mark",
    "_safe",
    "_shares_de",
    "_vetor_EF_dict",
    "_vetor_O_dict",
    "render_campaign_report_md",
    "render_campaign_report_pdf",
    "serialize_campaign_report",
]
