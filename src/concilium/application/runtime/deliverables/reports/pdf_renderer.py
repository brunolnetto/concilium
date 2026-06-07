"""Renderizacao de Markdown para PDF para deliverables.

Backend padrao: fpdf2.
Para usar o backend ReportLab (NEP-033): CONCILIUM__PDF_RENDERER=reportlab
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable

# Feature flag — ativa o backend ReportLab sem afetar producao
_USE_REPORTLAB = os.getenv("CONCILIUM__PDF_RENDERER", "reportlab") != "fpdf2"


_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_TABLE_SEP_RE = re.compile(r"^\|[-| :]+\|$")


def _strip_inline(text: str) -> str:
    """Remove **bold** e backtick para texto plano."""
    text = _MD_BOLD_RE.sub(r"\1", text)
    return text.replace("`", "")


def _is_table_sep(line: str) -> bool:
    return bool(_MD_TABLE_SEP_RE.match(line.strip()))


def _render_table_row(pdf: object, line: str, col_w: float, row_h: float = 4.5) -> None:
    """Renderiza uma linha de tabela Markdown como celulas fpdf2."""
    raw_cells = [_strip_inline(c.strip()) for c in line.strip().strip("|").split("|")]
    n = len(raw_cells)
    if n == 0:
        return
    for i, cell in enumerate(raw_cells):
        text = cell[:35]  # trunca para caber na celula
        is_last = i == n - 1
        try:
            pdf.cell(  # type: ignore[attr-defined]
                col_w,
                row_h,
                text,
                border=0,
                new_x="LMARGIN" if is_last else "RIGHT",
                new_y="NEXT" if is_last else "TOP",
            )
        except Exception:
            pass


def render_markdown_pdf(
    md_text: str,
    title: str = "",
    image_provider: Callable[[str], bytes | None] | None = None,
) -> bytes | None:
    """Converte Markdown para PDF quando fpdf2 estiver disponivel.

    Suporta: titulos (#/##/###), tabelas, ---,  blocos de codigo (skip),
    imagens inline (via image_provider) e texto com **negrito** (stripped).
    Retorna None em ambientes sem fpdf2.
    """
    if _USE_REPORTLAB:
        from .pdf_renderer_rl import render_markdown_pdf as _rl_render

        pdf_rl = _rl_render(md_text, title, image_provider)
        if pdf_rl:
            return pdf_rl

    temp_paths: list[str] = []
    try:
        from fpdf import FPDF

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_margins(20, 20, 20)
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        if title:
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(pdf.epw, 9, title, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

        in_code_block = False
        in_table = False
        table_cols: int = 0

        for line in md_text.splitlines():
            stripped = line.strip()

            # ---- Bloco de codigo: ignora conteudo ----
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                in_table = False
                continue
            if in_code_block:
                continue

            # ---- Imagem ----
            img_match = _MD_IMAGE_RE.search(stripped)
            if img_match and image_provider is not None:
                ref = img_match.group(1).strip().strip('"').strip("'")
                name = os.path.basename(ref)
                img_bytes = image_provider(name)
                if img_bytes:
                    sfx = os.path.splitext(name)[1] or ".png"
                    with tempfile.NamedTemporaryFile(suffix=sfx, delete=False) as tmp:
                        tmp.write(img_bytes)
                        temp_paths.append(tmp.name)
                    try:
                        in_table = False
                        pdf.set_x(pdf.l_margin)
                        pdf.image(tmp.name, x=pdf.l_margin, w=pdf.epw)
                        pdf.ln(2)
                        continue
                    except Exception:
                        pass

            # ---- Titulos ----
            if stripped.startswith("### "):
                in_table = False
                pdf.set_font("Helvetica", "B", 10)
                pdf.ln(1)
                pdf.multi_cell(pdf.epw, 6, _strip_inline(stripped[4:]))
                pdf.set_font("Helvetica", "", 9)
                continue
            if stripped.startswith("## "):
                in_table = False
                pdf.set_font("Helvetica", "B", 12)
                pdf.ln(3)
                pdf.multi_cell(pdf.epw, 7, _strip_inline(stripped[3:]))
                pdf.set_font("Helvetica", "", 9)
                pdf.ln(1)
                continue
            if stripped.startswith("# "):
                in_table = False
                pdf.set_font("Helvetica", "B", 14)
                pdf.multi_cell(pdf.epw, 9, _strip_inline(stripped[2:]))
                pdf.set_font("Helvetica", "", 10)
                pdf.ln(3)
                continue

            # ---- Separador de tabela |---|---| ----
            if _is_table_sep(stripped):
                continue

            # ---- Linha de tabela ----
            if stripped.startswith("|"):
                if not in_table:
                    in_table = True
                    table_cols = stripped.count("|") - 1
                    pdf.set_font("Helvetica", "", 8)
                col_w = pdf.epw / max(table_cols, 1)
                _render_table_row(pdf, stripped, col_w)
                continue

            # ---- Linha horizontal --- ----
            if stripped == "---":
                in_table = False
                pdf.ln(2)
                continue

            # ---- Linha vazia ----
            if not stripped:
                in_table = False
                pdf.ln(2)
                continue

            # ---- Texto normal ----
            in_table = False
            pdf.set_font("Helvetica", "", 9)
            try:
                pdf.multi_cell(pdf.epw, 5, _strip_inline(stripped))
            except Exception:
                pass

        return bytes(pdf.output())
    except Exception:
        return None
    finally:
        for temp_path in temp_paths:
            try:
                os.unlink(temp_path)
            except Exception:
                pass


__all__ = ["render_markdown_pdf"]
