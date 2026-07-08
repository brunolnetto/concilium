"""Relatório financeiro PDF (parte extraída de financial_report_pdf.py, grupo _flowables_summary)."""

from __future__ import annotations

from ._text_helpers import _brl, _fmt_localizacao, _pct, _safe_text


def _build_header_flowables(resumo: dict, meta: dict, title: str, styles: dict, rl: dict) -> list:
    """Título do relatório + linha de metadados + bloco 'Resumo Executivo'."""
    Paragraph = rl["Paragraph"]
    Spacer = rl["Spacer"]
    mm = rl["mm"]

    proj_nome = _safe_text(resumo.get("projeto", "") or title or "Relatório Financeiro")
    flowables = [Paragraph(f"Relatório Financeiro — {proj_nome}", styles["title"])]

    gerado_em = str(meta.get("gerado_em", ""))[:19].replace("T", " ")
    framework = _safe_text(meta.get("framework", "concilium"))
    flowables.append(
        Paragraph(
            f"Gerado em: {_safe_text(gerado_em)} | Framework: {framework}",
            styles["body"],
        )
    )

    flowables.append(Spacer(1, 2 * mm))
    flowables.append(Paragraph("Resumo Executivo", styles["h2"]))

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
    flowables.append(Paragraph(info_lines, styles["body"]))
    flowables.append(Spacer(1, 1 * mm))
    return flowables


def _build_resultado_financeiro_flowables(resultado: dict, styles: dict, rl: dict, usable_w: float) -> list:
    """Tabela 'Resultado Financeiro' (preço de venda, custos, margem)."""
    Paragraph = rl["Paragraph"]
    Table = rl["Table"]
    TableStyle = rl["TableStyle"]
    KeepTogether = rl["KeepTogether"]
    Spacer = rl["Spacer"]
    colors = rl["colors"]
    mm = rl["mm"]
    st_body = styles["body"]
    st_money = styles["money"]

    preco_venda = float(resultado.get("preco_venda_total", 0.0) or 0.0)
    custo_direto = float(resultado.get("custo_direto", 0.0) or 0.0)
    custo_indireto = float(resultado.get("custo_indireto", 0.0) or 0.0)
    custo_total = float(resultado.get("custo_total", 0.0) or 0.0)
    resultado_bruto = float(resultado.get("resultado_bruto", 0.0) or 0.0)
    margem_pct = float(resultado.get("margem_pct", 0.0) or 0.0)

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
    return [KeepTogether([Paragraph("Resultado Financeiro", styles["h2"]), Spacer(1, 1 * mm), fin_tbl])]


