"""Relatório financeiro PDF (parte extraída de financial_report_pdf.py, grupo _flowables_tables)."""

from __future__ import annotations

from ._text_helpers import _brl, _fmt_cpu_descricao, _fmt_tipo_id, _safe_text


def _eap_row_values(item: dict) -> tuple[str, str, str]:
    """Calcula (item_id, descrição, valor formatado) de uma linha da tabela EAP."""
    item_id = _safe_text(item.get("item_id", "-"))
    # Issue 1: if descricao is None/empty, format cpu_id humanely
    desc_raw = item.get("descricao")
    if desc_raw is None or str(desc_raw).strip() == "":
        cpu_id = item.get("cpu_id") or ""
        desc_raw = _fmt_cpu_descricao(cpu_id) if cpu_id else "-"
    desc = _safe_text(str(desc_raw)[:80])
    valor = _brl(float(item.get("subtotal_com_bdi", 0.0) or 0.0))
    return item_id, desc, valor


def _build_eap_flowables(planejamento: list, styles: dict, rl: dict, usable_w: float) -> list:
    """Tabela 'Quantitativos e Composição de Custos (EAP)' — todos os itens (Issue 1+3)."""
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

    st_small = ParagraphStyle("small3", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    st_small_right = ParagraphStyle(
        "small_right3", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=10, alignment=2
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
        item_id, desc, valor = _eap_row_values(item)
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
    return [
        KeepTogether(
            [
                Paragraph("Quantitativos e Composição de Custos (EAP)", styles["h2"]),
                Spacer(1, 1 * mm),
                plan_tbl,
            ]
        )
    ]


def _mob_row_values(inst: dict) -> tuple[str, str, str, str, str, str, str]:
    """Calcula os valores formatados de uma linha da tabela de mobilização/desmobilização."""
    inst_id = _safe_text(inst.get("instancia_id", "-"))
    tipo = _safe_text(_fmt_tipo_id(inst.get("tipo_id", "-") or "-"))
    mob = _safe_text(inst.get("semana_mobilizacao", "-") or "-")
    demob = _safe_text(inst.get("semana_desmobilizacao", "-") or "-")
    sem_ativas = str(inst.get("semanas_ativas", "-") or "-")
    utilizacao = f"{float(inst.get('taxa_utilizacao_pct', 0.0) or 0.0):.0f}%"
    custo_mob = float(inst.get("custo_mob_instancia", 0.0) or 0.0)
    custo_demob = float(inst.get("custo_demob_instancia", 0.0) or 0.0)
    custo_md = _brl(custo_mob + custo_demob)
    return inst_id, tipo, mob, demob, sem_ativas, utilizacao, custo_md


def _build_mob_flowables(instancias_recurso: list, styles: dict, rl: dict, usable_w: float) -> list:
    """Tabela 'Ciclo de Vida dos Recursos (Mobilização e Desmobilização)' (Issue 5)."""
    if not (isinstance(instancias_recurso, list) and instancias_recurso):
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

    st_small = ParagraphStyle("small4", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9)
    st_small_right = ParagraphStyle(
        "small_right4", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9, alignment=2
    )
    st_small_center = ParagraphStyle(
        "small_center4", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9, alignment=1
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
        inst_id, tipo, mob, demob, sem_ativas, utilizacao, custo_md = _mob_row_values(inst)
        mob_data.append(
            [
                Paragraph(inst_id[:35], st_small),
                Paragraph(tipo[:30], st_small),
                Paragraph(mob, st_small_center),
                Paragraph(demob, st_small_center),
                Paragraph(sem_ativas, st_small_center),
                Paragraph(utilizacao, st_small_center),
                Paragraph(custo_md, st_small_right),
            ]
        )

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
    return [
        KeepTogether(
            [
                Paragraph("Ciclo de Vida dos Recursos (Mobilização e Desmobilização)", styles["h2"]),
                Spacer(1, 1 * mm),
                mob_tbl,
            ]
        )
    ]


