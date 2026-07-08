"""Relatório financeiro PDF (parte extraída de financial_report_pdf.py, grupo _fallback)."""

from __future__ import annotations

from io import BytesIO

from ._text_helpers import _brl, _pct, _safe_text


def _draw_fallback_resultado(c, resultado: dict, y: float, mm) -> None:
    """Desenha o bloco 'Resultado Financeiro' do PDF de fallback (canvas simples)."""
    if not resultado:
        return
    c.setFont("Helvetica-Bold", 11)
    c.drawString(16 * mm, y, "Resultado Financeiro")
    y -= 8 * mm

    c.setFont("Helvetica", 9)
    preco_venda = float(resultado.get("preco_venda_total", 0.0) or 0.0)
    custo_total = float(resultado.get("custo_total", 0.0) or 0.0)
    resultado_bruto = float(resultado.get("resultado_bruto", 0.0) or 0.0)
    margem_pct = float(resultado.get("margem_pct", 0.0) or 0.0)

    c.drawString(16 * mm, y, f"Preço de venda: {_brl(preco_venda)}")
    y -= 5 * mm
    c.drawString(16 * mm, y, f"Custo total: {_brl(custo_total)}")
    y -= 5 * mm
    c.drawString(16 * mm, y, f"Resultado: {_brl(resultado_bruto)}")
    y -= 5 * mm
    c.drawString(16 * mm, y, f"Margem: {_pct(margem_pct)}")


def _draw_fallback_content(c, relatorio: dict, title: str, w: float, h: float, mm) -> None:
    """Desenha o conteúdo completo do PDF de fallback (modo resiliente sem Platypus)."""
    c.setFont("Helvetica-Bold", 16)
    c.drawString(16 * mm, h - 20 * mm, _safe_text("Relatório Financeiro"))

    c.setFont("Helvetica", 9)
    y = h - 30 * mm

    resumo = relatorio.get("resumo", {}) if isinstance(relatorio, dict) else {}
    projeto = _safe_text(resumo.get("projeto", "") or title or "Sem título")
    c.drawString(16 * mm, y, f"Projeto: {projeto}")
    y -= 6 * mm

    tipo = _safe_text(resumo.get("tipo_obra", "-") or "-")
    c.drawString(16 * mm, y, f"Tipo: {tipo}")
    y -= 6 * mm

    local = _safe_text(resumo.get("localizacao", "-") or "-")
    c.drawString(16 * mm, y, f"Local: {local}")
    y -= 12 * mm

    resultado = relatorio.get("RESULTADO", {}) if isinstance(relatorio, dict) else {}
    _draw_fallback_resultado(c, resultado, y, mm)

    c.setFont("Helvetica", 7)
    c.setFillGray(0.7)
    c.drawString(16 * mm, 12 * mm, "Relatório gerado em modo resiliente")


def _render_fallback_pdf(relatorio: dict, title: str) -> bytes | None:
    """PDF de fallback minimalista via reportlab.pdfgen, usado quando o Platypus falha."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas

        fallback_buf = BytesIO()
        c = canvas.Canvas(fallback_buf, pagesize=A4)
        w, h = A4

        _draw_fallback_content(c, relatorio, title, w, h, mm)

        c.showPage()
        c.save()
        return fallback_buf.getvalue()
    except Exception:
        return None


