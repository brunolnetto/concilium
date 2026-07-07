"""Renderizacao de Markdown para PDF usando ReportLab/Platypus.

Implementa a mesma API publica de ``pdf_renderer.py`` (render_markdown_pdf),
substituindo o backend fpdf2 por ReportLab Platypus para resolver:
- Tabelas truncadas (celulas agora usam Paragraph com wrapping)
- Blocos de codigo silenciosamente descartados (Preformatted com fundo cinza)
- Ausencia de cabecalho/rodape com numeracao de paginas
- Imagens sem controle de aspect ratio

Ref: NEP-033 / ADR-083
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from io import BytesIO
from xml.sax.saxutils import escape as _xml_escape

_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_TABLE_SEP_RE = re.compile(r"^\|[-| :]+\|$")
_MD_CODE_FENCE_RE = re.compile(r"^```")


# ---------------------------------------------------------------------------
# Inline markup conversion
# ---------------------------------------------------------------------------


def _inline_markup(text: str) -> str:
    """Converte Markdown inline para XML tags do ReportLab.

    Ordem: escape XML primeiro, depois aplica tags para nao duplo-escapar.
    """
    escaped = _xml_escape(text)
    escaped = _MD_BOLD_RE.sub(r"<b>\1</b>", escaped)
    escaped = _MD_INLINE_CODE_RE.sub(r'<font name="Courier">\1</font>', escaped)
    return escaped


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------


def _make_styles() -> dict:
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm

    base = getSampleStyleSheet()
    dark = colors.HexColor("#1a1a2e")

    return {
        "h1": ParagraphStyle(
            "rl_h1",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
            textColor=dark,
        ),
        "h2": ParagraphStyle(
            "rl_h2",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
            textColor=dark,
        ),
        "h3": ParagraphStyle(
            "rl_h3",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            spaceBefore=3 * mm,
            spaceAfter=1 * mm,
        ),
        "body": ParagraphStyle(
            "rl_body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            spaceAfter=2 * mm,
        ),
        "bullet": ParagraphStyle(
            "rl_bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            leftIndent=5 * mm,
            spaceAfter=1 * mm,
        ),
        "code": ParagraphStyle(
            "rl_code",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8,
            leading=11,
            leftIndent=4 * mm,
            rightIndent=4 * mm,
            backColor=colors.HexColor("#f3f3f3"),
            spaceAfter=2 * mm,
        ),
        "table_header": ParagraphStyle(
            "rl_table_header",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
        ),
        "table_cell": ParagraphStyle(
            "rl_table_cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
        ),
    }


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------


def _is_table_sep(line: str) -> bool:
    return bool(_MD_TABLE_SEP_RE.match(line.strip()))


def _parse_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _flush_table(
    table_rows: list[list[str]],
    styles: dict,
    usable_width: float,
):
    """Converte linhas de tabela acumuladas em um flowable Table do ReportLab."""
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    # Único chamador (flush_table() em _parse_md_to_story) só invoca esta
    # função quando table_rows já foi verificado como não-vazio.
    n_cols = max(len(r) for r in table_rows)
    col_w = usable_width / n_cols

    data = []
    for i, row in enumerate(table_rows):
        cell_style = styles["table_header"] if i == 0 else styles["table_cell"]
        padded = row + [""] * (n_cols - len(row))
        data.append([Paragraph(_inline_markup(c), cell_style) for c in padded])

    ts = TableStyle(
        [
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e0e0")),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#f8f8f8")],
            ),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]
    )

    return Table(data, colWidths=[col_w] * n_cols, style=ts, repeatRows=1)


# ---------------------------------------------------------------------------
# Markdown → Platypus story parser
# ---------------------------------------------------------------------------


class _MdParseState:
    """Estado mut\u00e1vel acumulado ao longo do parsing linha-a-linha do Markdown."""

    __slots__ = ("story", "in_code_block", "code_lines", "in_table", "table_rows")

    def __init__(self) -> None:
        self.story: list = []
        self.in_code_block = False
        self.code_lines: list[str] = []
        self.in_table = False
        self.table_rows: list[list[str]] = []


def _md_flush_table(state: _MdParseState, styles: dict, usable_width: float) -> None:
    from reportlab.lib.units import mm
    from reportlab.platypus import Spacer

    if state.in_table and state.table_rows:
        tbl = _flush_table(state.table_rows, styles, usable_width)
        if tbl is not None:
            state.story.append(tbl)
            state.story.append(Spacer(1, 3 * mm))
    state.in_table = False
    state.table_rows.clear()


def _md_flush_code(state: _MdParseState, styles: dict) -> None:
    from reportlab.lib.units import mm
    from reportlab.platypus import Preformatted, Spacer

    if state.code_lines:
        state.story.append(Preformatted("\n".join(state.code_lines), styles["code"]))
        state.story.append(Spacer(1, 2 * mm))
    state.in_code_block = False
    state.code_lines.clear()


def _md_toggle_code_fence(state: _MdParseState, styles: dict, usable_width: float) -> None:
    if state.in_code_block:
        _md_flush_code(state, styles)
    else:
        _md_flush_table(state, styles, usable_width)
        state.in_code_block = True


def _md_handle_image(
    state: _MdParseState,
    img_match: re.Match,
    image_provider: Callable[[str], bytes | None],
    usable_width: float,
) -> None:
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Spacer

    ref = img_match.group(1).strip().strip('"').strip("'")
    name = os.path.basename(ref)
    img_bytes = image_provider(name)
    if not img_bytes:
        return
    try:
        img = Image(BytesIO(img_bytes), width=usable_width)
        img.hAlign = "LEFT"
        state.story.append(img)
        state.story.append(Spacer(1, 3 * mm))
    except Exception:
        pass


def _md_handle_heading(stripped: str, state: _MdParseState, styles: dict, usable_width: float) -> bool:
    from reportlab.platypus import Paragraph

    for prefix, style_key in (("### ", "h3"), ("## ", "h2"), ("# ", "h1")):
        if stripped.startswith(prefix):
            _md_flush_table(state, styles, usable_width)
            state.story.append(Paragraph(_inline_markup(stripped[len(prefix) :]), styles[style_key]))
            return True
    return False


def _md_handle_plain_line(stripped: str, state: _MdParseState, styles: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, Spacer

    # ---- Horizontal rule ----
    if stripped == "---":
        state.story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=2 * mm))
        return

    # ---- Empty line ----
    if not stripped:
        state.story.append(Spacer(1, 2 * mm))
        return

    # ---- List item ----
    if stripped.startswith("- ") or stripped.startswith("* "):
        state.story.append(Paragraph(f"\u2022 {_inline_markup(stripped[2:])}", styles["bullet"]))
        return

    # ---- Normal paragraph ----
    state.story.append(Paragraph(_inline_markup(stripped), styles["body"]))


def _md_process_line(
    line: str,
    state: _MdParseState,
    image_provider: Callable[[str], bytes | None] | None,
    styles: dict,
    usable_width: float,
) -> None:
    stripped = line.strip()

    # ---- Code fence ----
    if _MD_CODE_FENCE_RE.match(stripped):
        _md_toggle_code_fence(state, styles, usable_width)
        return

    if state.in_code_block:
        state.code_lines.append(line)
        return

    # ---- Image ----
    img_match = _MD_IMAGE_RE.search(stripped)
    if img_match and image_provider is not None:
        _md_flush_table(state, styles, usable_width)
        _md_handle_image(state, img_match, image_provider, usable_width)
        return

    # ---- Headings ----
    if _md_handle_heading(stripped, state, styles, usable_width):
        return

    # ---- Table separator ----
    if _is_table_sep(stripped):
        return

    # ---- Table row ----
    if stripped.startswith("|"):
        state.in_table = True
        state.table_rows.append(_parse_row(stripped))
        return

    # Leaving table mode
    _md_flush_table(state, styles, usable_width)

    _md_handle_plain_line(stripped, state, styles)


def _parse_md_to_story(
    md_text: str,
    image_provider: Callable[[str], bytes | None] | None,
    styles: dict,
    usable_width: float,
) -> list:
    state = _MdParseState()

    for line in md_text.splitlines():
        _md_process_line(line, state, image_provider, styles, usable_width)

    # Flush remaining state
    if state.in_code_block:
        _md_flush_code(state, styles)
    _md_flush_table(state, styles, usable_width)

    return state.story


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------


def _build_doc(story: list, title: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    margin = 20 * mm
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin + 8 * mm,  # extra room for header
        bottomMargin=margin,
        title=title,
    )

    page_w, page_h = A4

    def _on_page(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        if title:
            canvas.drawString(margin, page_h - 12 * mm, title)
        canvas.drawCentredString(page_w / 2, 8 * mm, f"P\u00e1g. {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_markdown_pdf(
    md_text: str,
    title: str = "",
    image_provider: Callable[[str], bytes | None] | None = None,
) -> bytes | None:
    """Converte Markdown para PDF usando ReportLab/Platypus.

    API identica ao renderer fpdf2 — todos os callers existentes funcionam sem
    alteracao. Ativado via variavel de ambiente CONCILIUM__PDF_RENDERER=reportlab.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import Spacer

        margin = 20 * mm
        page_w, _ = A4
        usable_width = page_w - 2 * margin

        styles = _make_styles()
        story = _parse_md_to_story(md_text, image_provider, styles, usable_width)

        if not story:
            story = [Spacer(1, 1)]

        return _build_doc(story, title)
    except Exception:
        return None


__all__ = ["render_markdown_pdf"]
