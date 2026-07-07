"""Renderizacao de Markdown para PDF para deliverables.

Backend padrão: ReportLab (NEP-033 — melhor suporte a tabelas, blocos de código,
cabeçalho/rodapé e imagens com aspect ratio correto).
Para usar o backend legado fpdf2: CONCILIUM__PDF_RENDERER=fpdf2
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fpdf import FPDF

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


def _render_table_row(pdf: FPDF, line: str, col_w: float, row_h: float = 4.5) -> None:
    """Renderiza uma linha de tabela Markdown como celulas fpdf2."""
    raw_cells = [_strip_inline(c.strip()) for c in line.strip().strip("|").split("|")]
    n = len(raw_cells)
    if n == 0:  # pragma: no cover
        return
    for i, cell in enumerate(raw_cells):
        text = cell[:35]  # trunca para caber na celula
        is_last = i == n - 1
        try:
            pdf.cell(
                col_w,
                row_h,
                text,
                border=0,
                new_x="LMARGIN" if is_last else "RIGHT",
                new_y="NEXT" if is_last else "TOP",
            )
        except Exception:
            pass


def _try_render_image_line(
    pdf: FPDF,
    stripped: str,
    image_provider: Callable[[str], bytes | None] | None,
    temp_paths: list[str],
    state: dict,
) -> bool:
    """Renderiza a linha como imagem se ela referenciar uma; retorna True se tratada."""
    img_match = _MD_IMAGE_RE.search(stripped)
    if not (img_match and image_provider is not None):
        return False
    ref = img_match.group(1).strip().strip('"').strip("'")
    name = os.path.basename(ref)
    img_bytes = image_provider(name)
    if not img_bytes:
        return False
    sfx = os.path.splitext(name)[1] or ".png"
    with tempfile.NamedTemporaryFile(suffix=sfx, delete=False) as tmp:
        tmp.write(img_bytes)
        temp_paths.append(tmp.name)
    try:
        state["in_table"] = False
        pdf.set_x(pdf.l_margin)
        pdf.image(tmp.name, x=pdf.l_margin, w=pdf.epw)
        pdf.ln(2)
        return True
    except Exception:
        return False


def _try_render_heading_line(pdf: FPDF, stripped: str, state: dict) -> bool:
    """Renderiza a linha como título (###/##/#) se aplicável; retorna True se tratada."""
    if stripped.startswith("### "):
        state["in_table"] = False
        pdf.set_font("Helvetica", "B", 10)
        pdf.ln(1)
        pdf.multi_cell(pdf.epw, 6, _strip_inline(stripped[4:]))
        pdf.set_font("Helvetica", "", 9)
        return True
    if stripped.startswith("## "):
        state["in_table"] = False
        pdf.set_font("Helvetica", "B", 12)
        pdf.ln(3)
        pdf.multi_cell(pdf.epw, 7, _strip_inline(stripped[3:]))
        pdf.set_font("Helvetica", "", 9)
        pdf.ln(1)
        return True
    if stripped.startswith("# "):
        state["in_table"] = False
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(pdf.epw, 9, _strip_inline(stripped[2:]))
        pdf.set_font("Helvetica", "", 10)
        pdf.ln(3)
        return True
    return False


def _render_table_line(pdf: FPDF, stripped: str, state: dict) -> None:
    """Renderiza uma linha de tabela Markdown, iniciando a tabela se necessário."""
    if not state["in_table"]:
        state["in_table"] = True
        state["table_cols"] = stripped.count("|") - 1
        pdf.set_font("Helvetica", "", 8)
    col_w = pdf.epw / max(state["table_cols"], 1)
    _render_table_row(pdf, stripped, col_w)


def _process_pdf_line(
    pdf: FPDF,
    stripped: str,
    image_provider: Callable[[str], bytes | None] | None,
    temp_paths: list[str],
    state: dict,
) -> None:
    """Processa uma única linha de Markdown, atualizando o PDF e o estado do parser."""
    # ---- Bloco de codigo: ignora conteudo ----
    if stripped.startswith("```"):
        state["in_code_block"] = not state["in_code_block"]
        state["in_table"] = False
        return
    if state["in_code_block"]:
        return

    # ---- Imagem ----
    if _try_render_image_line(pdf, stripped, image_provider, temp_paths, state):
        return

    # ---- Titulos ----
    if _try_render_heading_line(pdf, stripped, state):
        return

    # ---- Separador de tabela |---|---| ----
    if _is_table_sep(stripped):
        return

    # ---- Linha de tabela ----
    if stripped.startswith("|"):
        _render_table_line(pdf, stripped, state)
        return

    # ---- Linha horizontal --- ----
    if stripped == "---":
        state["in_table"] = False
        pdf.ln(2)
        return

    # ---- Linha vazia ----
    if not stripped:
        state["in_table"] = False
        pdf.ln(2)
        return

    # ---- Texto normal ----
    state["in_table"] = False
    pdf.set_font("Helvetica", "", 9)
    try:
        pdf.multi_cell(pdf.epw, 5, _strip_inline(stripped))
    except Exception:
        pass


def _render_fpdf_body(
    pdf: FPDF,
    md_text: str,
    image_provider: Callable[[str], bytes | None] | None,
    temp_paths: list[str],
) -> None:
    """Percorre as linhas do Markdown, delegando a cada uma o processamento apropriado."""
    state: dict = {"in_code_block": False, "in_table": False, "table_cols": 0}
    for line in md_text.splitlines():
        _process_pdf_line(pdf, line.strip(), image_provider, temp_paths, state)


def render_markdown_pdf(
    md_text: str,
    title: str = "",
    image_provider: Callable[[str], bytes | None] | None = None,
) -> bytes | None:
    """Converte Markdown para PDF.

    Backend padrão: ReportLab (NEP-033). Fallback: fpdf2 (legado).
    Retorna None se nenhum backend disponível ou se md_text estiver vazio.
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

        _render_fpdf_body(pdf, md_text, image_provider, temp_paths)

        return bytes(pdf.output())
    except Exception:
        return None
    finally:
        for temp_path in temp_paths:
            try:
                os.unlink(temp_path)
            except Exception:  # pragma: no cover
                pass


__all__ = ["render_markdown_pdf"]
