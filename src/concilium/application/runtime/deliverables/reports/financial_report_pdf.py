"""Renderizador nativo ReportLab para relatório financeiro.

Gera PDF com conteúdo financeiro usando Platypus para layout robusto e tabulação
com wrapping de texto. Implementado conforme NEP-034 e ADR-084.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from io import BytesIO


def _brl(v: float) -> str:
    v = float(v)
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: float) -> str:
    x = float(v)
    if -1.0 <= x <= 1.0:
        x *= 100.0
    return f"{x:.2f}%"


def _safe_text(v: object) -> str:
    return html.escape(str(v or ""), quote=False)


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
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=16 * mm,
            rightMargin=16 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=title,
        )
        page_w, page_h = A4
        usable_w = page_w - 32 * mm

        base = getSampleStyleSheet()
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

        meta = relatorio.get("meta", {}) if isinstance(relatorio, dict) else {}
        resumo = relatorio.get("resumo", {}) if isinstance(relatorio, dict) else {}
        resultado = relatorio.get("RESULTADO", {}) if isinstance(relatorio, dict) else {}
        planejamento = relatorio.get("PLANEJAMENTO", []) if isinstance(relatorio, dict) else []

        story: list = []

        proj_nome = _safe_text(resumo.get("projeto", "") or title or "Relatório Financeiro")
        story.append(Paragraph(f"Relatório Financeiro — {proj_nome}", st_title))

        gerado_em = str(meta.get("gerado_em", ""))[:19].replace("T", " ")
        framework = _safe_text(meta.get("framework", "concilium"))
        story.append(
            Paragraph(
                f"Gerado em: {_safe_text(gerado_em)} | Framework: {framework}",
                st_body,
            )
        )

        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Resumo Executivo", st_h2))

        tipo = _safe_text(resumo.get("tipo_obra", "-") or "-")
        local = _safe_text(resumo.get("localizacao", "-") or "-")
        story.append(
            Paragraph(
                f"<b>Projeto:</b> {proj_nome}<br/><b>Tipo de Obra:</b> {tipo}<br/><b>Localização:</b> {local}",
                st_body,
            )
        )

        story.append(Spacer(1, 1 * mm))
        story.append(Paragraph("Resultado Financeiro", st_h2))

        preco_venda = float(resultado.get("preco_venda_total", 0.0) or 0.0)
        custo_direto = float(resultado.get("custo_direto", 0.0) or 0.0)
        custo_indireto = float(resultado.get("custo_indireto", 0.0) or 0.0)
        custo_total = float(resultado.get("custo_total", 0.0) or 0.0)
        resultado_bruto = float(resultado.get("resultado_bruto", 0.0) or 0.0)
        margem_pct = float(resultado.get("margem_pct", 0.0) or 0.0)

        st_money = ParagraphStyle(
            "money",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.HexColor("#1f2933"),
        )

        table_data = [
            [Paragraph("<b>Indicador</b>", st_body), Paragraph("<b>Valor</b>", st_money)],
            [Paragraph("Preço de venda (c/ BDI)", st_body), Paragraph(_brl(preco_venda), st_money)],
            [Paragraph("Custo direto", st_body), Paragraph(_brl(custo_direto), st_money)],
            [Paragraph("Custo indireto", st_body), Paragraph(_brl(custo_indireto), st_money)],
            [Paragraph("Custo total", st_body), Paragraph(_brl(custo_total), st_money)],
            [Paragraph("Resultado bruto", st_body), Paragraph(_brl(resultado_bruto), st_money)],
            [Paragraph("Margem", st_body), Paragraph(_pct(margem_pct), st_money)],
        ]

        tbl = Table(table_data, colWidths=[usable_w * 0.62, usable_w * 0.38])
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2ec")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102a43")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bcccdc")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(tbl)

        if isinstance(planejamento, list) and planejamento:
            story.append(Spacer(1, 1 * mm))
            story.append(Paragraph("Planejamento por EAP (top 20)", st_h2))

            st_small = ParagraphStyle(
                "small",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
            )

            st_small_right = ParagraphStyle(
                "small_right",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                alignment=2,
            )

            plan_data = [
                [
                    Paragraph("<b>Item</b>", st_small),
                    Paragraph("<b>Descrição</b>", st_small),
                    Paragraph("<b>c/BDI (R$)</b>", st_small_right),
                ]
            ]
            for item in planejamento[:20]:
                item_id = _safe_text(item.get("item_id", "-"))
                desc = _safe_text(str(item.get("descricao", ""))[:80])
                valor = _brl(float(item.get("subtotal_com_bdi", 0.0) or 0.0))
                plan_data.append(
                    [
                        Paragraph(item_id, st_small),
                        Paragraph(desc, st_small),
                        Paragraph(valor, st_small_right),
                    ]
                )

            plan_tbl = Table(plan_data, colWidths=[usable_w * 0.12, usable_w * 0.55, usable_w * 0.33])
            plan_tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2ec")),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bcccdc")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            story.append(plan_tbl)

        if image_provider:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph("Principais Gráficos", st_h2))

            preferred = [
                "scurve_custo.png",
                "bar_direto_atividade_temporal.png",
                "bar_direto_atividade_temporal.png",
                "pool_utilizacao_temporal.png",
                "pool_custo_estado.png",
                "pool_economia.png",
                "painel_equilibrio.png",
            ]
            # Altura máxima por imagem: ½ da página útil para evitar LayoutError
            # "Flowable too large on page N" quando a imagem excede o frame restante.
            max_img_h = (page_h - 32 * mm) * 0.5
            images_added = 0
            for name in preferred:
                if images_added >= 4:
                    break
                content = image_provider(name)
                if not content:
                    continue
                try:
                    img = Image(BytesIO(content), width=usable_w * 0.95)
                    # Limita altura mantendo aspect ratio
                    if img.imageHeight > max_img_h:
                        ratio = max_img_h / img.imageHeight
                        img = Image(BytesIO(content), width=usable_w * 0.95 * ratio, height=max_img_h)
                    img.hAlign = "CENTER"
                    story.append(Spacer(1, 2 * mm))
                    story.append(Paragraph(_safe_text(name.replace(".png", "")), st_h2))
                    story.append(img)
                    images_added += 1
                except Exception:
                    pass

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
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas

            fallback_buf = BytesIO()
            c = canvas.Canvas(fallback_buf, pagesize=A4)
            w, h = A4

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
            if resultado:
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

            c.setFont("Helvetica", 7)
            c.setFillGray(0.7)
            c.drawString(16 * mm, 12 * mm, "Relatório gerado em modo resiliente")

            c.showPage()
            c.save()
            return fallback_buf.getvalue()
        except Exception:
            return None
