#!/usr/bin/env python3
"""Gera PDF do relatório de estado da solução a partir do markdown."""

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Paleta ────────────────────────────────────────────────────────────────────
BLUE_DARK = colors.HexColor("#1a3a5c")
BLUE_MID = colors.HexColor("#2e6da4")
BLUE_LIGHT = colors.HexColor("#d6e4f0")
GREY_LIGHT = colors.HexColor("#f5f5f5")
GREY_MID = colors.HexColor("#cccccc")
ORANGE = colors.HexColor("#e07b39")
BLACK = colors.black
WHITE = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 2.5 * cm
BODY_W = PAGE_W - 2 * MARGIN


def make_styles() -> dict:
    base = getSampleStyleSheet()
    styles: dict = {}

    styles["title"] = ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=28,
        textColor=BLUE_DARK,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    styles["subtitle"] = ParagraphStyle(
        "subtitle",
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#555555"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    styles["h1"] = ParagraphStyle(
        "h1",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=20,
        textColor=WHITE,
        spaceBefore=18,
        spaceAfter=4,
        leftIndent=0,
    )
    styles["h2"] = ParagraphStyle(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=BLUE_DARK,
        spaceBefore=12,
        spaceAfter=4,
        borderPad=2,
    )
    styles["h3"] = ParagraphStyle(
        "h3",
        fontName="Helvetica-BoldOblique",
        fontSize=11,
        leading=14,
        textColor=BLUE_MID,
        spaceBefore=8,
        spaceAfter=3,
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        textColor=BLACK,
        spaceAfter=6,
        alignment=TA_LEFT,
    )
    styles["code"] = ParagraphStyle(
        "code",
        fontName="Courier",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1a1a1a"),
        backColor=GREY_LIGHT,
        leftIndent=8,
        rightIndent=8,
        spaceAfter=6,
        spaceBefore=4,
        borderPad=4,
        borderWidth=0.5,
        borderColor=GREY_MID,
        borderRadius=3,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        leftIndent=18,
        firstLineIndent=-10,
        spaceAfter=3,
        textColor=BLACK,
    )
    styles["note"] = ParagraphStyle(
        "note",
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#666666"),
        spaceAfter=4,
    )
    return styles


def escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_format(text: str) -> str:
    """Convert backtick code spans and **bold** to ReportLab XML tags."""
    text = escape_xml(text)
    # Bold: **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic: *text* or _text_
    text = re.sub(r"\*([^*]+?)\*", r"<i>\1</i>", text)
    # Code spans
    text = re.sub(r"`([^`]+?)`", r'<font name="Courier" size="9"><b>\1</b></font>', text)
    # Math: $...$  (strip delimiters, keep content)
    text = re.sub(r"\$([^$]+?)\$", r"<i>\1</i>", text)
    return text


def make_h1_block(text: str, styles: dict) -> list:
    """H1 rendered as a coloured banner paragraph."""
    safe = inline_format(text.lstrip("#").strip())
    banner = Table(
        [[Paragraph(safe, styles["h1"])]],
        colWidths=[BODY_W],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BLUE_DARK),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
            ]
        )
    )
    return [Spacer(1, 0.2 * cm), banner, Spacer(1, 0.15 * cm)]


