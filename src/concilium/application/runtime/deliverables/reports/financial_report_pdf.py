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
}

# Issue 2: captions para cada gráfico
_CHART_CAPTIONS: dict[str, str] = {
    "scurve_custo": "Acúmulo de custos ao longo das semanas do projeto, comparado ao planejado.",
    "bar_direto_atividade_temporal": "Distribuição semanal do custo direto por atividade da EAP.",
    "pool_utilizacao_temporal": "Taxa de utilização de cada equipamento do pool ao longo do tempo.",
    "pool_custo_estado": "Custo de recursos agrupado por estado operacional (produtivo, standby, ocioso).",
    "pool_economia": "Comparativo de custo entre execução via pool e execução autônoma por atividade.",
    "painel_equilibrio": "Ponto de equilíbrio financeiro por atividade: receita atribuída vs. custo total.",
    "gantt_cronograma": "Cronograma RCPSP otimizado: barras indicam início, duração e folga de cada frente.",
    "fluxo_financeiro": "Entradas e saídas de caixa por período, evidenciando o saldo acumulado.",
    "area_tempo_componente": "Evolução semanal dos custos decompostos em MO, EQ, Diesel e Materiais.",
    "bar_atividade_componente": "Composição de custo (MO, EQ, Diesel, Mat) para cada atividade da EAP.",
    "bar_categoria_componente": "Participação de cada categoria de insumo no custo direto total.",
    "bar_combustivel_tipo_temporal": "Consumo semanal de combustível separado por tipo de equipamento.",
    "bar_diesel_temporal": "Volume e custo do diesel consumido semana a semana.",
    "bar_tempo_direto_categoria": "Evolução semanal do custo direto por categoria de insumo.",
    "bar_tempo_indireto_categoria": "Evolução semanal dos custos indiretos por categoria.",
    "bar_tempo_natureza": "Participação semanal de custos diretos vs. indiretos no custo total.",
    "dependencia_eap": "Grafo de precedências entre atividades da Estrutura Analítica de Projeto.",
    "hist_equipamentos": "Distribuição das horas de utilização por equipamento ao longo do projeto.",
    "hist_mao_obra": "Distribuição das horas trabalhadas por categoria de mão de obra.",
}


def _chart_label(filename: str) -> str:
    """Converte nome de arquivo PNG em título legível."""
    slug = filename.replace(".png", "")
    if slug in _CHART_LABELS:
        return _CHART_LABELS[slug]
    # Fallback: capitalize e substitui underscores por espaços
    return slug.replace("_", " ").title()


def _chart_caption(filename: str) -> str:
    """Retorna legenda/caption para o gráfico, ou string vazia."""
    slug = filename.replace(".png", "")
    return _CHART_CAPTIONS.get(slug, "")


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


def _fmt_cpu_descricao(cpu_id: str) -> str:
    """Formata um cpu_id quando a descrição está ausente.

    'CPU-TERRA-ATI-003' → 'ATI 003'
    'CPU-TERRA-ESCO-CARGA-1CAT-DMT2000' → 'ESCO CARGA 1CAT DMT2000'
    """
    s = cpu_id
    # Remove prefixo 'CPU-TERRA-' ou 'CPU-' genérico
    for prefix in ("CPU-TERRA-", "CPU-"):
        if s.upper().startswith(prefix):
            s = s[len(prefix):]
            break
    return s.replace("-", " ").title()


