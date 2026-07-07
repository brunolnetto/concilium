"""ADR-070 — Campaign report generation.

Three public functions:
- serialize_campaign_report(bundle, cube) -> dict
- render_campaign_report_md(report) -> str
- render_campaign_report_pdf(report, md_text) -> bytes | None
"""

from __future__ import annotations

import html
from io import BytesIO

from concilium.domain.models.campaign.campaign import CampaignBundleCube, CampaignOutputBundle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe(v: object) -> str:
    return html.escape(str(v or ""), quote=False)


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "-"
    x = float(v)
    if -1.0 <= x <= 1.0:
        x *= 100.0
    return f"{x:.1f}%"


def _fmt_f2(v: float | None) -> str:
    return f"{v:.2f}" if v is not None else "-"


def _fmt_f3(v: float | None) -> str:
    return f"{v:.3f}" if v is not None else "-"


def _fmt_int(v: int | float | None) -> str:
    return str(int(v)) if v is not None else "-"


def _vetor_O_dict(v) -> dict:
    return {
        "prazo_semanas": v.prazo_semanas,
        "folga_semanas": v.folga_semanas,
        "fe_nec_medio": v.fe_nec_medio,
        "itens_criticos_pct": v.itens_criticos_pct,
        "gap_pool_total": v.gap_pool_total,
        "custo_mob_window_total": v.custo_mob_window_total,
        "utilizacao_recursos_pct": v.utilizacao_recursos_pct,
        "paralelismo_medio": v.paralelismo_medio,
        "idle_pool_pct": v.idle_pool_pct,
    }


def _vetor_EF_dict(v) -> dict:
    return {
        "margem_pct": v.margem_pct,
        "custo_execucao_pool": v.custo_execucao_pool,
        "custo_indireto": v.custo_indireto,
        "preco_venda": v.preco_venda,
        "ratio_pool_vs_cat": v.ratio_pool_vs_cat,
        "fidelidade_gates": v.fidelidade_gates,
        "share_mo_pct": v.share_mo_pct,
        "share_eq_pct": v.share_eq_pct,
        "share_comb_pct": v.share_comb_pct,
        "concentracao_atividade": v.concentracao_atividade,
    }


# ---------------------------------------------------------------------------
# Task 1.1 — serialize_campaign_report
# ---------------------------------------------------------------------------


def serialize_campaign_report(
    bundle: CampaignOutputBundle,
    cube: CampaignBundleCube,
) -> dict:
    """Converts CampaignOutputBundle + CampaignBundleCube to a JSON-serializable dict."""
    n_av = bundle.n_cenarios_avaliados
    n_vi = bundle.n_cenarios_viaveis
    cobertura = n_vi / n_av if n_av else 0.0

    meta = {
        "campaign_id": bundle.campaign_id,
        "campaign_version": bundle.campaign_version,
        "gerado_em": str(bundle.gerado_em),
        "status": bundle.status,
        "n_avaliados": n_av,
        "n_viaveis": n_vi,
        "n_falhas": bundle.n_falhas,
        "cobertura_pct": round(cobertura * 100, 1),
    }

    shortlist = []
    for ranked in bundle.shortlist:
        c = ranked.cenario
        j = ranked.justificativa
        shortlist.append(
            {
                "rank": ranked.rank,
                "cenario_id": c.cenario_id,
                "motivo_inclusao": j.motivo_inclusao,
                "destaques_O": j.destaques_O,
                "destaques_EF": j.destaques_EF,
                "alertas": j.alertas,
                "parametros_chave": j.parametros_chave,
                "vetor_O": _vetor_O_dict(c.vetor_O),
                "vetor_EF": _vetor_EF_dict(c.vetor_EF),
            }
        )

    cenarios = []
    for c in bundle.cenarios:
        cenarios.append(
            {
                "cenario_id": c.cenario_id,
                "viabilidade": c.viabilidade,
                "classificacao_O": c.classificacao_O,
                "classificacao_EF": c.classificacao_EF,
                "pareto_O": c.pareto_O,
                "pareto_EF": c.pareto_EF,
                "pareto_intersecao": c.pareto_intersecao,
                "rank_final": c.rank_final,
                "vetor_O": _vetor_O_dict(c.vetor_O),
                "vetor_EF": _vetor_EF_dict(c.vetor_EF),
                "parametros_variados": c.parametros_variados,
                "erro": c.erro,
            }
        )

    dimensoes = [{"nome": d.nome, "campo": d.campo, "valores": d.valores} for d in cube.dimensoes]

    resumos_marginais = [
        {
            "dimensao": r.dimensao,
            "metrica": r.metrica,
            "valores": r.valores,
            "medias": r.medias,
            "tendencia": r.tendencia,
        }
        for r in cube.resumos_marginais
    ]

    faces = [
        {
            "dim_x": f.dim_x,
            "dim_y": f.dim_y,
            "metrica": f.metrica,
            "valores_x": f.valores_x,
            "valores_y": f.valores_y,
            "grade": f.grade,
        }
        for f in cube.faces
    ]

    cubo = {
        "dimensoes": dimensoes,
        "n_celulas_total": cube.n_celulas_total,
        "n_celulas_avaliadas": cube.n_celulas_avaliadas,
        "cobertura_pct": round(cube.cobertura_pct * 100, 1),
        "resumos_marginais": resumos_marginais,
        "faces": faces,
    }

    return {"meta": meta, "shortlist": shortlist, "cenarios": cenarios, "cubo": cubo}


