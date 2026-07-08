"""ADR-070 — Campaign report generation — render_campaign_report_md e linhas de markdown."""

from __future__ import annotations

from ._helpers import _fmt_f2, _fmt_f3, _fmt_int, _fmt_pct
from ._insights import _derive_insights


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


