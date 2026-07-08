"""ADR-070 — Campaign report generation — render_campaign_report_pdf."""

from __future__ import annotations

from io import BytesIO

from ._helpers import _fmt_f2, _fmt_f3, _fmt_int, _fmt_pct, _safe
from ._insights import _derive_insights
from ._markdown import _pareto_mark


def render_campaign_report_pdf(report: dict, md_text: str) -> bytes | None:
    """Generates PDF using ReportLab Platypus. Returns None if unavailable."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buf = BytesIO()

        page_w, page_h = A4
        margin = 16 * mm
        usable_w = page_w - 2 * margin

        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin + 6 * mm,
            bottomMargin=margin + 4 * mm,
            title=f"Concilium — Campanha GO {report.get('meta', {}).get('campaign_id', '')}",
        )

        base = getSampleStyleSheet()
        st_title = ParagraphStyle(
            "camp_title",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#102a43"),
            spaceAfter=4 * mm,
        )
        st_h2 = ParagraphStyle(
            "camp_h2",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#243b53"),
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        )
        st_h3 = ParagraphStyle(
            "camp_h3",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334e68"),
            spaceBefore=2 * mm,
            spaceAfter=1 * mm,
        )
        st_body = ParagraphStyle(
            "camp_body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1f2933"),
            spaceAfter=1.5 * mm,
        )
        st_small = ParagraphStyle(
            "camp_small",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#1f2933"),
        )
        st_small_r = ParagraphStyle(
            "camp_small_r",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#1f2933"),
            alignment=2,
        )
        st_small_c = ParagraphStyle(
            "camp_small_c",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#1f2933"),
            alignment=1,
        )
        st_bullet = ParagraphStyle(
            "camp_bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1f2933"),
            leftIndent=8,
            spaceAfter=1.5 * mm,
        )

        # Colors
        C_GREEN = colors.HexColor("#16a34a")
        C_AMBER = colors.HexColor("#d97706")
        C_RED = colors.HexColor("#dc2626")
        C_HEADER_BG = colors.HexColor("#d9e2ec")
        C_ROW_ALT = colors.HexColor("#f5f7fa")
        C_GRID = colors.HexColor("#bcccdc")
        C_PARETO_BG = colors.HexColor("#dcfce7")

        def _status_color(status: str):
            if status in ("SUCESSO",):
                return C_GREEN
            if status in ("FRONTEIRA_UNICA", "SUCESSO_PARCIAL", "INCONCLUSO"):
                return C_AMBER
            return C_RED

        def _tbl_style_base() -> list:
            return [
                ("BACKGROUND", (0, 0), (-1, 0), C_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102a43")),
                ("GRID", (0, 0), (-1, -1), 0.4, C_GRID),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_ROW_ALT]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
            ]

        def _on_page(canvas, _doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#486581"))
            canvas.drawString(
                margin,
                page_h - margin + 2 * mm,
                "Concilium — Relatório de Campanha GO",
            )
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(colors.HexColor("#627d98"))
            canvas.drawRightString(
                page_w - margin,
                margin - 6 * mm,
                f"Página {_doc.page}",
            )
            canvas.restoreState()

        def _cl_o_color(cl_O: str) -> str:
            if cl_O == "IDEAL":
                return C_GREEN.hexval()
            if cl_O == "CRITICO":
                return C_RED.hexval()
            return "#1f2933"

        def _build_page1_header(meta: dict, n_shortlist: int) -> list:
            campaign_id = meta.get("campaign_id", "-")
            status = meta.get("status", "-")
            gerado_em = str(meta.get("gerado_em", "-"))[:19].replace("T", " ")
            n_av = meta.get("n_avaliados", 0)
            n_vi = meta.get("n_viaveis", 0)
            n_fa = meta.get("n_falhas", 0)
            cob = meta.get("cobertura_pct", 0.0)
            sc = _status_color(status)
            return [
                Paragraph(f"Relatório de Campanha GO — {_safe(campaign_id)}", st_title),
                Paragraph(
                    f"<b>Status:</b> <font color='{sc.hexval()}'>{_safe(status)}</font>"
                    f" &nbsp;|&nbsp; <b>Gerado em:</b> {_safe(gerado_em)}",
                    st_body,
                ),
                Paragraph(
                    f"<b>Cenários:</b> {n_av} avaliados &nbsp;·&nbsp; "
                    f"{n_vi} viáveis &nbsp;·&nbsp; {n_fa} falhas &nbsp;·&nbsp; "
                    f"cobertura {cob:.1f}%",
                    st_body,
                ),
                Spacer(1, 2 * mm),
                Paragraph(f"Shortlist — Top {n_shortlist} Candidatos", st_h2),
            ]

        def _build_shortlist_table(shortlist: list) -> Table:
            sl_headers = ["Rank", "ID", "Motivo", "Prazo", "fe_nec", "Margem", "MO%", "EQ%", "Utiliz.%"]
            sl_data = [[Paragraph(f"<b>{h}</b>", st_small_c) for h in sl_headers]]
            for item in shortlist:
                vO = item.get("vetor_O", {})
                vEF = item.get("vetor_EF", {})
                sl_data.append(
                    [
                        Paragraph(str(item.get("rank", "-")), st_small_c),
                        Paragraph(_safe(item.get("cenario_id", "-")), st_small),
                        Paragraph(_safe(str(item.get("motivo_inclusao", "-")))[:30], st_small),
                        Paragraph(_fmt_int(vO.get("prazo_semanas")), st_small_c),
                        Paragraph(_fmt_f3(vO.get("fe_nec_medio")), st_small_c),
                        Paragraph(_fmt_pct(vEF.get("margem_pct")), st_small_r),
                        Paragraph(_fmt_pct(vEF.get("share_mo_pct")), st_small_r),
                        Paragraph(_fmt_pct(vEF.get("share_eq_pct")), st_small_r),
                        Paragraph(_fmt_pct(vO.get("utilizacao_recursos_pct")), st_small_r),
                    ]
                )
            col_w_sl = [usable_w * x for x in [0.06, 0.14, 0.22, 0.07, 0.09, 0.10, 0.10, 0.10, 0.12]]
            sl_tbl = Table(sl_data, colWidths=col_w_sl, repeatRows=1)
            sl_tbl.setStyle(TableStyle(_tbl_style_base()))
            return sl_tbl

        def _build_scenario_row(c: dict) -> list:
            vO = c.get("vetor_O", {})
            vEF = c.get("vetor_EF", {})
            params = "; ".join(f"{k}={v}" for k, v in list(c.get("parametros_variados", {}).items())[:2])
            cl_O = c.get("classificacao_O", "-")
            cl_EF = c.get("classificacao_EF", "-")
            cl_O_color = _cl_o_color(cl_O)
            return [
                Paragraph(_safe(c.get("cenario_id", "-")), st_small),
                Paragraph(_safe(params[:30]), st_small),
                Paragraph(_fmt_int(vO.get("prazo_semanas")), st_small_c),
                Paragraph(_fmt_f3(vO.get("fe_nec_medio")), st_small_c),
                Paragraph(_fmt_pct(vEF.get("margem_pct")), st_small_r),
                Paragraph(_fmt_pct(vEF.get("share_mo_pct")), st_small_r),
                Paragraph(_fmt_pct(vEF.get("share_eq_pct")), st_small_r),
                Paragraph(f"<font color='{cl_O_color}'>{_safe(cl_O)}</font>", st_small_c),
                Paragraph(_safe(cl_EF), st_small_c),
                Paragraph(_pareto_mark(c), st_small_c),
            ]

        def _build_scenarios_table(cenarios: list) -> Table:
            sc_headers = [
                "ID",
                "Parâmetros",
                "Prazo",
                "fe_nec",
                "Margem",
                "MO%",
                "EQ%",
                "O-class",
                "EF-class",
                "Pareto",
            ]
            sc_data = [[Paragraph(f"<b>{h}</b>", st_small_c) for h in sc_headers]]
            sorted_c = sorted(
                cenarios,
                key=lambda c: (c.get("rank_final") or 9999, c.get("cenario_id", "")),
            )
            for c in sorted_c:
                sc_data.append(_build_scenario_row(c))

            col_w_sc = [usable_w * x for x in [0.11, 0.19, 0.07, 0.08, 0.09, 0.07, 0.07, 0.12, 0.13, 0.07]]
            sc_tbl = Table(sc_data, colWidths=col_w_sc, repeatRows=1)
            sc_style = _tbl_style_base()
            for i, c in enumerate(sorted_c, start=1):
                if c.get("pareto_intersecao"):
                    sc_style.append(("BACKGROUND", (0, i), (-1, i), C_PARETO_BG))
            sc_tbl.setStyle(TableStyle(sc_style))
            return sc_tbl

        def _build_marginal_effects_flowables(resumos: list) -> list:
            if not resumos:
                return []
            flowables: list = [Paragraph("Efeitos Marginais", st_h3)]
            for r in resumos:
                dim = r.get("dimensao", "-")
                met = r.get("metrica", "-")
                tend = r.get("tendencia", "-")
                valores = r.get("valores", [])
                medias = r.get("medias", [])
                flowables.append(
                    Paragraph(
                        f"<b>{_safe(dim)}</b> / {_safe(met)} — tendência: <i>{_safe(tend)}</i>",
                        st_small,
                    )
                )
                if valores:
                    mg_headers = [Paragraph("<b>Valor</b>", st_small_c)] + [
                        Paragraph(_safe(str(v))[:10], st_small_c) for v in valores
                    ]
                    mg_medias = [Paragraph("<b>Média</b>", st_small_c)] + [
                        Paragraph(_fmt_f3(m), st_small_c) for m in medias
                    ]
                    col_w_mg = [usable_w * 0.20] + [usable_w * 0.80 / len(valores)] * len(valores)
                    mg_tbl = Table([mg_headers, mg_medias], colWidths=col_w_mg)
                    mg_tbl.setStyle(TableStyle(_tbl_style_base()))
                    flowables.append(mg_tbl)
                    flowables.append(Spacer(1, 1.5 * mm))
            return flowables

        def _build_face_flowables(face: dict) -> list:
            dim_x = face.get("dim_x", "-")
            dim_y = face.get("dim_y", "-")
            met = face.get("metrica", "-")
            valores_x = face.get("valores_x", [])
            valores_y = face.get("valores_y", [])
            grade = face.get("grade", [])
            flowables: list = [
                Paragraph(
                    f"<b>{_safe(dim_x)} × {_safe(dim_y)} → {_safe(met)}</b>",
                    st_small,
                )
            ]
            if valores_x and valores_y and grade:
                f_header = [
                    Paragraph(
                        f"<b>{_safe(str(dim_y)[:8])}\\{_safe(str(dim_x)[:8])}</b>",
                        st_small_c,
                    )
                ] + [Paragraph(_safe(str(vx))[:8], st_small_c) for vx in valores_x]
                f_data = [f_header]
                for vy, row in zip(valores_y, grade, strict=False):
                    f_row = [Paragraph(_safe(str(vy))[:10], st_small)] + [
                        Paragraph(_fmt_f2(v), st_small_c) for v in row
                    ]
                    f_data.append(f_row)
                col_w_f = [usable_w * 0.22] + [usable_w * 0.78 / len(valores_x)] * len(valores_x)
                f_tbl = Table(f_data, colWidths=col_w_f)
                f_tbl.setStyle(TableStyle(_tbl_style_base()))
                flowables.append(f_tbl)
                flowables.append(Spacer(1, 1.5 * mm))
            return flowables

        def _build_faces_flowables(faces: list) -> list:
            if not faces:
                return []
            flowables: list = [Spacer(1, 2 * mm), Paragraph("Faces 2D", st_h3)]
            seen: set[tuple] = set()
            for face in faces:
                key = (face.get("dim_x"), face.get("dim_y"), face.get("metrica"))
                if key in seen:
                    continue
                seen.add(key)
                flowables.extend(_build_face_flowables(face))
            return flowables

        def _build_cube_flowables(cubo: dict) -> list:
            n_cel_total = cubo.get("n_celulas_total", 0)
            n_cel_av = cubo.get("n_celulas_avaliadas", 0)
            cob_cubo = cubo.get("cobertura_pct", 0.0)
            flowables: list = [
                Paragraph("Análise do CampaignBundleCube", st_h2),
                Paragraph(
                    f"<b>Células:</b> {n_cel_av}/{n_cel_total} avaliadas ({cob_cubo:.1f}% cobertura)",
                    st_body,
                ),
                Spacer(1, 2 * mm),
            ]
            flowables.extend(_build_marginal_effects_flowables(cubo.get("resumos_marginais", [])))
            flowables.extend(_build_faces_flowables(cubo.get("faces", [])))
            return flowables

        def _build_insights_flowables(cubo: dict, cenarios: list) -> list:
            flowables: list = [Paragraph("Insights", st_h2), Spacer(1, 1 * mm)]
            for ins in _derive_insights(cubo, cenarios):
                ins_clean = ins.replace("**", "")
                flowables.append(Paragraph(f"• {_safe(ins_clean)}", st_bullet))
            return flowables

        meta = report.get("meta", {})
        shortlist = report.get("shortlist", [])
        cenarios = report.get("cenarios", [])
        cubo = report.get("cubo", {})

        story: list = []

        # ── Page 1: title + meta + shortlist ──────────────────────────────
        story.extend(_build_page1_header(meta, len(shortlist)))
        story.append(_build_shortlist_table(shortlist))
        story.append(PageBreak())

        # ── Page 2: all scenarios ─────────────────────────────────────────
        story.append(Paragraph("Todos os Cenários", st_h2))
        story.append(_build_scenarios_table(cenarios))
        story.append(PageBreak())

        # ── Page 3+: cube analysis ────────────────────────────────────────
        story.extend(_build_cube_flowables(cubo))
        story.append(PageBreak())

        # ── Last section: insights ────────────────────────────────────────
        story.extend(_build_insights_flowables(cubo, cenarios))

        doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
        return buf.getvalue()

    except ImportError:
        return None
    except Exception:
        # Fallback: minimal single-page PDF
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas as rl_canvas

            fallback_buf = BytesIO()
            c = rl_canvas.Canvas(fallback_buf, pagesize=A4)
            w, h = A4
            c.setFont("Helvetica-Bold", 14)
            meta = report.get("meta", {})
            c.drawString(16 * mm, h - 24 * mm, f"Campanha GO — {meta.get('campaign_id', '')}")
            c.setFont("Helvetica", 9)
            c.drawString(16 * mm, h - 36 * mm, f"Status: {meta.get('status', '-')}")
            c.drawString(16 * mm, h - 44 * mm, f"Cenários: {meta.get('n_avaliados', 0)}")
            c.setFont("Helvetica", 7)
            c.setFillGray(0.6)
            c.drawString(16 * mm, 12 * mm, "Relatório gerado em modo resiliente")
            c.showPage()
            c.save()
            return fallback_buf.getvalue()
        except Exception:
            return None