def _build_viabilidade_flowables(ponto_equilibrio: list, styles: dict, rl: dict, usable_w: float) -> list:
    """Tabela 'Análise de Viabilidade' (Issue 6a)."""
    if not (isinstance(ponto_equilibrio, list) and ponto_equilibrio):
        return []

    Paragraph = rl["Paragraph"]
    Table = rl["Table"]
    TableStyle = rl["TableStyle"]
    KeepTogether = rl["KeepTogether"]
    Spacer = rl["Spacer"]
    colors = rl["colors"]
    ParagraphStyle = rl["ParagraphStyle"]
    mm = rl["mm"]
    base = styles["base"]

    st_small = ParagraphStyle("small", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    st_small_right = ParagraphStyle(
        "small_right", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10, alignment=2
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
        viab_data.append(
            [
                Paragraph(item_id, st_small),
                Paragraph(frentes, st_small_right),
                Paragraph(status, st_small),
                Paragraph(pu_cal, st_small_right),
            ]
        )

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
    return [KeepTogether([Paragraph("Análise de Viabilidade", styles["h2"]), Spacer(1, 1 * mm), viab_tbl])]


def _distribuicao_totais(planejamento: list) -> tuple[float, float, float, float, float]:
    """Soma os subtotais sem BDI por categoria (MO/EQ/Diesel/Mat) e o total geral."""
    total_mo = sum(float(it.get("subtotal_sem_bdi_mo", 0.0) or 0.0) for it in planejamento)
    total_eq = sum(float(it.get("subtotal_sem_bdi_eq", 0.0) or 0.0) for it in planejamento)
    total_diesel = sum(float(it.get("subtotal_sem_bdi_diesel", 0.0) or 0.0) for it in planejamento)
    total_mat = sum(float(it.get("subtotal_sem_bdi_mat", 0.0) or 0.0) for it in planejamento)
    total_all = total_mo + total_eq + total_diesel + total_mat or 1.0
    return total_mo, total_eq, total_diesel, total_mat, total_all


def _build_distribuicao_flowables(planejamento: list, styles: dict, rl: dict, usable_w: float) -> list:
    """Tabela 'Distribuição de Custos por Tipo de Serviço' (Issue 6b)."""
    if not (isinstance(planejamento, list) and planejamento):
        return []

    Paragraph = rl["Paragraph"]
    Table = rl["Table"]
    TableStyle = rl["TableStyle"]
    KeepTogether = rl["KeepTogether"]
    Spacer = rl["Spacer"]
    colors = rl["colors"]
    ParagraphStyle = rl["ParagraphStyle"]
    mm = rl["mm"]
    base = styles["base"]

    total_mo, total_eq, total_diesel, total_mat, total_all = _distribuicao_totais(planejamento)

    st_small = ParagraphStyle("small2", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    st_small_right = ParagraphStyle(
        "small_right2", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10, alignment=2
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
        dist_data.append(
            [
                Paragraph(label, st_small),
                Paragraph(_brl(value), st_small_right),
                Paragraph(f"{100.0 * value / total_all:.1f}%", st_small_right),
            ]
        )

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
    return [
        KeepTogether(
            [
                Paragraph("Distribuição de Custos por Tipo de Serviço", styles["h2"]),
                Spacer(1, 1 * mm),
                dist_tbl,
            ]
        )
    ]


def _collect_recs_from_list(val: list) -> list[str]:
    """Coleta textos de recomendação de uma lista (str ou dict com descrição/texto/título)."""
    found: list[str] = []
    for v in val:
        if isinstance(v, str) and v.strip():
            found.append(v.strip())
        elif isinstance(v, dict):
            txt = v.get("descricao") or v.get("texto") or v.get("titulo") or ""
            if txt:
                found.append(str(txt).strip())
    return found


def _collect_recs_from_section(sec: dict) -> list[str]:
    """Coleta recomendações de uma seção de ACTIONABLE_INSIGHTS (criticidade/sensibilidade/intervencao)."""
    if not isinstance(sec, dict):
        return []
    found: list[str] = []
    # Try common keys for recommendation text
    for field in ("notas_engenheiro", "recomendacao_primaria", "passos_repair"):
        val = sec.get(field)
        if isinstance(val, str) and val.strip():
            found.append(val.strip())
        elif isinstance(val, list):
            found.extend(_collect_recs_from_list(val))
    return found


def _collect_recomendacoes(actionable_insights: dict) -> list[str]:
    """Reúne as recomendações textuais de todas as seções de ACTIONABLE_INSIGHTS."""
    if not isinstance(actionable_insights, dict):
        return []
    recs: list[str] = []
    for section_key in ("criticidade", "sensibilidade", "intervencao"):
        sec = actionable_insights.get(section_key, {})
        recs.extend(_collect_recs_from_section(sec))
    return recs


def _build_recomendacoes_flowables(actionable_insights: dict, styles: dict, rl: dict) -> list:
    """Bloco 'Recomendações Técnicas' (Issue 6c), no máximo 5 itens."""
    recs = _collect_recomendacoes(actionable_insights)
    if not recs:
        return []

    Paragraph = rl["Paragraph"]
    KeepTogether = rl["KeepTogether"]
    rec_paragraphs: list = [Paragraph("Recomendações Técnicas", styles["h2"])]
    for i, rec in enumerate(recs[:5]):
        rec_paragraphs.append(Paragraph(f"{i + 1}. {_safe_text(rec)}", styles["body"]))
    return [KeepTogether(rec_paragraphs)]


