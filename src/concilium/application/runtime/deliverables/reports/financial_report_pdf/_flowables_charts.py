"""Relatório financeiro PDF (parte extraída de financial_report_pdf.py, grupo _flowables_charts)."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

from ._text_helpers import _chart_caption, _chart_label, _safe_text


def _build_charts_flowables(
    image_provider: Callable[[str], bytes | None] | None,
    styles: dict,
    rl: dict,
    usable_w: float,
    page_h: float,
) -> list:
    """Bloco 'Principais Gráficos' com legendas, no máximo 4 imagens (Issue 2+4+5)."""
    if not image_provider:
        return []

    Image = rl["Image"]
    Paragraph = rl["Paragraph"]
    KeepTogether = rl["KeepTogether"]
    Spacer = rl["Spacer"]
    mm = rl["mm"]

    flowables: list = [Spacer(1, 2 * mm), Paragraph("Principais Gráficos", styles["h2"])]

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
                Paragraph(_safe_text(_chart_label(name)), styles["h2"]),
            ]
            if caption_text:
                chart_block.append(Paragraph(_safe_text(caption_text), styles["caption"]))
            chart_block.append(img)
            # Issue 4: KeepTogether so title doesn't orphan from image
            flowables.append(KeepTogether(chart_block))
            images_added += 1
        except Exception:
            pass

    return flowables