def parse_table(lines: list[str], styles: dict) -> Table:
    rows = []
    for i, line in enumerate(lines):
        if re.match(r"^\s*\|[-: |]+\|\s*$", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        style = styles["h3"] if i == 0 else styles["body"]
        rows.append([Paragraph(inline_format(c), style) for c in cells])

    col_count = max(len(r) for r in rows)
    col_w = BODY_W / col_count

    t = Table(rows, colWidths=[col_w] * col_count, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE_LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, 0), BLUE_DARK),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GREY_LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.4, GREY_MID),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def md_to_flowables(md_text: str, styles: dict) -> list:
    story = []
    lines = md_text.splitlines()
    i = 0
    in_code = False
    code_lines: list[str] = []
    table_lines: list[str] = []
    in_table = False

    def flush_code():
        nonlocal code_lines
        if code_lines:
            block = "\n".join(escape_xml(l) for l in code_lines)
            story.append(Paragraph(block.replace("\n", "<br/>"), styles["code"]))
            code_lines = []

    def flush_table():
        nonlocal table_lines, in_table
        if table_lines:
            story.append(Spacer(1, 0.1 * cm))
            story.append(parse_table(table_lines, styles))
            story.append(Spacer(1, 0.2 * cm))
            table_lines = []
            in_table = False

    # Skip YAML front-matter if present
    while i < len(lines):
        line = lines[i]

        # Code fence
        if line.strip().startswith("```"):
            if not in_code:
                flush_table()
                in_code = True
                i += 1
                continue
            else:
                in_code = False
                flush_code()
                i += 1
                continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # Table rows
        if line.strip().startswith("|"):
            if not in_table:
                in_table = True
            table_lines.append(line)
            i += 1
            continue
        else:
            flush_table()

        # Headings
        if line.startswith("# ") and not line.startswith("## "):
            story.extend(make_h1_block(line, styles))
            i += 1
            continue

        if line.startswith("## "):
            text = inline_format(line.lstrip("#").strip())
            story.append(Paragraph(text, styles["h2"]))
            story.append(HRFlowable(width=BODY_W, thickness=1, color=BLUE_MID, spaceAfter=4))
            i += 1
            continue

        if line.startswith("### "):
            text = inline_format(line.lstrip("#").strip())
            story.append(Paragraph(text, styles["h3"]))
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^---+\s*$", line):
            story.append(HRFlowable(width=BODY_W, thickness=0.5, color=GREY_MID, spaceBefore=4, spaceAfter=4))
            i += 1
            continue

        # Bullet / list
        m = re.match(r"^(\s*)[*\-+] (.*)", line)
        if m:
            indent = len(m.group(1))
            text = inline_format(m.group(2))
            bullet_char = "•" if indent == 0 else "◦"
            p = ParagraphStyle(
                "bul",
                parent=styles["bullet"],
                leftIndent=18 + indent * 10,
                firstLineIndent=-(10 + indent * 2),
            )
            story.append(Paragraph(f"{bullet_char}  {text}", p))
            i += 1
            continue

        # Numbered list
        m2 = re.match(r"^\d+\. (.*)", line)
        if m2:
            text = inline_format(m2.group(1))
            story.append(Paragraph(f"  {text}", styles["bullet"]))
            i += 1
            continue

        # Blank line
        if not line.strip():
            story.append(Spacer(1, 0.12 * cm))
            i += 1
            continue

        # Normal paragraph
        story.append(Paragraph(inline_format(line.strip()), styles["body"]))
        i += 1

    flush_code()
    flush_table()
    return story


def make_cover(styles: dict) -> list:
    cover = []
    cover.append(Spacer(1, 3 * cm))

    # Title band
    title_table = Table(
        [[Paragraph("Relatório de Estado da Solução", styles["title"])]],
        colWidths=[BODY_W],
    )
    title_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BLUE_LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    cover.append(title_table)
    cover.append(Spacer(1, 0.5 * cm))

    subtitle_data = [
        ["Sistema", "Concilium / AGIS — Agente Gerente de Engenharia"],
        ["Repositório", "mendes-lobo-construcao/agente-gerente-de-engenharia"],
        ["Branch", "main"],
        ["Data", "2026-08-14"],
        ["Audiência", "Engenheiros e times que continuarão o desenvolvimento"],
    ]
    meta_style = ParagraphStyle("meta", fontName="Helvetica", fontSize=10, leading=14)
    meta_bold = ParagraphStyle("meta_b", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=BLUE_DARK)
    rows = [[Paragraph(k, meta_bold), Paragraph(v, meta_style)] for k, v in subtitle_data]
    t = Table(rows, colWidths=[3.5 * cm, BODY_W - 3.5 * cm])
    t.setStyle(
        TableStyle(
            [
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, GREY_LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.4, GREY_MID),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    cover.append(t)
    cover.append(PageBreak())
    return cover


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#888888"))
    page_num = canvas.getPageNumber()
    canvas.drawRightString(PAGE_W - MARGIN, 1.2 * cm, f"Página {page_num}")
    canvas.drawString(MARGIN, 1.2 * cm, "Concilium / AGIS — Relatório de Estado — 2026-08-14")
    canvas.line(MARGIN, 1.5 * cm, PAGE_W - MARGIN, 1.5 * cm)
    canvas.restoreState()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    src = root / "docs" / "RELATORIO_ESTADO_DA_SOLUCAO.md"
    dst = root / "docs" / "RELATORIO_ESTADO_DA_SOLUCAO.pdf"

    if not src.exists():
        print(f"Arquivo não encontrado: {src}", file=sys.stderr)
        return 1

    md_text = src.read_text(encoding="utf-8")
    # Strip the initial H1 (goes to cover) and metadata header lines
    md_text = re.sub(r"^# .+\n(\*\*.+\*\*\s*\n)+\n---\n", "", md_text, flags=re.MULTILINE)

    styles = make_styles()

    doc = SimpleDocTemplate(
        str(dst),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Relatório de Estado da Solução — Concilium / AGIS",
        author="Mendes Lobo Construção",
        subject="Documentação técnica para continuidade do desenvolvimento",
    )

    story = make_cover(styles)
    story += md_to_flowables(md_text, styles)

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"PDF gerado: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
