"""Renderizador nativo ReportLab para relatório financeiro.

Gera PDF com conteúdo financeiro usando Platypus para layout robusto e tabulação
com wrapping de texto. Implementado conforme NEP-034 e ADR-084.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from io import BytesIO

# Mapa de slug de arquivo → título legível para humanos
_CHART_LABELS: dict[str, str] = {
    "scurve_custo": "Curva S de Custo Acumulado",
    "bar_direto_atividade_temporal": "Custo Direto por Atividade (Evolução Temporal)",
    "pool_utilizacao_temporal": "Utilização do Pool de Equipamentos",
    "pool_custo_estado": "Custo por Estado do Pool de Recursos",
    "pool_economia": "Economia de Pool vs. Execução Autônoma",
    "painel_equilibrio": "Painel de Ponto de Equilíbrio",
    "gantt_cronograma": "Cronograma de Execução (Gantt RCPSP)",
    "fluxo_financeiro": "Fluxo de Caixa do Projeto",
    "area_tempo_componente": "Evolução de Custos por Componente",
    "bar_atividade_componente": "Composição de Custos por Atividade",
    "bar_categoria_componente": "Composição de Custos por Categoria de Insumo",
    "bar_combustivel_tipo_temporal": "Consumo de Combustível por Tipo (Temporal)",
    "bar_diesel_temporal": "Consumo de Diesel ao Longo do Projeto",
    "bar_tempo_direto_categoria": "Custo Direto por Categoria (Evolução Temporal)",
    "bar_tempo_indireto_categoria": "Custos Indiretos por Categoria (Evolução Temporal)",
    "bar_tempo_natureza": "Distribuição de Custos por Natureza (Temporal)",
    "dependencia_eap": "Rede de Dependências da EAP",
    "hist_equipamentos": "Histograma de Utilização de Equipamentos",
    "hist_mao_obra": "Histograma de Utilização de Mão de Obra",
    "linha_recursos_tempo": "Utilização de Recursos ao Longo do Tempo",
}


def _chart_label(filename: str) -> str:
    """Converte nome de arquivo PNG em título legível."""
    slug = filename.replace(".png", "")
    if slug in _CHART_LABELS:
        return _CHART_LABELS[slug]
    # Fallback: capitalize e substitui underscores por espaços
    return slug.replace("_", " ").title()


def _fmt_localizacao(loc: str | None) -> str:
    """Converte 'lat=X, lng=Y' em formato legível; retorna original caso não seja coordenada."""
    if not loc:
        return "-"
    m = re.match(r"lat\s*=\s*([-\d.]+),?\s*lng\s*=\s*([-\d.]+)", str(loc))
    if not m:
        return loc
    lat, lng = float(m.group(1)), float(m.group(2))
    # Mapeamento simplificado de faixas de coordenadas para estados brasileiros
    # (cobre os principais biomas e faixas relevantes para obras de infraestrutura)
    estado = _br_estado_approx(lat, lng)
    lat_fmt = f"{abs(lat):.2f}°{'S' if lat < 0 else 'N'}"
    lng_fmt = f"{abs(lng):.2f}°{'O' if lng < 0 else 'L'}"
    if estado:
        return f"{estado}, Brasil ({lat_fmt}, {lng_fmt})"
    return f"Brasil ({lat_fmt}, {lng_fmt})"


def _br_estado_approx(lat: float, lng: float) -> str | None:
    """Aproximação grosseira de estado brasileiro por bounding box."""
    # Tabela compacta: (lat_min, lat_max, lng_min, lng_max, sigla, nome)
    _BOXES = [
        (-5.3, 2.8, -52.6, -44.0, "PA", "Pará"),
        (-18.4, -7.4, -48.0, -39.6, "TO/BA", "Tocantins / Bahia"),
        (-4.5, 0.0, -48.0, -43.0, "MA", "Maranhão"),
        (-7.5, -2.4, -41.5, -34.8, "CE", "Ceará"),
        (-9.0, -6.0, -38.0, -34.8, "BA/PE", "Bahia / Pernambuco"),
        (-10.0, -6.5, -41.5, -37.0, "BA", "Bahia"),
        (-23.0, -19.0, -53.0, -44.0, "SP/PR", "São Paulo / Paraná"),
        (-23.8, -19.8, -44.0, -40.3, "MG", "Minas Gerais"),
        (-33.8, -27.0, -57.0, -48.0, "RS", "Rio Grande do Sul"),
        (-15.0, -7.0, -61.0, -48.0, "MT/GO", "Mato Grosso / Goiás"),
    ]
    for lat_min, lat_max, lng_min, lng_max, _sigla, nome in _BOXES:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return nome
    return None


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

        tipo_obra_map = {
            "terraplenagem": "Terraplenagem",
            "pavimentacao": "Pavimentação Asfáltica",
            "pavimentação": "Pavimentação Asfáltica",
            "saneamento": "Saneamento Básico",
            "edificacao": "Edificação",
            "edificação": "Edificação",
            "infraestrutura": "Infraestrutura",
        }
        tipo_raw = resumo.get("tipo_obra", "") or ""
        tipo = _safe_text(tipo_obra_map.get(tipo_raw.lower(), tipo_raw or "-"))
        local = _safe_text(_fmt_localizacao(resumo.get("localizacao")))
        descricao = resumo.get("descricao") or resumo.get("objetivo") or ""
        info_lines = f"<b>Projeto:</b> {proj_nome}<br/><b>Tipo de Obra:</b> {tipo}<br/><b>Localização:</b> {local}"
        if descricao:
            info_lines += f"<br/><b>Descrição:</b> {_safe_text(str(descricao))}"
        story.append(Paragraph(info_lines, st_body))

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
                # item.get("descricao") pode retornar None explícito (JSON null)
                desc_raw = item.get("descricao") or item.get("cpu_id") or ""
                desc = _safe_text(str(desc_raw)[:80])
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
            # Limites de dimensão por imagem para evitar LayoutError e distorção.
            max_img_w = usable_w * 0.95
            max_img_h = (page_h - 32 * mm) * 0.5  # ½ página útil
            images_added = 0
            for name in preferred:
                if images_added >= 4:
                    break
                content = image_provider(name)
                if not content:
                    continue
                try:
                    probe = Image(BytesIO(content))
                    nat_w, nat_h = probe.imageWidth, probe.imageHeight
                    if nat_w <= 0 or nat_h <= 0:
                        continue
                    # Escala proporcional: cabe dentro de max_img_w × max_img_h sem distorcer
                    scale = min(max_img_w / nat_w, max_img_h / nat_h, 1.0)
                    disp_w, disp_h = nat_w * scale, nat_h * scale
                    img = Image(BytesIO(content), width=disp_w, height=disp_h)
                    img.hAlign = "CENTER"
                    story.append(Spacer(1, 2 * mm))
                    story.append(Paragraph(_safe_text(_chart_label(name)), st_h2))
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