# ---------------------------------------------------------------------------
# Task 1.2 — render_campaign_report_md
# ---------------------------------------------------------------------------


def _md_header_lines(meta: dict) -> list[str]:
    campaign_id = meta.get("campaign_id", "-")
    status = meta.get("status", "-")
    gerado_em = str(meta.get("gerado_em", "-"))[:19].replace("T", " ")
    n_av = meta.get("n_avaliados", 0)
    n_vi = meta.get("n_viaveis", 0)
    n_fa = meta.get("n_falhas", 0)
    return [
        f"# Relatório de Campanha GO — {campaign_id}",
        "",
        f"**Status:** {status} | **Gerado em:** {gerado_em}  ",
        f"**Cenários:** {n_av} avaliados · {n_vi} viáveis · {n_fa} falhas",
        "",
    ]


def _md_shortlist_lines(shortlist: list[dict]) -> list[str]:
    lines: list[str] = [
        f"## Shortlist — Top {len(shortlist)} Candidatos",
        "",
        "| Rank | ID | Motivo | Prazo | fe_nec | Margem | MO% | EQ% | Utiliz.% |",
        "|------|-----|--------|-------|--------|--------|-----|-----|----------|",
    ]
    for item in shortlist:
        vO = item.get("vetor_O", {})
        vEF = item.get("vetor_EF", {})
        lines.append(
            f"| {item.get('rank', '-')} "
            f"| {item.get('cenario_id', '-')} "
            f"| {item.get('motivo_inclusao', '-')} "
            f"| {_fmt_int(vO.get('prazo_semanas'))} "
            f"| {_fmt_f3(vO.get('fe_nec_medio'))} "
            f"| {_fmt_pct(vEF.get('margem_pct'))} "
            f"| {_fmt_pct(vEF.get('share_mo_pct'))} "
            f"| {_fmt_pct(vEF.get('share_eq_pct'))} "
            f"| {_fmt_pct(vO.get('utilizacao_recursos_pct'))} |"
        )
    lines.append("")
    return lines


def _pareto_mark(item: dict) -> str:
    if item.get("pareto_intersecao"):
        return "★"
    if item.get("pareto_O"):
        return "O"
    if item.get("pareto_EF"):
        return "EF"
    return "-"