def _fmt_tipo_id(tipo_id: str) -> str:
    """Formata tipo_id de instância de recurso.

    Remove sufixo de hash hexadecimal como '-cdc3632643c1', substitui underscores.
    """
    # Sufixo hash: hífen seguido de 12+ chars hex
    s = re.sub(r"-[0-9a-f]{10,}$", "", tipo_id, flags=re.IGNORECASE)
    return s.replace("_", " ").replace("-", " ").title()


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
            KeepTogether,
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
        st_caption = ParagraphStyle(
            "caption",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#627d98"),
            spaceAfter=1 * mm,
        )

        meta = relatorio.get("meta", {}) if isinstance(relatorio, dict) else {}
        resumo = relatorio.get("resumo", {}) if isinstance(relatorio, dict) else {}
        resultado = relatorio.get("RESULTADO", {}) if isinstance(relatorio, dict) else {}
        planejamento = relatorio.get("PLANEJAMENTO", []) if isinstance(relatorio, dict) else []
        instancias_recurso = relatorio.get("instancias_recurso", []) if isinstance(relatorio, dict) else []
        ponto_equilibrio = relatorio.get("ponto_equilibrio", []) if isinstance(relatorio, dict) else []
        actionable_insights = relatorio.get("ACTIONABLE_INSIGHTS", {}) if isinstance(relatorio, dict) else {}

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

        # ── Resultado Financeiro ──────────────────────────────────────────────
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

        fin_table_data = [
            [Paragraph("<b>Indicador</b>", st_body), Paragraph("<b>Valor</b>", st_money)],
            [Paragraph("Preço de venda (c/ BDI)", st_body), Paragraph(_brl(preco_venda), st_money)],
            [Paragraph("Custo direto", st_body), Paragraph(_brl(custo_direto), st_money)],
            [Paragraph("Custo indireto", st_body), Paragraph(_brl(custo_indireto), st_money)],
            [Paragraph("Custo total", st_body), Paragraph(_brl(custo_total), st_money)],
            [Paragraph("Resultado bruto", st_body), Paragraph(_brl(resultado_bruto), st_money)],
            [Paragraph("Margem", st_body), Paragraph(_pct(margem_pct), st_money)],
        ]

        fin_tbl = Table(fin_table_data, colWidths=[usable_w * 0.62, usable_w * 0.38])
        fin_tbl.setStyle(
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
        # Issue 4: KeepTogether para não separar título da tabela
        story.append(KeepTogether([Paragraph("Resultado Financeiro", st_h2), Spacer(1, 1 * mm), fin_tbl]))

        # ── Issue 6a: Análise de Viabilidade ─────────────────────────────────
        if isinstance(ponto_equilibrio, list) and ponto_equilibrio:
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

            viab_data = [
                [
                    Paragraph("<b>Item EAP</b>", st_small),
                    Paragraph("<b>Frentes Nec.</b>", st_small_right),
                    Paragraph("<b>Status</b>", st_small),
                    Paragraph("<b>PU Calibrado</b>", st_small_right),
                ]
            ]
            for pe in ponto_equilibrio:
                item_id = _safe_text(pe.get("item_id", "-"))
                frentes = f"{float(pe.get('frentes_necessarias', 0.0) or 0.0):.3f}"
                status = _safe_text(pe.get("status_validacao", "-") or "-")
                pu_cal = _brl(float(pe.get("pu_cat", 0.0) or 0.0))
                viab_data.append([
                    Paragraph(item_id, st_small),
                    Paragraph(frentes, st_small_right),
                    Paragraph(status, st_small),
                    Paragraph(pu_cal, st_small_right),
                ])

            viab_tbl = Table(
                viab_data,
                colWidths=[usable_w * 0.25, usable_w * 0.18, usable_w * 0.22, usable_w * 0.35],
            )
            viab_tbl.setStyle(
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
            story.append(KeepTogether([Paragraph("Análise de Viabilidade", st_h2), Spacer(1, 1 * mm), viab_tbl]))

        # ── Issue 6b: Distribuição de Custos por Tipo de Serviço ─────────────
        if isinstance(planejamento, list) and planejamento:
            total_mo = sum(float(it.get("subtotal_sem_bdi_mo", 0.0) or 0.0) for it in planejamento)
            total_eq = sum(float(it.get("subtotal_sem_bdi_eq", 0.0) or 0.0) for it in planejamento)
            total_diesel = sum(float(it.get("subtotal_sem_bdi_diesel", 0.0) or 0.0) for it in planejamento)
            total_mat = sum(float(it.get("subtotal_sem_bdi_mat", 0.0) or 0.0) for it in planejamento)
            total_all = total_mo + total_eq + total_diesel + total_mat or 1.0

            st_small = ParagraphStyle(
                "small2",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
            )
            st_small_right = ParagraphStyle(
                "small_right2",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                alignment=2,
            )

            dist_data = [
                [
                    Paragraph("<b>Categoria</b>", st_small),
                    Paragraph("<b>Subtotal (R$)</b>", st_small_right),
                    Paragraph("<b>Participação (%)</b>", st_small_right),
                ]
            ]
            for label, value in [
                ("Mão de Obra (MO)", total_mo),
                ("Equipamentos (EQ)", total_eq),
                ("Combustível (DIESEL)", total_diesel),
                ("Materiais (MAT)", total_mat),
            ]:
                dist_data.append([
                    Paragraph(label, st_small),
                    Paragraph(_brl(value), st_small_right),
                    Paragraph(f"{100.0 * value / total_all:.1f}%", st_small_right),
                ])

            dist_tbl = Table(
                dist_data,
                colWidths=[usable_w * 0.45, usable_w * 0.30, usable_w * 0.25],
            )
            dist_tbl.setStyle(
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
            story.append(KeepTogether([
                Paragraph("Distribuição de Custos por Tipo de Serviço", st_h2),
                Spacer(1, 1 * mm),
                dist_tbl,
            ]))

        # ── Issue 6c: Recomendações Técnicas ─────────────────────────────────
        if isinstance(actionable_insights, dict):
            recs: list[str] = []
            for section_key in ("criticidade", "sensibilidade", "intervencao"):
                sec = actionable_insights.get(section_key, {})
                if not isinstance(sec, dict):
                    continue
                # Try common keys for recommendation text
                for field in ("notas_engenheiro", "recomendacao_primaria", "passos_repair"):
                    val = sec.get(field)
                    if isinstance(val, str) and val.strip():
                        recs.append(val.strip())
                    elif isinstance(val, list):
                        for v in val:
                            if isinstance(v, str) and v.strip():
                                recs.append(v.strip())
                            elif isinstance(v, dict):
                                txt = v.get("descricao") or v.get("texto") or v.get("titulo") or ""
                                if txt:
                                    recs.append(str(txt).strip())

            if recs:
                rec_paragraphs: list = [Paragraph("Recomendações Técnicas", st_h2)]
                for i, rec in enumerate(recs[:5]):
                    rec_paragraphs.append(Paragraph(f"{i + 1}. {_safe_text(rec)}", st_body))
                story.append(KeepTogether(rec_paragraphs))

        # ── Issue 1+3: EAP table — all items, descriptions from cpu_id ───────
        if isinstance(planejamento, list) and planejamento:
            st_small = ParagraphStyle(
                "small3",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
            )
            st_small_right = ParagraphStyle(
                "small_right3",
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
            # Issue 3: remove [:20] limit; show all items
            for item in planejamento:
                item_id = _safe_text(item.get("item_id", "-"))
                # Issue 1: if descricao is None/empty, format cpu_id humanely
                desc_raw = item.get("descricao")
                if desc_raw is None or str(desc_raw).strip() == "":
                    cpu_id = item.get("cpu_id") or ""
                    desc_raw = _fmt_cpu_descricao(cpu_id) if cpu_id else "-"
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
            # Issue 3: updated section title + Issue 4: KeepTogether
            story.append(KeepTogether([
                Paragraph("Quantitativos e Composição de Custos (EAP)", st_h2),
                Spacer(1, 1 * mm),
                plan_tbl,
            ]))

        # ── Issue 5: MOB/DESMOB table ─────────────────────────────────────────
        if isinstance(instancias_recurso, list) and instancias_recurso:
            st_small = ParagraphStyle(
                "small4",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=7,
                leading=9,
            )
            st_small_right = ParagraphStyle(
                "small_right4",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=7,
                leading=9,
                alignment=2,
            )
            st_small_center = ParagraphStyle(
                "small_center4",
                parent=base["Normal"],
                fontName="Helvetica",
                fontSize=7,
                leading=9,
                alignment=1,
            )

            mob_data = [
                [
                    Paragraph("<b>Frente / Recurso</b>", st_small),
                    Paragraph("<b>Tipo</b>", st_small),
                    Paragraph("<b>Mob.</b>", st_small_center),
                    Paragraph("<b>Desmob.</b>", st_small_center),
                    Paragraph("<b>Sem. Ativas</b>", st_small_center),
                    Paragraph("<b>Utiliz.</b>", st_small_center),
                    Paragraph("<b>Custo Mob+Desmob</b>", st_small_right),
                ]
            ]
            for inst in instancias_recurso:
                inst_id = _safe_text(inst.get("instancia_id", "-"))
                tipo = _safe_text(_fmt_tipo_id(inst.get("tipo_id", "-") or "-"))
                mob = _safe_text(inst.get("semana_mobilizacao", "-") or "-")
                demob = _safe_text(inst.get("semana_desmobilizacao", "-") or "-")
                sem_ativas = str(inst.get("semanas_ativas", "-") or "-")
                utilizacao = f"{float(inst.get('taxa_utilizacao_pct', 0.0) or 0.0):.0f}%"
                custo_mob = float(inst.get("custo_mob_instancia", 0.0) or 0.0)
                custo_demob = float(inst.get("custo_demob_instancia", 0.0) or 0.0)
                custo_md = _brl(custo_mob + custo_demob)
                mob_data.append([
                    Paragraph(inst_id[:35], st_small),
                    Paragraph(tipo[:30], st_small),
                    Paragraph(mob, st_small_center),
                    Paragraph(demob, st_small_center),
                    Paragraph(sem_ativas, st_small_center),
                    Paragraph(utilizacao, st_small_center),
                    Paragraph(custo_md, st_small_right),
                ])

            mob_tbl = Table(
                mob_data,
                colWidths=[
                    usable_w * 0.22,
                    usable_w * 0.18,
                    usable_w * 0.10,
                    usable_w * 0.10,
                    usable_w * 0.10,
                    usable_w * 0.08,
                    usable_w * 0.22,
                ],
            )
            mob_tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e2ec")),
                        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bcccdc")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            story.append(KeepTogether([
                Paragraph("Ciclo de Vida dos Recursos (Mobilização e Desmobilização)", st_h2),
                Spacer(1, 1 * mm),
                mob_tbl,
            ]))

        # ── Issue 2+4: Charts with captions wrapped in KeepTogether ──────────
        if image_provider:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph("Principais Gráficos", st_h2))

            # Issue 5: removed 'linha_recursos_tempo.png' (confusing MOB/DESMOB chart)
            preferred = [
                "scurve_custo.png",
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
                    # Issue 2: caption paragraph
                    caption_text = _chart_caption(name)
                    chart_block = [
                        Spacer(1, 2 * mm),
                        Paragraph(_safe_text(_chart_label(name)), st_h2),
                    ]
                    if caption_text:
                        chart_block.append(Paragraph(_safe_text(caption_text), st_caption))
                    chart_block.append(img)
                    # Issue 4: KeepTogether so title doesn't orphan from image
                    story.append(KeepTogether(chart_block))
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
