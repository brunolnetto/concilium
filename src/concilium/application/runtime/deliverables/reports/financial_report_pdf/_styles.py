"""Relatório financeiro PDF (parte extraída de financial_report_pdf.py, grupo _styles)."""

from __future__ import annotations


def _import_reportlab_widgets() -> dict:
    """Importa e agrupa as classes ReportLab usadas no relatório financeiro."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    return {
        "colors": colors,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "mm": mm,
        "Image": Image,
        "KeepTogether": KeepTogether,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def _build_report_styles(rl: dict) -> dict:
    """Constrói os ParagraphStyles base (título, h2, corpo, legenda, dinheiro)."""
    colors = rl["colors"]
    ParagraphStyle = rl["ParagraphStyle"]
    mm = rl["mm"]
    base = rl["getSampleStyleSheet"]()

    st_title = ParagraphStyle(
        "title",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#102a43"),
        spaceAfter=4 * mm,
    )
    st_h2 = ParagraphStyle(
        "h2",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#243b53"),
        spaceBefore=3 * mm,
        spaceAfter=2 * mm,
    )
    st_body = ParagraphStyle(
        "body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1f2933"),
        spaceAfter=1.5 * mm,
    )
    st_caption = ParagraphStyle(
        "caption",
        parent=base["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#627d98"),
        spaceAfter=1 * mm,
    )
    st_money = ParagraphStyle(
        "money",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor("#1f2933"),
    )
    return {
        "base": base,
        "title": st_title,
        "h2": st_h2,
        "body": st_body,
        "caption": st_caption,
        "money": st_money,
    }


def _split_relatorio_sections(relatorio: dict) -> tuple[dict, dict, dict, list, list, list, dict]:
    """Extrai as subseções do dicionário de relatório financeiro."""
    meta = relatorio.get("meta", {}) if isinstance(relatorio, dict) else {}
    resumo = relatorio.get("resumo", {}) if isinstance(relatorio, dict) else {}
    resultado = relatorio.get("RESULTADO", {}) if isinstance(relatorio, dict) else {}
    planejamento = relatorio.get("PLANEJAMENTO", []) if isinstance(relatorio, dict) else []
    instancias_recurso = relatorio.get("instancias_recurso", []) if isinstance(relatorio, dict) else []
    ponto_equilibrio = relatorio.get("ponto_equilibrio", []) if isinstance(relatorio, dict) else []
    actionable_insights = relatorio.get("ACTIONABLE_INSIGHTS", {}) if isinstance(relatorio, dict) else {}
    return meta, resumo, resultado, planejamento, instancias_recurso, ponto_equilibrio, actionable_insights