def _md_cenarios_lines(cenarios: list[dict]) -> list[str]:
    lines: list[str] = [
        "## Todos os Cenários",
        "",
        "| ID | Parâmetros | Prazo | fe_nec | Margem | MO% | EQ% | O-class | EF-class | Pareto |",
        "|-----|-----------|-------|--------|--------|-----|-----|---------|----------|--------|",
    ]
    for c in cenarios:
        vO = c.get("vetor_O", {})
        vEF = c.get("vetor_EF", {})
        params = "; ".join(f"{k}={v}" for k, v in list(c.get("parametros_variados", {}).items())[:2])
        lines.append(
            f"| {c.get('cenario_id', '-')} "
            f"| {params[:30]} "
            f"| {_fmt_int(vO.get('prazo_semanas'))} "
            f"| {_fmt_f3(vO.get('fe_nec_medio'))} "
            f"| {_fmt_pct(vEF.get('margem_pct'))} "
            f"| {_fmt_pct(vEF.get('share_mo_pct'))} "
            f"| {_fmt_pct(vEF.get('share_eq_pct'))} "
            f"| {c.get('classificacao_O', '-')} "
            f"| {c.get('classificacao_EF', '-')} "
            f"| {_pareto_mark(c)} |"
        )
    lines.append("")
    return lines


def _md_marginal_effects_lines(resumos: list[dict]) -> list[str]:
    if not resumos:
        return []
    lines: list[str] = ["### Efeitos Marginais", ""]
    for r in resumos:
        dim = r.get("dimensao", "-")
        met = r.get("metrica", "-")
        tend = r.get("tendencia", "-")
        valores = r.get("valores", [])
        medias = r.get("medias", [])
        lines.append(f"**{dim} / {met}** — tendência: `{tend}`")
        lines.append("")
        header_vals = " | ".join(str(v)[:10] for v in valores)
        lines.append(f"| Valor | {header_vals} |")
        lines.append(f"|-------|{'|'.join('------' for _ in valores)}|")
        media_vals = " | ".join(_fmt_f3(m) for m in medias)
        lines.append(f"| Média | {media_vals} |")
        lines.append("")
    return lines


def _md_faces_lines(faces: list[dict]) -> list[str]:
    if not faces:
        return []
    lines: list[str] = ["### Faces 2D", ""]
    seen: set[tuple] = set()
    for face in faces:
        key = (face.get("dim_x"), face.get("dim_y"), face.get("metrica"))
        if key in seen:
            continue
        seen.add(key)
        dim_x = face.get("dim_x", "-")
        dim_y = face.get("dim_y", "-")
        met = face.get("metrica", "-")
        valores_x = face.get("valores_x", [])
        valores_y = face.get("valores_y", [])
        grade = face.get("grade", [])
        lines.append(f"**{dim_x} × {dim_y} → {met}**")
        lines.append("")
        header_cols = " | ".join(str(vx)[:10] for vx in valores_x)
        lines.append(f"| {dim_y} \\ {dim_x} | {header_cols} |")
        lines.append(f"|{'---|' * (len(valores_x) + 1)}")
        for vy, row in zip(valores_y, grade, strict=False):
            row_vals = " | ".join(_fmt_f2(v) for v in row)
            lines.append(f"| {str(vy)[:12]} | {row_vals} |")
        lines.append("")
    return lines


def _md_cubo_lines(cubo: dict) -> list[str]:
    n_cel_total = cubo.get("n_celulas_total", 0)
    n_cel_av = cubo.get("n_celulas_avaliadas", 0)
    cob = cubo.get("cobertura_pct", 0.0)
    lines: list[str] = [
        "## Análise do CampaignBundleCube",
        "",
        f"**Células:** {n_cel_av}/{n_cel_total} avaliadas ({cob:.1f}% cobertura)",
        "",
    ]
    lines.extend(_md_marginal_effects_lines(cubo.get("resumos_marginais", [])))
    lines.extend(_md_faces_lines(cubo.get("faces", [])))
    return lines


def _md_insights_lines(cubo: dict, cenarios: list[dict]) -> list[str]:
    lines: list[str] = ["## Insights", ""]
    for insight in _derive_insights(cubo, cenarios):
        lines.append(f"- {insight}")
    lines.append("")
    return lines


def render_campaign_report_md(report: dict) -> str:
    """Generates Markdown from the serialized campaign report dict."""
    meta = report.get("meta", {})
    shortlist = report.get("shortlist", [])
    cenarios = report.get("cenarios", [])
    cubo = report.get("cubo", {})

    lines: list[str] = []
    lines.extend(_md_header_lines(meta))
    lines.extend(_md_shortlist_lines(shortlist))
    lines.extend(_md_cenarios_lines(cenarios))
    lines.extend(_md_cubo_lines(cubo))
    lines.extend(_md_insights_lines(cubo, cenarios))

    return "\n".join(lines)


