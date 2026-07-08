"""Relatório financeiro PDF (parte extraída de financial_report_pdf.py, grupo _render)."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

from ._fallback import _render_fallback_pdf
from ._flowables_charts import _build_charts_flowables
from ._flowables_summary import (
    _build_distribuicao_flowables,
    _build_header_flowables,
    _build_recomendacoes_flowables,
    _build_resultado_financeiro_flowables,
    _build_viabilidade_flowables,
)
from ._flowables_tables import _build_eap_flowables, _build_mob_flowables
from ._styles import _build_report_styles, _import_reportlab_widgets, _split_relatorio_sections
from ._text_helpers import _safe_text


def render_financial_report_pdf(
    relatorio: dict,
    title: str,
    image_provider: Callable[[str], bytes | None] | None = None,
) -> bytes | None:
    """Renderiza dicionário de relatório financeiro para PDF ReportLab/Platypus.

    Tabelas e imagens com wrapping de texto, cabeçalho/rodapé, estilos profissionais.
    Retorna None se ReportLab não estiver disponível.
    """
    try:
        rl = _import_reportlab_widgets()
        mm = rl["mm"]

        buf = BytesIO()
        doc = rl["SimpleDocTemplate"](
            buf,
            pagesize=rl["A4"],
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=title,
        )
        page_w, page_h = rl["A4"]
        usable_w = page_w - 32 * mm

        styles = _build_report_styles(rl)

        meta, resumo, resultado, planejamento, instancias_recurso, ponto_equilibrio, actionable_insights = (
            _split_relatorio_sections(relatorio)
        )

        story: list = []
        story.extend(_build_header_flowables(resumo, meta, title, styles, rl))
        story.extend(_build_resultado_financeiro_flowables(resultado, styles, rl, usable_w))
        story.extend(_build_viabilidade_flowables(ponto_equilibrio, styles, rl, usable_w))
        story.extend(_build_distribuicao_flowables(planejamento, styles, rl, usable_w))
        story.extend(_build_recomendacoes_flowables(actionable_insights, styles, rl))
        story.extend(_build_eap_flowables(planejamento, styles, rl, usable_w))
        story.extend(_build_mob_flowables(instancias_recurso, styles, rl, usable_w))
        story.extend(_build_charts_flowables(image_provider, styles, rl, usable_w, page_h))

        colors = rl["colors"]

        def _on_page(canvas, _doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#486581"))
            canvas.drawString(16 * mm, page_h - 12 * mm, _safe_text(title))
            canvas.setFont("Helvetica", 7)
            canvas.drawRightString(page_w - 16 * mm, 10 * mm, f"Página {_doc.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
        return buf.getvalue()
    except Exception:
        return _render_fallback_pdf(relatorio, title)