def _insight_best_lever(resumos: list[dict], metrica: str, label: str) -> str | None:
    """Finds the resumo with the widest marginal range for a metric and formats an insight."""
    candidatos = [r for r in resumos if r.get("metrica") == metrica]
    if not candidatos:
        return None
    best = max(
        candidatos,
        key=lambda r: _marginal_range(r.get("medias", [])),
    )
    return f"Lever mais impactante em {label}: **{best['dimensao']}** (tendência: {best['tendencia']})"


def _insight_paralelismo_from_resumos(para_resumos: list[dict]) -> str | None:
    all_medias = [m for r in para_resumos for m in r.get("medias", []) if m is not None]
    if not all_medias:
        return None
    avg_para = sum(all_medias) / len(all_medias)
    return f"Paralelismo médio: {avg_para:.1f} atividades/semana"


def _insight_paralelismo_from_cenarios(cenarios: list[dict]) -> str | None:
    paras = [
        c.get("vetor_O", {}).get("paralelismo_medio")
        for c in cenarios
        if c.get("vetor_O", {}).get("paralelismo_medio") is not None
    ]
    if not paras:
        return None
    avg_para = sum(paras) / len(paras)
    return f"Paralelismo médio (cenários viáveis): {avg_para:.1f} atividades/semana"


def _insight_paralelismo(resumos: list[dict], cenarios: list[dict]) -> str | None:
    para_resumos = [r for r in resumos if r.get("metrica") == "paralelismo_medio"]
    if para_resumos:
        return _insight_paralelismo_from_resumos(para_resumos)
    return _insight_paralelismo_from_cenarios(cenarios)


def _shares_de(cenarios: list[dict], campo: str) -> list[float]:
    return [c.get("vetor_EF", {}).get(campo) for c in cenarios if c.get("vetor_EF", {}).get(campo) is not None]


def _insight_composicao_custo(cenarios: list[dict]) -> str | None:
    eq_shares = _shares_de(cenarios, "share_eq_pct")
    mo_shares = _shares_de(cenarios, "share_mo_pct")
    if not eq_shares and not mo_shares:
        return None
    avg_eq = (sum(eq_shares) / len(eq_shares) * 100) if eq_shares else 0.0
    avg_mo = (sum(mo_shares) / len(mo_shares) * 100) if mo_shares else 0.0
    dominant = "equipamento" if avg_eq > avg_mo else "mão-de-obra"
    dom_pct = avg_eq if avg_eq > avg_mo else avg_mo
    return f"Composição de custo dominante: {dom_pct:.1f}% {dominant}"


def _insight_fallback_viabilidade(cenarios: list[dict]) -> str:
    n_vi = sum(1 for c in cenarios if c.get("viabilidade") in {"APROVADO", "APROVADO_COM_RESSALVAS"})
    n_tot = len(cenarios)
    return f"Taxa de viabilidade: {n_vi}/{n_tot} cenários aprovados"


def _derive_insights(cubo: dict, cenarios: list[dict]) -> list[str]:
    """Auto-derive 3-5 bullet insights from marginal effects and scenario data."""
    insights: list[str] = []
    resumos = cubo.get("resumos_marginais", [])

    prazo_insight = _insight_best_lever(resumos, "prazo_semanas", "prazo")
    if prazo_insight:
        insights.append(prazo_insight)

    margem_insight = _insight_best_lever(resumos, "margem_pct", "margem")
    if margem_insight:
        insights.append(margem_insight)

    para_insight = _insight_paralelismo(resumos, cenarios)
    if para_insight:
        insights.append(para_insight)

    custo_insight = _insight_composicao_custo(cenarios)
    if custo_insight:
        insights.append(custo_insight)

    if not insights:
        insights.append(_insight_fallback_viabilidade(cenarios))

    return insights[:5]


def _marginal_range(medias: list) -> float:
    valid = [m for m in medias if m is not None]
    if len(valid) < 2:
        return 0.0
    return abs(max(valid) - min(valid))


# ---------------------------------------------------------------------------
# Task 1.3 — render_campaign_report_pdf
# ---------------------------------------------------------------------------


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
