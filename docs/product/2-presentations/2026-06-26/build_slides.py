"""
Concilium Tech Overview — Canvas direto (sem Platypus), fórmulas via matplotlib mathtext.
Dimensões 16:9: 960 × 540 pt.
"""
import io
import os
import math as _math

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph

# ── Dimensões ─────────────────────────────────────────────────────────────────
W, H = 960, 540
HDR_H  = 48
FTR_H  = 22
CX     = 40
CW     = W - 80
CT     = H - HDR_H   # 492
CB     = FTR_H       # 22
CH     = CT - CB     # 470

# ── Paleta ────────────────────────────────────────────────────────────────────
BLUE    = colors.HexColor("#123456")
BLUE2   = colors.HexColor("#1A4A7A")
ORANGE  = colors.HexColor("#D6641C")
GREEN   = colors.HexColor("#277848")
RED     = colors.HexColor("#B42323")
GRAY    = colors.HexColor("#F0F2F5")
LGRAY   = colors.HexColor("#D8DCE2")
MUTED   = colors.HexColor("#5A6370")
WHITE   = colors.white
BLACK   = colors.HexColor("#1A1A1A")
BLUE_LT = colors.HexColor("#A8C4E0")
DARK    = colors.HexColor("#0D2A44")

ROLE_COLORS = {
    "operator":    colors.HexColor("#1A6FAA"),
    "engineer":    colors.HexColor("#277848"),
    "admin":       colors.HexColor("#B46010"),
    "auditor":     colors.HexColor("#6A4C93"),
    "cat-manager": colors.HexColor("#0D7A7A"),
}

# Nomes de negocio dos papeis (substituem os identificadores técnicos em ingles)
ROLE_PT = {
    "operator":    "Comercial",
    "engineer":    "Engenharia",
    "admin":       "TI",
    "auditor":     "Financeiro",
    "cat-manager": "Suprimentos",
}

# ═══════════════════════════════════════════════════════════════════════════════
# MATH RENDERING (matplotlib mathtext → PNG → reportlab ImageReader)
# ═══════════════════════════════════════════════════════════════════════════════

_math_cache: dict = {}   # (latex, size, colorhex, dpi) -> (bytes, w_pt, h_pt)


def math_img(latex: str, size: int = 12, color=BLACK, dpi: int = 150):
    """Render a LaTeX math expression. Returns (ImageReader, w_pt, h_pt)."""
    # Convert reportlab color to a 6-digit hex string matplotlib understands
    if hasattr(color, "red"):
        r, g, b = int(color.red * 255), int(color.green * 255), int(color.blue * 255)
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
    else:
        hex_color = "#1a1a1a"
    key = (latex, size, hex_color, dpi)

    if key not in _math_cache:
        expr = latex if latex.startswith("$") else f"${latex}$"
        mpl_color = hex_color
        fig = plt.figure(figsize=(0.1, 0.1))
        fig.text(0.5, 0.5, expr, fontsize=size, color=mpl_color,
                 ha="center", va="center")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi,
                    bbox_inches="tight", pad_inches=0.06, transparent=True)
        plt.close(fig)
        raw = buf.getvalue()
        # Measure size in pt (1 pt = 72/dpi px)
        tmp = ImageReader(io.BytesIO(raw))
        w_px, h_px = tmp.getSize()
        w_pt = w_px * 72 / dpi
        h_pt = h_px * 72 / dpi
        _math_cache[key] = (raw, w_pt, h_pt)

    raw, w_pt, h_pt = _math_cache[key]
    return ImageReader(io.BytesIO(raw)), w_pt, h_pt


def math_box(c, x: float, y_top: float, w: float, title: str,
             items: list, title_bg=BLUE, padding: float = 8) -> float:
    """
    Draw a titled box containing formula images and/or text lines.
    items: list of dicts with 'type' in {'math', 'text', 'gap'}.
      math: {'latex': str, 'size': int, 'align': 'left'|'center'}
      text: {'content': str, 'size': float, 'bold': bool, 'code': bool, 'color': color}
      gap:  {'height': float}
    Returns y_bottom.
    """
    TITLE_H = 20
    ITEM_GAP = 5

    # --- pre-render to measure ---
    rendered = []
    total_h = 0.0
    for item in items:
        t = item.get("type", "text")
        if t == "math":
            img, iw, ih = math_img(item["latex"], item.get("size", 12))
            max_w = w - 2 * padding
            scale = min(1.0, max_w / iw) if iw > 0 else 1.0
            rendered.append({**item, "_img": img, "_w": iw * scale, "_h": ih * scale})
            total_h += ih * scale + ITEM_GAP
        elif t == "gap":
            rendered.append(item)
            total_h += item.get("height", 4)
        else:
            sz = item.get("size", 8.5)
            rendered.append({**item, "_h": sz * 1.45})
            total_h += sz * 1.45 + 1

    box_h = TITLE_H + padding + total_h + padding

    # --- draw box ---
    rect(c, x, y_top - box_h, w, box_h, GRAY, stroke_color=LGRAY, lw=0.5, r=4)
    rect(c, x, y_top - TITLE_H, w, TITLE_H, title_bg, r=4)
    txt(c, title, x + padding, y_top - 14, "Helvetica-Bold", 9, WHITE)

    # --- draw items ---
    cy = y_top - TITLE_H - padding
    for item in rendered:
        t = item.get("type", "text")
        if t == "math":
            sh, sw = item["_h"], item["_w"]
            ix = (x + (w - sw) / 2 if item.get("align") == "center"
                  else x + padding)
            c.drawImage(item["_img"], ix, cy - sh, sw, sh, mask="auto")
            cy -= sh + ITEM_GAP
        elif t == "gap":
            cy -= item.get("height", 4)
        else:
            sz = item.get("size", 8.5)
            col = item.get("color", MUTED if item.get("muted") else BLACK)
            fn = ("Helvetica-Bold" if item.get("bold") else
                  "Courier" if item.get("code") else "Helvetica")
            txt(c, item["content"], x + padding, cy - sz, fn, sz, col)
            cy -= item["_h"] + 1

    return y_top - box_h


# ═══════════════════════════════════════════════════════════════════════════════
# PRIMITIVE DRAWING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def poly(c, pts, fill=1, stroke=0):
    p = c.beginPath()
    p.moveTo(*pts[0])
    for xy in pts[1:]:
        p.lineTo(*xy)
    p.close()
    c.drawPath(p, fill=fill, stroke=stroke)


def rect(c, x, y, w, h, fill_color, stroke_color=None, lw=0.5, r=3):
    c.setFillColor(fill_color)
    if stroke_color:
        c.setStrokeColor(stroke_color)
        c.setLineWidth(lw)
        c.roundRect(x, y, w, h, r, fill=1, stroke=1)
    else:
        c.roundRect(x, y, w, h, r, fill=1, stroke=0)


def arrow(c, x1, y1, x2, y2, color=BLUE, lw=1.2, dashed=False, label=""):
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    if dashed:
        c.setDash([5, 3])
    c.line(x1, y1, x2, y2)
    if dashed:
        c.setDash()
    a = _math.atan2(y2 - y1, x2 - x1)
    sz = 6
    p1 = (x2 - sz * _math.cos(a - 0.4), y2 - sz * _math.sin(a - 0.4))
    p2 = (x2 - sz * _math.cos(a + 0.4), y2 - sz * _math.sin(a + 0.4))
    c.setFillColor(color)
    poly(c, [(x2, y2), p1, p2])
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        txt(c, label, mx, my + 4, "Helvetica", 7, MUTED, "center")


def txt(c, text, x, y, font="Helvetica", size=10, color=BLACK, align="left"):
    c.setFont(font, size)
    c.setFillColor(color)
    if align == "center":
        c.drawCentredString(x, y, text)
    elif align == "right":
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)


def para(c, html, x, y_top, width, font="Helvetica", size=9,
         color=BLACK, leading=None, bold=False):
    fn = "Helvetica-Bold" if bold else font
    ld = leading or size * 1.4
    st = ParagraphStyle("_", fontName=fn, fontSize=size, leading=ld, textColor=color)
    p = Paragraph(html, st)
    _, h = p.wrap(width, 5000)
    p.drawOn(c, x, y_top - h)
    return y_top - h


def hline(c, x1, x2, y, color=LGRAY, lw=0.5):
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    c.line(x1, y, x2, y)


def code_block(c, lines, x, y_top, width, size=8):
    ld = size * 1.4
    h = len(lines) * ld + 10
    rect(c, x, y_top - h, width, h, GRAY, stroke_color=LGRAY, lw=0.5)
    c.setFillColor(BLUE)
    c.rect(x, y_top - h, 3, h, fill=1, stroke=0)
    y = y_top - 6
    for line in lines:
        txt(c, line, x + 8, y - size, "Courier", size, BLACK)
        y -= ld
    return y_top - h


def labeled_box(c, x, y, w, h, title, body_lines,
                title_bg=BLUE, body_bg=GRAY, tsz=9, bsz=8.5, key_w=95):
    """Render a titled box with body lines.
    Each line may be a plain string or a (key, value) tuple for two-column layout.
    Tuple keys render bold; values start at x + 7 + key_w.
    """
    th = 18
    rect(c, x, y + h - th, w, th, title_bg, r=3)
    txt(c, title, x + 7, y + h - th + 5, "Helvetica-Bold", tsz, WHITE)
    rect(c, x, y, w, h - th, body_bg, stroke_color=LGRAY, lw=0.5, r=0)
    cy = y + h - th - 10
    for ln in body_lines:
        if isinstance(ln, tuple):
            key, val = ln
            txt(c, key, x + 7,          cy, "Helvetica-Bold", bsz, BLACK)
            txt(c, val, x + 7 + key_w,  cy, "Helvetica",      bsz, MUTED)
        else:
            txt(c, ln, x + 7, cy, "Helvetica", bsz, BLACK)
        cy -= bsz * 1.45
    return x, y, w, h


# ── Slide frame ───────────────────────────────────────────────────────────────

def slide_frame(c, title, section="", page=0):
    c.setFillColor(BLUE)
    c.rect(0, H - HDR_H, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.rect(0, H - HDR_H, 5, HDR_H, fill=1, stroke=0)
    txt(c, title, 16, H - 31, "Helvetica-Bold", 17, WHITE)
    if section:
        txt(c, section, 16, H - HDR_H + 6, "Helvetica", 8, BLUE_LT)
    c.setFillColor(BLUE)
    c.rect(0, 0, W, FTR_H, fill=1, stroke=0)
    txt(c, "Concilium — Mendes Lobo Construção  ·  Uso interno  ·  Confidencial",
        CX, 6, "Helvetica", 7.5, BLUE_LT)
    if page:
        txt(c, str(page), W - CX, 6, "Helvetica", 7.5, BLUE_LT, "right")


# ── User silhouette ───────────────────────────────────────────────────────────

def user_figure(c, cx, cy, sz=36, color=BLUE, label="", sub=""):
    """cy = base (feet). Height ~ sz*1.5."""
    bh = sz * 0.55
    bw = sz * 0.52
    hr = sz * 0.24
    c.setFillColor(color)
    c.roundRect(cx - bw / 2, cy, bw, bh, sz * 0.12, fill=1, stroke=0)
    c.circle(cx, cy + bh + hr * 0.55, hr, fill=1, stroke=0)
    if label:
        txt(c, label, cx, cy - 13, "Helvetica-Bold", 8, BLACK, "center")
    if sub:
        txt(c, sub, cx, cy - 23, "Helvetica", 7, MUTED, "center")


def state_machine(c, x, y, states, node_w=96, node_h=34, gap=34,
                  accent=BLUE, final_color=GREEN, branch=None):
    """Draw a horizontal state machine. y = vertical center of node row.
    states: list of (label, transition_label_to_next | "").
    branch: optional (from_index, label, branch_state_label) drawn below.
    Returns the list of node-center x positions."""
    centers = []
    cx = x
    n = len(states)
    for i, (label, trans) in enumerate(states):
        is_final = (i == n - 1)
        col = final_color if is_final else accent
        rect(c, cx, y - node_h/2, node_w, node_h, col, r=node_h/2)
        # label may have 2 lines
        lines = label.split("\n")
        if len(lines) == 1:
            txt(c, lines[0], cx + node_w/2, y - 3.5, "Helvetica-Bold", 8.5, WHITE, "center")
        else:
            txt(c, lines[0], cx + node_w/2, y + 1, "Helvetica-Bold", 8, WHITE, "center")
            txt(c, lines[1], cx + node_w/2, y - 9, "Helvetica-Bold", 8, WHITE, "center")
        centers.append(cx + node_w/2)
        if i < n - 1:
            arrow(c, cx + node_w, y, cx + node_w + gap, y, MUTED, lw=1.1)
            if trans:
                txt(c, trans, cx + node_w + gap/2, y + 6, "Helvetica", 6.5, MUTED, "center")
        cx += node_w + gap
    if branch:
        fi, blabel, bstate = branch
        bx = centers[fi] - node_w/2
        by = y - node_h/2 - 30
        arrow(c, centers[fi], y - node_h/2, centers[fi], by + node_h/2, MUTED, lw=1.0)
        txt(c, blabel, centers[fi] + 6, y - node_h/2 - 14, "Helvetica", 6.5, MUTED)
        rect(c, bx, by - node_h/2, node_w, node_h, colors.HexColor("#8A93A0"), r=node_h/2)
        txt(c, bstate, centers[fi], by - 3.5, "Helvetica-Bold", 8.5, WHITE, "center")
    return centers


# ═══════════════════════════════════════════════════════════════════════════════
# SLIDES
# ═══════════════════════════════════════════════════════════════════════════════

def s_title(c):
    c.setFillColor(BLUE)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(BLUE2)
    poly(c, [(W*0.58, H), (W*0.9, H), (W, H*0.55), (W, H*0.25)])
    c.setFillColor(ORANGE)
    c.rect(0, 0, W, 8, fill=1, stroke=0)
    txt(c, "Concilium", W/2, H-130, "Helvetica-Bold", 52, WHITE, "center")
    txt(c, "Pipeline  ·  Catálogo  ·  Roles  ·  Workflows",
        W/2, H-175, "Helvetica-Bold", 20, BLUE_LT, "center")
    c.setStrokeColor(ORANGE); c.setLineWidth(2)
    c.line(W*0.28, H-192, W*0.72, H-192)
    txt(c, "MendesLobo Construtora", W/2, H-218, "Helvetica", 14,
        colors.HexColor("#C8DCF0"), "center")
    txt(c, "Engenharia de Software  ·  26 de junho de 2026  ·  Uso interno",
        W/2, H-244, "Helvetica", 10, colors.HexColor("#7A9FBF"), "center")
    txt(c, "1", W-30, 8, "Helvetica", 8, BLUE_LT, "right")


def s_interaction(c):
    slide_frame(c, "Modelo de Interação e Arquitetura", "Arquitetura", 3)

    MAIN_R = 690   # main column right edge; deploy column to the right
    midx = (70 + MAIN_R) / 2   # ~380, center of the main column

    # ── Layer labels (left gutter) ────────────────────────────────────────
    for ly, lbl in [(412,"Usuarios"),(360,"Cliente"),(300,"Endereco"),
                    (210,"Hospedagem (ACA)"),(78,"Dados")]:
        txt(c, lbl, CX-4, ly, "Helvetica-Oblique", 7.5, MUTED)

    # ── Users row ─────────────────────────────────────────────────────────
    user_xs = [140, 250, 360, 470, 580]
    roles = ["operator","engineer","admin","auditor","cat-manager"]
    for rx, role in zip(user_xs, roles):
        user_figure(c, rx, 412, sz=30, color=ROLE_COLORS[role], label=ROLE_PT[role])
        arrow(c, rx, 408, rx, 392, ROLE_COLORS[role], lw=0.9)

    # ── Claude Desktop ────────────────────────────────────────────────────
    rect(c, 120, 354, 480, 36, BLUE, stroke_color=BLUE2, lw=1, r=6)
    txt(c, "Claude Desktop  ·  cliente do usuario", midx, 375, "Helvetica-Bold", 11, WHITE, "center")
    txt(c, "O usuario fala com o agente, nunca direto com o servidor", midx, 361, "Helvetica", 7.5, BLUE_LT, "center")
    arrow(c, midx, 354, midx, 330, MUTED, lw=1.2, label="HTTPS")

    # ── DNS CNAME endpoint ────────────────────────────────────────────────
    rect(c, 175, 292, 370, 34, ORANGE, r=6)
    txt(c, "mcp.mendesloboconstrucao.com.br", midx, 310, "Helvetica-Bold", 10.5, WHITE, "center")
    txt(c, "alias DNS CNAME  ->  porta do serviço no ACA", midx, 297, "Helvetica", 7.5, WHITE, "center")
    arrow(c, midx, 292, midx, 270, MUTED, lw=1.2)

    # ── Azure ACA container (holds MCP + API + Pipeline, same image) ──────
    aca_top, aca_bot = 268, 130
    rect(c, 70, aca_bot, MAIN_R-70, aca_top-aca_bot, DARK, stroke_color=BLUE2, lw=1.2, r=8)
    txt(c, "Azure Container Apps (ACA)  —  MCP e API compartilham a mesma imagem",
        80, aca_top-13, "Helvetica-Bold", 9.5, BLUE_LT)
    # MCP + API boxes
    rect(c, 90, 214, 270, 36, BLUE, r=5)
    txt(c, "Servidor MCP", 225, 234, "Helvetica-Bold", 10.5, WHITE, "center")
    txt(c, "ferramentas por papel", 225, 221, "Helvetica", 7.5, BLUE_LT, "center")
    rect(c, 400, 214, 210, 36, BLUE, r=5)
    txt(c, "API REST", 505, 234, "Helvetica-Bold", 10.5, WHITE, "center")
    txt(c, "integracoes e automacoes", 505, 221, "Helvetica", 7.5, BLUE_LT, "center")
    # Pipeline de skills — consumed by BOTH MCP and API
    rect(c, 90, 144, 520, 40, GREEN, r=5)
    txt(c, "Pipeline de Skills  —  orquestra o orcamento", 350, 168, "Helvetica-Bold", 10, WHITE, "center")
    txt(c, "consumida tanto pelo Servidor MCP quanto pela API REST", 350, 155, "Helvetica", 7.5, WHITE, "center")
    arrow(c, 225, 214, 225, 184, LGRAY, lw=1.0)   # MCP -> pipeline
    arrow(c, 505, 214, 505, 184, LGRAY, lw=1.0)   # API -> pipeline

    # ── SharePoint blob storage wrapping the data layer ───────────────────
    sp_top, sp_bot = 116, 44
    rect(c, 70, sp_bot, MAIN_R-70, sp_top-sp_bot, colors.HexColor("#13304C"),
         stroke_color=GREEN, lw=1.2, r=8)
    txt(c, "Armazenamento SharePoint (blob)  —  envolve catálogo, projetos e artefatos",
        80, sp_top-13, "Helvetica-Bold", 8.5, colors.HexColor("#9FD9B4"))
    for ax, title, sub, acol in [
        (90,  "Catálogo",   "insumos · composições", ORANGE),
        (290, "Projetos",   "planos · versões",       colors.HexColor("#8FA8DA")),
        (470, "Artefatos",  "relatórios · pacotes",   colors.HexColor("#B79CD8")),
    ]:
        bw, bh = 140, 34
        rect(c, ax, 52, bw, bh, GRAY, stroke_color=acol, lw=1.0, r=4)
        txt(c, title, ax+bw/2, 52+bh-14, "Helvetica-Bold", 9, acol, "center")
        txt(c, sub, ax+bw/2, 52+bh-26, "Helvetica", 7, MUTED, "center")
    # pipeline <-> data (consome / popula), bidirectional
    arrow(c, 340, 144, 340, 120, GREEN, lw=1.1)
    arrow(c, 380, 116, 380, 140, GREEN, lw=1.1)
    txt(c, "le e grava", 412, 128, "Helvetica", 6.5, MUTED)

    # ── Deploy column (gh-action) on the right ────────────────────────────
    dx = MAIN_R + 20
    dw = W - CX - dx
    rect(c, dx, 60, dw, 380, colors.HexColor("#10243A"), stroke_color=ORANGE, lw=1, r=8)
    txt(c, "Entrega Continua", dx+dw/2, 418, "Helvetica-Bold", 10, ORANGE, "center")
    txt(c, "(GitHub Actions)", dx+dw/2, 406, "Helvetica", 8, BLUE_LT, "center")
    dsteps = [
        ("Build da imagem\n(MCP + API)",        BLUE),
        ("Publica no\nregistro de container",   BLUE),
        ("Nova revisão\nno ACA",                BLUE),
        ("Teste smoke\nautomatico",             ORANGE),
        ("Promove trafego\nse o smoke passar",  GREEN),
    ]
    dy = 388
    for i, (step, col) in enumerate(dsteps):
        bh = 42
        rect(c, dx+12, dy-bh, dw-24, bh, col, r=5)
        lines = step.split("\n")
        txt(c, lines[0], dx+dw/2, dy-16, "Helvetica-Bold", 8, WHITE, "center")
        txt(c, lines[1], dx+dw/2, dy-28, "Helvetica", 7, BLUE_LT if col != GREEN else WHITE, "center")
        if i < len(dsteps)-1:
            arrow(c, dx+dw/2, dy-bh, dx+dw/2, dy-bh-12, BLUE_LT, lw=0.9)
        dy -= bh + 12
    txt(c, "Smoke falhou: nada muda;", dx+dw/2, dy+2, "Helvetica-Oblique", 6.8, MUTED, "center")
    txt(c, "revisão atual segue ativa.", dx+dw/2, dy-7, "Helvetica-Oblique", 6.8, MUTED, "center")
    # arrow from deploy into ACA (atualiza a camada de hospedagem)
    arrow(c, dx, 199, MAIN_R, 199, ORANGE, lw=1.2, dashed=True, label="atualiza")


def s_pipeline(c):
    slide_frame(c, "Pipeline de Planejamento: Etapas e Entregaveis", "Pipeline", 5)

    # ── Monitoring band (right), full height ──────────────────────────────
    mx = W - 100
    rect(c, mx, CB+4, 88, CH-8, DARK, r=6)
    txt(c, "Monitoramento", mx+44, CT-34, "Helvetica-Bold", 8.5, BLUE_LT, "center")
    txt(c, "fim a fim", mx+44, CT-45, "Helvetica-Oblique", 7.5, BLUE_LT, "center")
    monitor = ["Saude do\nsistema","Status dos\njobs","Tracos e\nlogs",
               "Notificacao\npor email","Testes\nsmoke"]
    my = CT-62
    for m in monitor:
        lines = m.split("\n")
        h = 30
        c.setFillColor(colors.HexColor("#1E5080"))
        c.roundRect(mx+6, my-h, 76, h, 3, fill=1, stroke=0)
        txt(c, lines[0], mx+44, my-13, "Helvetica", 7.5, BLUE_LT, "center")
        txt(c, lines[1], mx+44, my-23, "Helvetica", 7.5, BLUE_LT, "center")
        my -= h + 12

    # ── Vertical pipeline: 8 skills ativas (08, 09, 11 dormentes/explicitas) ─
    PURPLE = colors.HexColor("#6A4C93")
    skills = [
        ("01", "Escopo e EAP",           ["EAP e atividades", "Precedencias (DAG)"],    BLUE),
        ("02", "Produtividade Climatica", ["Praticabilidade mensal", "Janela climatica"], BLUE),
        ("03", "Catálogo de Recursos",   ["Tipos de recurso", "Pool inicial"],           BLUE),
        ("04", "Cronograma",             ["Cronograma semanal", "Caminho critico"],      ORANGE),
        ("05", "Equipes e Alocacao",     ["Custo por equipe", "Pool consolidado"],       ORANGE),
        ("06", "Resultado Financeiro",   ["Precificacao e BDI", "Custo total e margem"], ORANGE),
        ("07", "Diagnostico Criticidade",["Prazo, Custo e Recurso", "Sensibilidade"],    PURPLE),
        ("10", "Relatório e Artefatos",  ["Excel auditavel", "Insights executivos"],     GREEN),
    ]
    box_x = CX
    box_w = 232
    chip_x = box_x + box_w + 18
    chip_w = 185
    chip_gap = 14
    rh = 42
    gap = 9
    top_y = CT - 26
    for i, (num, name, delivs, col) in enumerate(skills):
        by = top_y - i*(rh+gap)
        # skill box: number + name
        rect(c, box_x, by-rh, box_w, rh, col, r=6)
        rect(c, box_x, by-rh, 42, rh, BLUE2 if col == BLUE else col, r=6)
        txt(c, num, box_x+21, by-rh/2-6, "Helvetica-Bold", 16, WHITE, "center")
        txt(c, name, box_x+54, by-rh/2-3, "Helvetica-Bold", 11, WHITE)
        # deliverable chips (side by side)
        cy = by - rh + (rh-22)/2
        for k, d in enumerate(delivs):
            cxp = chip_x + k*(chip_w+chip_gap)
            c.setFillColor(GRAY); c.setStrokeColor(LGRAY); c.setLineWidth(0.5)
            c.roundRect(cxp, cy, chip_w, 22, 3, fill=1, stroke=1)
            txt(c, d, cxp+chip_w/2, cy+7, "Helvetica", 8, BLUE, "center")
        # arrow to next skill
        if i < len(skills)-1:
            arrow(c, box_x+box_w/2, by-rh, box_x+box_w/2, by-rh-gap, MUTED, lw=1.1)

    # entregavel label header over the chip column
    txt(c, "Entregaveis de cada etapa", chip_x, top_y+4, "Helvetica-Bold", 8, MUTED)
    txt(c, "Cada etapa recebe o resultado da anterior; tudo e congelado e versionado a cada execução.",
        chip_x, CB+12, "Helvetica-Oblique", 8, MUTED)


# ── SLIDE 6: Modelagem do Cronograma ──────────────────────────────────────────

def s_cronograma(c):  # noqa: C901
    slide_frame(c, "Modelagem do Cronograma: Envelope e Precedencias", "Regras de Negocio", 6)

    TEAL    = colors.HexColor("#0D7A7A")
    ENV_BG  = colors.HexColor("#E4EDF5")
    ENV_BD  = colors.HexColor("#90AECC")
    MOB_C   = colors.HexColor("#F5A623")
    DEM_C   = colors.HexColor("#888EA8")
    PRAT_HI = colors.HexColor("#2D8C4E")   # λ ≥ 90%
    PRAT_MD = colors.HexColor("#C87820")   # 75% ≤ λ < 90%
    PRAT_LO = colors.HexColor("#B42323")   # λ < 75%

    # ── Grid parameters ───────────────────────────────────────────────────────
    act_w   = 130
    n_wks   = 10
    cw      = 42
    rh      = 64
    hh      = 34    # semana label (20pt) + praticabilidade (14pt)
    row_gap = 8
    mat_x   = CX
    mat_w   = act_w + n_wks * cw    # 130 + 420 = 550
    def_x   = mat_x + mat_w + 22
    def_w   = CW - mat_w - 22       # 308
    top_y   = CT - 20

    # λ_j: praticabilidade climatica por semana (%)
    practicab = [92, 88, 75, 70, 85, 95, 90, 88, 82, 78]
    wlabels   = [f"S{i}" for i in range(1, n_wks + 1)]

    def _fmt_q(val, unit):
        """Format weekly quantity for display inside a schedule cell."""
        if unit == "ev":
            return ""
        if val >= 1000:
            return f"{val / 1000:.1f}k {unit}"
        if val >= 10:
            return f"{val:.0f} {unit}"
        return f"{val:.1f} {unit}"

    # Envelope t_i^min = t_A^min + ceil(alpha * D_A)  (prec. parcial)
    #          t_i^min = t_A^max + 1                 (prec. completa)
    # alpha: fracao da DURACAO de A (não do ac.% de equipes)
    #
    #   Mob  S1     complete  → Terr S2   (t = 1+1 = 2)
    #   Terr S2-S5  parcial 50% → Fund S4  (t = 2+ceil(0.5·4) = 4)
    #   Fund S4-S6  complete  → Estr S7   (t = 6+1 = 7)
    #   Estr S7-S10 parcial 50% → Inst S9  (t = 7+ceil(0.5·4) = 9)
    #
    # (label, color, envelope, sched, m_ij[], Q_tot_str, unit, prec, q_num)
    # Mobilização omitida: não e atividade produtiva; envelope de Terr inicia em S2
    # pois mobilização precede e consome a semana 1 (restrição implicita).
    acts = [
        ("Terraplenagem", BLUE2,  (2, 6),  (2, 5),  [1, 3, 3, 2], "4.0k","m³",  ("partial", 0.50), 4000),
        ("Fundacao",      BLUE,   (4, 8),  (4, 6),  [1, 2, 2],    "150", "m³",  "full",             150),
        ("Estrutura",     TEAL,   (7, 10), (7, 10), [1, 2, 2, 1], "38",  "t",   ("partial", 0.50),   38),
        ("Instalações",   GREEN,  (9, 10), (9, 10), [1, 1],        "140", "m",   None,               140),
    ]

    def _prat_color(lam):
        if lam >= 90: return PRAT_HI
        if lam >= 75: return PRAT_MD
        return PRAT_LO

    # ── Header: semana label + praticabilidade ────────────────────────────────
    hy = top_y
    rect(c, mat_x, hy - hh, act_w - 1, hh, DARK, r=3)
    txt(c, "Atividade", mat_x + act_w / 2, hy - 12, "Helvetica-Bold", 7.5, WHITE, "center")
    txt(c, "Q total / unid.", mat_x + act_w / 2, hy - hh + 7,
        "Helvetica", 6.5, BLUE_LT, "center")
    for wi, (wl, lam) in enumerate(zip(wlabels, practicab)):
        wx = mat_x + act_w + wi * cw
        rect(c, wx + 1, hy - hh, cw - 2, hh, DARK, r=2)
        txt(c, wl, wx + cw / 2, hy - 12, "Helvetica-Bold", 8, BLUE_LT, "center")
        txt(c, f"λ={lam}%", wx + cw / 2, hy - hh + 7,
            "Helvetica-Bold", 6.5, _prat_color(lam), "center")

    # ── Activity rows ────────────────────────────────────────────────────────
    row_tops = []
    for ai, (name, col, env, sched, neq, qtot, unit, prec, q_num) in enumerate(acts):
        ry = top_y - hh - ai * (rh + row_gap)
        row_tops.append(ry)
        total_eq = sum(neq)

        # Activity name + Q total
        rect(c, mat_x, ry - rh, act_w - 1, rh, GRAY, stroke_color=LGRAY, lw=0.5, r=3)
        c.setFillColor(col)
        c.circle(mat_x + 9, ry - rh / 2 + 6, 5, fill=1, stroke=0)
        txt(c, name,                mat_x + 20, ry - rh / 2 + 3,  "Helvetica-Bold", 8.5, DARK)
        txt(c, f"Q={qtot} {unit}",  mat_x + 20, ry - rh / 2 - 10, "Helvetica",      7,   MUTED)

        # Faint gridlines
        for wi in range(n_wks + 1):
            gx = mat_x + act_w + wi * cw
            c.setStrokeColor(LGRAY); c.setLineWidth(0.25)
            c.line(gx, ry, gx, ry - rh)

        # Envelope band
        ex = mat_x + act_w + (env[0] - 1) * cw + 1
        ew = (env[1] - env[0] + 1) * cw - 2
        c.setFillColor(ENV_BG); c.setStrokeColor(ENV_BD); c.setLineWidth(0.7)
        c.roundRect(ex, ry - rh + 3, ew, rh - 6, 3, fill=1, stroke=1)

        # Scheduled cells
        n_sched = sched[1] - sched[0] + 1
        for k in range(n_sched):
            si     = sched[0] - 1 + k
            cx_c   = mat_x + act_w + si * cw + 2
            cy_c   = ry - rh + 4
            cw_c   = cw - 4
            ch_c   = rh - 8
            rect(c, cx_c, cy_c, cw_c, ch_c, col, r=3)

            n      = neq[k] if k < len(neq) else neq[-1]
            cum_n  = sum(neq[:k + 1])
            pct    = int(round(cum_n / total_eq * 100))

            # Ramp indicator triangle (left side of cell)
            prev_n = 0 if k == 0 else (neq[k - 1] if k - 1 < len(neq) else neq[-1])
            next_n = 0 if k == n_sched - 1 else (neq[k + 1] if k + 1 < len(neq) else neq[-1])
            if n > prev_n:   # ramp up
                tx = cx_c + 4; ty = cy_c + ch_c - 10
                c.setFillColor(colors.HexColor("#A8E6C0"))
                poly(c, [(tx, ty + 8), (tx + 5, ty), (tx - 5, ty)])
            elif n < next_n or (k == n_sched - 1 and n < (neq[k-1] if k > 0 else n)):
                # ramp down (includes last cell if it's lower)
                tx = cx_c + 4; ty = cy_c + ch_c - 8
                c.setFillColor(colors.HexColor("#F4A0A0"))
                poly(c, [(tx, ty), (tx + 5, ty + 8), (tx - 5, ty + 8)])

            # m_ij label (top)
            txt(c, f"{n}m", cx_c + cw_c / 2, cy_c + ch_c - 16,
                "Helvetica-Bold", 9, WHITE, "center")
            # Weekly quantity (middle)
            q_wk = neq[k] / total_eq * q_num
            q_str = _fmt_q(q_wk, unit)
            if q_str:
                txt(c, q_str, cx_c + cw_c / 2, cy_c + 26,
                    "Helvetica", 7, colors.HexColor("#FFE8C0"), "center")
            # Cumulative % label (bottom)
            txt(c, f"ac.{pct}%", cx_c + cw_c / 2, cy_c + 9,
                "Helvetica", 7, colors.HexColor("#D8EEE8"), "center")

            # [M] badge: top-right, first cell
            if k == 0:
                bx = cx_c + cw_c - 11; by = cy_c + ch_c - 11
                c.setFillColor(MOB_C)
                c.roundRect(bx, by, 10, 10, 2, fill=1, stroke=0)
                txt(c, "M", bx + 5, by + 2, "Helvetica-Bold", 6, WHITE, "center")
            # [D] badge: bottom-right, last cell
            if k == n_sched - 1:
                bx = cx_c + cw_c - 11; by = cy_c + 1
                c.setFillColor(DEM_C)
                c.roundRect(bx, by, 10, 10, 2, fill=1, stroke=0)
                txt(c, "D", bx + 5, by + 2, "Helvetica-Bold", 6, WHITE, "center")

    # ── Precedence arrows in row gaps ─────────────────────────────────────────
    for ai, (name, col, env, sched, neq, qtot, unit, prec, q_num) in enumerate(acts):
        if prec is None or ai >= len(acts) - 1:
            continue
        gap_top = row_tops[ai] - rh
        gap_bot = row_tops[ai + 1]
        mid_y   = (gap_top + gap_bot) / 2

        if prec == "full":
            ax = mat_x + act_w + sched[1] * cw - cw / 2
            arrow(c, ax, gap_top, ax, gap_bot, MUTED, lw=1.0)
            txt(c, "proxima semana", ax + 4, mid_y - 2, "Helvetica-Oblique", 6, MUTED)
        else:
            alpha      = prec[1]
            dur        = sched[1] - sched[0] + 1
            trigger_wk = sched[0] - 1 + _math.ceil(alpha * dur)
            ax         = mat_x + act_w + trigger_wk * cw - cw / 2
            next_s     = acts[ai + 1][3][0]
            dx         = mat_x + act_w + (next_s - 1) * cw + cw / 2
            c.setStrokeColor(ORANGE); c.setLineWidth(0.9); c.setDash([4, 2])
            p = c.beginPath()
            p.moveTo(ax, gap_top); p.lineTo(ax, mid_y); p.lineTo(dx, gap_bot)
            c.drawPath(p, fill=0, stroke=1)
            c.setDash()
            ang = _math.atan2(gap_bot - mid_y, dx - ax); sz = 5
            c.setFillColor(ORANGE)
            poly(c, [(dx, gap_bot),
                     (dx - sz * _math.cos(ang - 0.4), gap_bot - sz * _math.sin(ang - 0.4)),
                     (dx - sz * _math.cos(ang + 0.4), gap_bot - sz * _math.sin(ang + 0.4))])
            lx = min(ax, dx) + abs(dx - ax) * 0.25
            txt(c, f"α={int(alpha*100)}% → prox. sem.", lx, mid_y - 2,
                "Helvetica-Oblique", 6, ORANGE)

    # ── Legend ────────────────────────────────────────────────────────────────
    ly = CB + 18
    # Envelope
    c.setFillColor(ENV_BG); c.setStrokeColor(ENV_BD); c.setLineWidth(0.6)
    c.roundRect(mat_x, ly - 8, 20, 12, 2, fill=1, stroke=1)
    txt(c, "Envelope", mat_x + 26, ly - 1, "Helvetica", 7, MUTED)
    # Execução
    rect(c, mat_x + 82, ly - 8, 20, 12, BLUE2, r=2)
    txt(c, "Execução", mat_x + 108, ly - 1, "Helvetica", 7, MUTED)
    # m_ij / %
    txt(c, "m / %", mat_x + 155, ly - 1, "Helvetica", 7, MUTED)
    # M/D badges
    c.setFillColor(MOB_C); c.roundRect(mat_x+210, ly-7, 9, 9, 1, fill=1, stroke=0)
    txt(c, "M mob.",  mat_x + 223, ly - 1, "Helvetica", 7, MUTED)
    c.setFillColor(DEM_C); c.roundRect(mat_x+268, ly-7, 9, 9, 1, fill=1, stroke=0)
    txt(c, "D desm.", mat_x + 281, ly - 1, "Helvetica", 7, MUTED)
    # Prec arrows
    arrow(c, mat_x + 332, ly - 2, mat_x + 352, ly - 2, MUTED, lw=1.0)
    txt(c, "prec. completa", mat_x + 356, ly - 1, "Helvetica-Oblique", 7, MUTED)
    c.setStrokeColor(ORANGE); c.setLineWidth(0.8); c.setDash([4, 2])
    c.line(mat_x + 450, ly - 2, mat_x + 470, ly - 2); c.setDash()
    c.setFillColor(ORANGE)
    poly(c, [(mat_x+470,ly-2),(mat_x+464,ly-5),(mat_x+464,ly+1)])
    txt(c, "prec. parcial", mat_x + 474, ly - 1, "Helvetica-Oblique", 7, ORANGE)
    # Praticabilidade colors
    txt(c, "λ:", mat_x + 545, ly - 1, "Helvetica", 7, MUTED)
    c.setFillColor(PRAT_HI); c.circle(mat_x+562, ly-3, 4, fill=1, stroke=0)
    txt(c, "≥90%", mat_x + 568, ly - 1, "Helvetica", 6.5, PRAT_HI)
    c.setFillColor(PRAT_MD); c.circle(mat_x+600, ly-3, 4, fill=1, stroke=0)
    txt(c, "75-89%", mat_x + 606, ly - 1, "Helvetica", 6.5, PRAT_MD)
    c.setFillColor(PRAT_LO); c.circle(mat_x+642, ly-3, 4, fill=1, stroke=0)
    txt(c, "<75%", mat_x + 648, ly - 1, "Helvetica", 6.5, PRAT_LO)

    # ── Right panel: model definitions ───────────────────────────────────────
    y_r = CT - 20

    y_r = math_box(c, def_x, y_r, def_w, "Envelope e equipes", [
        {"type": "math",
         "latex": r"m_{ij} \geq 0 \;\;\text{(equipes na semana } j\text{)}",
         "size": 10, "align": "center"},
        {"type": "math",
         "latex": r"m_{ij} = 0 \;\;\forall\; j \notin [t_i^{\min},\, t_i^{\max}]",
         "size": 10, "align": "center"},
    ])
    y_r -= 6

    y_r = math_box(c, def_x, y_r, def_w, "Precedencia — proxima semana", [
        {"type": "math",
         "latex": r"\bullet\;\text{completa: } t_B^{\min} = t_A^{\max} + 1",
         "size": 10, "align": "left"},
        {"type": "math",
         "latex": r"\bullet\;\text{parcial: } t_B^{\min} = t_A^{\min} + \lceil \alpha_{AB} \cdot D_A \rceil",
         "size": 10, "align": "left"},
        {"type": "math",
         "latex": r"D_A = t_A^{\max} - t_A^{\min} + 1 \;\; \alpha_{AB}\text{: fracao da duracao}",
         "size": 8, "align": "left"},
    ])
    y_r -= 6

    y_r = math_box(c, def_x, y_r, def_w, "Quantitativo e Mob/Demob", [
        {"type": "math",
         "latex": r"q_{ij} = m_{ij} \cdot \rho_i \cdot h_j \cdot \lambda_j",
         "size": 10, "align": "center"},
        {"type": "math",
         "latex": r"\mathrm{ac.}_j = \frac{\sum_{k \leq j} m_{ik}}{\sum_k m_{ik}}",
         "size": 10, "align": "center"},
        {"type": "gap", "height": 3},
        {"type": "text", "content": "[M]/[D] = inicio/fim de cadeia de slots", "bold": True},
        {"type": "math",
         "latex": r"n_{ev} = |\text{cadeias}| \leq |\text{atividades}|",
         "size": 9, "align": "left"},
    ])
    y_r -= 6

    math_box(c, def_x, y_r, def_w, "Otimização: RCPSP", [
        {"type": "math",
         "latex": r"\min\,\text{prazo} \;\;\text{s.a.}\;\; \alpha_{AB},\; S_r(t),\; \lambda_j",
         "size": 10, "align": "center"},
        {"type": "text",
         "content": "Resource-Constrained Project Scheduling Problem", "bold": True},
        {"type": "text",
         "content": "N cenários what-if: frentes, jornada, tamanho do pool"},
    ], title_bg=colors.HexColor("#0D5A3A"))


# ── SLIDE 7: Pool de Recursos — Reaproveitamento ───────────────────────────────

def s_pool_reuso(c):
    slide_frame(c, "Pool de Recursos: Reaproveitamento de Equipes", "Regras de Negocio", 7)

    TEAL   = colors.HexColor("#0D7A7A")
    MOB_C  = colors.HexColor("#F5A623")
    DEM_C  = colors.HexColor("#888EA8")
    POOL_C = colors.HexColor("#1A3A6A")
    NEG_C  = colors.HexColor("#B42323")
    POS_C  = colors.HexColor("#277848")

    def_x = 630
    def_w = CX + CW - def_x    # 290

    # ── Flow diagram ──────────────────────────────────────────────────────────
    act_w  = 120
    bw     = 28    # badge circle diameter
    pw     = 120   # pool box width
    ph     = 80    # pool box height
    gap    = 26

    x0 = CX                          # Activity A left
    x1 = x0 + act_w + gap            # D badge left edge
    x2 = x1 + bw + gap               # pool box left
    x3 = x2 + pw + gap               # M badge left edge
    x4 = x3 + bw + gap               # Activity B left

    arrow_y = CT - 64                # 428 — vertical center of flow
    act_h   = 64
    act_bot = arrow_y - act_h // 2   # 396
    pool_bot = arrow_y - ph // 2     # 388
    pool_top = arrow_y + ph // 2     # 468

    # Activity A
    rect(c, x0, act_bot, act_w, act_h, BLUE2, r=6)
    txt(c, "Atividade", x0+act_w/2, act_bot+act_h-18, "Helvetica-Bold", 9, WHITE, "center")
    txt(c, "em execução", x0+act_w/2, act_bot+act_h-30, "Helvetica", 8, BLUE_LT, "center")
    txt(c, "(Proj. A, B...)", x0+act_w/2, act_bot+10, "Helvetica-Oblique", 7, BLUE_LT, "center")

    arrow(c, x0+act_w, arrow_y, x1, arrow_y, MUTED, lw=1.2)

    # [D] badge
    bc_d = x1 + bw/2
    c.setFillColor(DEM_C)
    c.circle(bc_d, arrow_y, 14, fill=1, stroke=0)
    txt(c, "D", bc_d, arrow_y-4, "Helvetica-Bold", 11, WHITE, "center")
    txt(c, "desmob.", bc_d, arrow_y-22, "Helvetica", 6.5, DEM_C, "center")

    arrow(c, x1+bw, arrow_y, x2, arrow_y, MUTED, lw=1.2)

    # Pool box
    rect(c, x2, pool_bot, pw, ph, POOL_C, r=8)
    txt(c, "Pool de Slots", x2+pw/2, pool_top-14, "Helvetica-Bold", 9.5, WHITE, "center")
    SLOT_COLORS = [colors.HexColor("#E07B20"), colors.HexColor("#E07B20"),
                   colors.HexColor("#2A7AB5"), colors.HexColor("#2A7AB5")]
    SLOT_LABELS = ["ESC", "ESC", "OP", "OP"]
    for ti in range(4):
        tcx = x2 + 14 + ti * 24
        c.setFillColor(SLOT_COLORS[ti])
        c.circle(tcx, arrow_y, 9, fill=1, stroke=0)
        txt(c, SLOT_LABELS[ti], tcx, arrow_y-3, "Helvetica-Bold", 5.5, WHITE, "center")
    txt(c, "slots por tipo_id", x2+pw/2, pool_bot+8, "Helvetica", 7, BLUE_LT, "center")

    arrow(c, x2+pw, arrow_y, x3, arrow_y, MUTED, lw=1.2)

    # [M] badge
    bc_m = x3 + bw/2
    c.setFillColor(MOB_C)
    c.circle(bc_m, arrow_y, 14, fill=1, stroke=0)
    txt(c, "M", bc_m, arrow_y-4, "Helvetica-Bold", 11, WHITE, "center")
    txt(c, "mob.", bc_m, arrow_y-22, "Helvetica-Bold", 6.5, POS_C, "center")

    arrow(c, x3+bw, arrow_y, x4, arrow_y, MUTED, lw=1.2)

    # Activity B
    rect(c, x4, act_bot, act_w, act_h, TEAL, r=6)
    txt(c, "Proxima", x4+act_w/2, act_bot+act_h-18, "Helvetica-Bold", 9, WHITE, "center")
    txt(c, "atividade", x4+act_w/2, act_bot+act_h-30, "Helvetica", 8,
        colors.HexColor("#90CCCC"), "center")
    txt(c, "(mesmo ou outro proj.)", x4+act_w/2, act_bot+10, "Helvetica-Oblique", 7,
        colors.HexColor("#90CCCC"), "center")

    # Pool perpetuo note
    c.setStrokeColor(TEAL); c.setLineWidth(0.8); c.setDash([3, 2])
    c.line(x2+pw/2, pool_bot, x2+pw/2, pool_bot-14)
    c.setDash()
    txt(c, "Perpetuo — persiste entre atividades e projetos",
        x2+pw/2, pool_bot-26, "Helvetica-Oblique", 8, TEAL, "center")

    # ── Comparison: sem pool vs com pool ──────────────────────────────────────
    comp_top = pool_bot - 50    # 338
    comp_h   = 120
    col_gap  = 16
    col_mar  = 14               # gap between second card and right panel
    col_w    = (def_x - CX - col_gap - col_mar) / 2    # 560/2 = 280
    col1_x   = CX
    col2_x   = CX + col_w + col_gap

    # ── Sem pool ─────────────────────────────────────────────────────────────
    rect(c, col1_x, comp_top-comp_h, col_w, comp_h, GRAY, stroke_color=NEG_C, lw=0.8, r=5)
    rect(c, col1_x, comp_top-20, col_w, 20, NEG_C, r=5)
    txt(c, "Sem pool — contratação direta", col1_x+col_w/2, comp_top-13,
        "Helvetica-Bold", 8.5, WHITE, "center")
    items1 = [
        ("slots dispensados: novo contrato por atividade",  NEG_C),
        ("1 mob + 1 demob por atividade por tipo_id",       NEG_C),
        ("c_mob > 0 em cada inicio de atividade",           NEG_C),
        ("perda de know-how e reaprendizado",                MUTED),
    ]
    iy1 = comp_top - 36
    for ln, col in items1:
        txt(c, f"• {ln}", col1_x+12, iy1, "Helvetica", 7.5, col)
        iy1 -= 15

    # ── Com pool ─────────────────────────────────────────────────────────────
    rect(c, col2_x, comp_top-comp_h, col_w, comp_h, GRAY, stroke_color=POS_C, lw=0.8, r=5)
    rect(c, col2_x, comp_top-20, col_w, 20, POS_C, r=5)
    txt(c, "Com pool perpetuo — reaproveitamento", col2_x+col_w/2, comp_top-13,
        "Helvetica-Bold", 8.5, WHITE, "center")
    items2 = [
        ("slots retornam ao pool via [D]: reutilizaveis",   POS_C),
        ("1 mob + 1 demob por cadeia (varias atividades)",  POS_C),
        ("c_mob = 0 ao consumir slot ja no pool",           POS_C),
        ("know-how e curva de aprendizado preservados",      MUTED),
    ]
    iy2 = comp_top - 36
    for ln, col in items2:
        txt(c, f"• {ln}", col2_x+12, iy2, "Helvetica", 7.5, col)
        iy2 -= 15

    # ── Right panel: definitions ──────────────────────────────────────────────
    WARN_C = colors.HexColor("#7B5EA7")   # roxo para nota de implementacao
    y_r = CT - 24

    y_r = math_box(c, def_x, y_r, def_w, "Pool de slots instanciais", [
        {"type": "math",
         "latex": r"S_r(t)\text{: slots do tipo\_id }r\text{ disponíveis}",
         "size": 9, "align": "center"},
        {"type": "math",
         "latex": r"S_r += n_r \cdot m_i \;\;\text{[D] desm. de }i",
         "size": 9, "align": "center"},
        {"type": "math",
         "latex": r"S_r -= n_r \cdot m_j \;\;\text{[M] mob. de }j",
         "size": 9, "align": "center"},
        {"type": "text", "content": "n_r: qtd do tipo r por equipe-padrão e_i"},
    ], title_bg=POOL_C)
    y_r -= 6

    y_r = math_box(c, def_x, y_r, def_w, "Restricao de subconjunto", [
        {"type": "text", "content": "Slots só entram via desmobilização:", "bold": True},
        {"type": "math",
         "latex": r"\mathcal{P}(t) \subseteq \biguplus_{i \in \mathcal{A}} \mathcal{E}_i",
         "size": 12, "align": "center"},
        {"type": "math",
         "latex": r"\mathcal{E}_i\text{: slots por tipo\_id de atividade }i",
         "size": 9, "align": "left"},
        {"type": "text", "content": "Nenhum slot e criado fora de uma cadeia."},
    ])
    y_r -= 6

    y_r = math_box(c, def_x, y_r, def_w, "Cadeias de perpetuacao", [
        {"type": "math",
         "latex": r"n_{\rm ev} = |\text{cadeias}| \leq |\text{atividades}|",
         "size": 10, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "text", "content": "1 cadeia = atividades consecutivas do mesmo tipo"},
        {"type": "text", "content": "1 mob + 1 demob por cadeia (não por atividade)"},
        {"type": "text", "content": "c_mob = 0 ao reutilizar slot ativo da cadeia"},
    ], title_bg=POS_C)
    y_r -= 6

    math_box(c, def_x, y_r, def_w, "Skill 05 — em tempo de planejamento", [
        {"type": "text", "content": "Contratos dimensionados ao peak demand:"},
        {"type": "math",
         "latex": r"q_c = \min(\max_j m_{ij},\; \text{pool\_cap})",
         "size": 9, "align": "center"},
        {"type": "text", "content": "Slots 1..q_c alocados por InstanciaRecurso"},
        {"type": "text", "content": "Demob rastreada (early-demob ADR-079/080)"},
        {"type": "text",
         "content": "Re-planejamento via skill 05 para novas atividades",
         "color": MUTED},
    ], title_bg=BLUE2)



# ── SLIDE 8: Pool — Ciclo de Vida dos Slots ao Longo das Atividades ───────────

def s_pool_timeline(c):
    slide_frame(c, "Pool: Ciclo de Vida dos Slots ao Longo das Atividades",
                "Regras de Negocio", 9)

    TEAL    = colors.HexColor("#0D7A7A")
    MOB_C   = colors.HexColor("#F5A623")    # mobilização inicial (c_mob cobrado)
    REUSE_C = colors.HexColor("#277848")    # mob do pool (c_mob = 0)
    DEM_C   = colors.HexColor("#888EA8")
    POOL_BG = colors.HexColor("#1A3A6A")
    STAN_C  = colors.HexColor("#7B5EA7")
    NEG_C   = colors.HexColor("#B42323")
    POS_C   = colors.HexColor("#277848")
    ACT_C   = colors.HexColor("#1A4A7A")    # activity bar blue

    # ── Timeline geometry ────────────────────────────────────────────────────
    LBL_W  = 72     # left label column
    tl_x   = CX + LBL_W     # 112
    tl_w   = CX + CW - tl_x # 808
    N_WKS  = 12
    wk     = tl_w / N_WKS   # ~67.3 px per week

    def wx(week):   return tl_x + (week - 1) * wk   # left edge of week
    def wm(week):   return wx(week) + wk / 2         # mid of week

    # Activities: (label_line1, label_line2, start_wk, end_wk, color)
    acts_pool = [
        ("Pavim. A", "Proj. Alfa", 1,  4,  ACT_C),
        ("Pavim. B", "Proj. Alfa", 6,  8,  ACT_C),
        ("Pavim. C", "Proj. Beta", 10, 12, TEAL),
    ]
    gaps_pool = [(5, 5), (9, 9)]   # standby weeks

    # ── Section header ───────────────────────────────────────────────────────
    top_y = CT - 4     # 488
    rect(c, CX, top_y - 18, CW, 18, POS_C, r=3)
    txt(c, "Com pool perpetuo — Cadeia 1  (tipo: ESCAVADEIRA — ESC)",
        CX + CW / 2, top_y - 9, "Helvetica-Bold", 8.5, WHITE, "center")

    # ── Week header ──────────────────────────────────────────────────────────
    wk_top = top_y - 18   # 470
    wk_h   = 18
    wk_bot = wk_top - wk_h   # 452
    for w in range(1, N_WKS + 1):
        x0 = wx(w)
        c.setFillColor(DARK)
        c.rect(x0 + 0.5, wk_bot, wk - 1, wk_h, fill=1, stroke=0)
        txt(c, f"S{w}", x0 + wk / 2, wk_bot + 4, "Helvetica", 7, BLUE_LT, "center")

    # ── Activity bars (com pool) ──────────────────────────────────────────────
    ACT_H  = 46
    act_top = wk_bot - 3   # 449
    act_bot = act_top - ACT_H   # 403

    for idx, (l1, l2, s, e, col) in enumerate(acts_pool):
        ax = wx(s) + 1
        aw = (e - s + 1) * wk - 2
        ay = act_bot
        rect(c, ax, ay, aw, ACT_H, col, r=5)
        txt(c, l1, ax + aw / 2, ay + ACT_H - 15, "Helvetica-Bold", 9, WHITE, "center")
        txt(c, l2, ax + aw / 2, ay + 7,  "Helvetica-Oblique", 7, BLUE_LT, "center")

        # [M] badge: initial mob = orange; pool reuse = green
        mob_col  = MOB_C if idx == 0 else REUSE_C
        mob_cost = "+c_mob" if idx == 0 else "c_mob=0"
        mob_cost_col = MOB_C if idx == 0 else REUSE_C
        c.setFillColor(mob_col)
        c.circle(ax + 11, ay + ACT_H / 2, 9, fill=1, stroke=0)
        txt(c, "M", ax + 11, ay + ACT_H / 2 - 3, "Helvetica-Bold", 7, WHITE, "center")

        # [D] badge
        c.setFillColor(DEM_C)
        c.circle(ax + aw - 11, ay + ACT_H / 2, 9, fill=1, stroke=0)
        txt(c, "D", ax + aw - 11, ay + ACT_H / 2 - 3, "Helvetica-Bold", 7, WHITE, "center")

        # mob cost annotation below badge
        txt(c, mob_cost, ax + 11, ay - 10,
            "Helvetica-Bold", 6.5, mob_cost_col, "center")

    # Gap standby bands in activity row
    for gs, ge in gaps_pool:
        gx = wx(gs) + 1
        gw = (ge - gs + 1) * wk - 2
        c.setFillColor(colors.HexColor("#EDE0F5"))
        c.setStrokeColor(STAN_C); c.setLineWidth(0.7); c.setDash([4, 2])
        c.roundRect(gx, act_bot, gw, ACT_H, 4, fill=1, stroke=1)
        c.setDash()
        txt(c, "standby", gx + gw / 2, act_bot + ACT_H - 14,
            "Helvetica-Oblique", 7.5, STAN_C, "center")
        txt(c, "κ·c_eq/sem",  gx + gw / 2, act_bot + 7,
            "Helvetica", 7, STAN_C, "center")

    # ── Slot state row: ESC-01 ───────────────────────────────────────────────
    SLT_H  = 26
    slt_top = act_bot - 14   # 389
    slt_bot = slt_top - SLT_H  # 363

    txt(c, "ESC-01", tl_x - 4, slt_bot + 9, "Helvetica-Bold", 8, DARK, "right")

    for idx, (l1, l2, s, e, col) in enumerate(acts_pool):
        ax = wx(s) + 1
        aw = (e - s + 1) * wk - 2
        rect(c, ax, slt_bot, aw, SLT_H, col, r=3)
        txt(c, "ATIVO", ax + aw / 2, slt_bot + 8, "Helvetica-Bold", 7.5, WHITE, "center")
        txt(c, "S_r=0",  ax + aw / 2, slt_top + 4, "Helvetica", 6, MUTED, "center")

    for gs, ge in gaps_pool:
        gx = wx(gs) + 1
        gw = (ge - gs + 1) * wk - 2
        rect(c, gx, slt_bot, gw, SLT_H, POOL_BG, r=3)
        txt(c, "NO POOL", gx + gw / 2, slt_bot + 8, "Helvetica-Bold", 7, WHITE, "center")
        txt(c, "S_r=1",  gx + gw / 2, slt_top + 4, "Helvetica", 6, POOL_BG, "center")

    # "retorna ao pool" annotation after last activity
    last_s, last_e = acts_pool[-1][2], acts_pool[-1][3]
    ret_x = wx(last_e + 1) if last_e < N_WKS else wx(last_e) + wk
    if ret_x < tl_x + tl_w - 10:
        txt(c, "→ retorna", ret_x + 2, slt_bot + 9, "Helvetica-Oblique", 6.5, POOL_BG)

    # ── Chain bracket ─────────────────────────────────────────────────────────
    br_y  = slt_bot - 10   # 353
    br_x1 = wx(1)
    br_x2 = wx(last_e) + wk

    c.setStrokeColor(POS_C); c.setLineWidth(1.4)
    c.line(br_x1, br_y, br_x2, br_y)
    c.line(br_x1, br_y, br_x1, br_y + 7)
    c.line(br_x2, br_y, br_x2, br_y + 7)
    mid_x = (br_x1 + br_x2) / 2
    c.setFillColor(POS_C)
    c.roundRect(mid_x - 140, br_y - 11, 280, 14, 3, fill=1, stroke=0)
    txt(c, "Cadeia 1   —   1 mob total  ·  1 demob total  ·  c_mob cobrado 1×",
        mid_x, br_y - 4, "Helvetica-Bold", 7, WHITE, "center")

    # ── Legend (mob colors) ───────────────────────────────────────────────────
    leg_x = br_x2 + 14
    leg_y = br_y - 3
    if leg_x < tl_x + tl_w - 100:
        c.setFillColor(MOB_C);   c.circle(leg_x + 6,  leg_y, 5, fill=1, stroke=0)
        txt(c, "mob inicial",  leg_x + 14, leg_y + 1, "Helvetica", 6.5, MUTED)
        c.setFillColor(REUSE_C); c.circle(leg_x + 80, leg_y, 5, fill=1, stroke=0)
        txt(c, "mob do pool (c_mob=0)", leg_x + 88, leg_y + 1, "Helvetica", 6.5, MUTED)

    # ── Separator ──────────────────────────────────────────────────────────────
    sep_y = br_y - 28   # 325
    c.setStrokeColor(LGRAY); c.setLineWidth(0.5)
    c.line(CX, sep_y, CX + CW, sep_y)

    # ── Sem pool section ─────────────────────────────────────────────────────
    rect(c, CX, sep_y - 18, CW, 18, NEG_C, r=3)
    txt(c, "Sem pool — 3 contratos independentes",
        CX + CW / 2, sep_y - 9, "Helvetica-Bold", 8.5, WHITE, "center")

    SP_H   = 32
    sp_top = sep_y - 18   # 307
    sp_bot = sp_top - SP_H  # 275

    for idx, (l1, l2, s, e, _col) in enumerate(acts_pool):
        ax = wx(s) + 1
        aw = (e - s + 1) * wk - 2
        c.setFillColor(colors.HexColor("#B0B8C8"))
        c.roundRect(ax, sp_bot, aw, SP_H, 3, fill=1, stroke=0)
        txt(c, l1, ax + aw / 2, sp_bot + 9, "Helvetica-Bold", 8, WHITE, "center")
        # [M] red
        c.setFillColor(NEG_C)
        c.circle(ax + 10, sp_bot + SP_H / 2, 8, fill=1, stroke=0)
        txt(c, "M", ax + 10, sp_bot + SP_H / 2 - 3, "Helvetica-Bold", 6.5, WHITE, "center")
        # [D] gray
        c.setFillColor(DEM_C)
        c.circle(ax + aw - 10, sp_bot + SP_H / 2, 8, fill=1, stroke=0)
        txt(c, "D", ax + aw - 10, sp_bot + SP_H / 2 - 3, "Helvetica-Bold", 6.5, WHITE, "center")
        # annotation
        txt(c, "+c_mob", ax + 10, sp_bot - 9, "Helvetica-Bold", 6.5, NEG_C, "center")

    # Gaps em sem-pool: sem standby (contrato encerrado)
    for gs, ge in gaps_pool:
        gx = wx(gs) + 1
        gw = (ge - gs + 1) * wk - 2
        c.setFillColor(colors.HexColor("#F5EAEA"))
        c.setStrokeColor(NEG_C); c.setLineWidth(0.4); c.setDash([2, 2])
        c.roundRect(gx, sp_bot, gw, SP_H, 3, fill=1, stroke=1)
        c.setDash()
        txt(c, "—", gx + gw / 2, sp_bot + 9, "Helvetica-Oblique", 8, NEG_C, "center")

    # Sem pool summary annotation
    txt(c, "3× c_mob  +  3× c_demob  +  rescisão e recontratação a cada atividade",
        CX + CW / 2, sp_bot - 18, "Helvetica-Bold", 8, NEG_C, "center")

    # ── Comparison boxes at bottom ───────────────────────────────────────────
    box_top = sp_bot - 34   # 241
    box_h   = 64
    box_w   = (CW - 20) / 2
    bx1     = CX
    bx2     = CX + box_w + 20

    # Com pool box
    rect(c, bx1, box_top - box_h, box_w, box_h, GRAY, stroke_color=POS_C, lw=1.0, r=5)
    rect(c, bx1, box_top - 20, box_w, 20, POS_C, r=5)
    txt(c, "Custo com pool", bx1 + box_w / 2, box_top - 12,
        "Helvetica-Bold", 8.5, WHITE, "center")
    cp_items = [
        "1× c_mob  ·  1× c_demob (por cadeia)",
        "κ · c_eq × n_standby  (EQ em standby)",
        "MO: retido ou dispensado por contrato",
    ]
    iy = box_top - 32
    for ln in cp_items:
        txt(c, f"• {ln}", bx1 + 10, iy, "Helvetica", 7.5, DARK)
        iy -= 14

    # Sem pool box
    rect(c, bx2, box_top - box_h, box_w, box_h, GRAY, stroke_color=NEG_C, lw=1.0, r=5)
    rect(c, bx2, box_top - 20, box_w, 20, NEG_C, r=5)
    txt(c, "Custo sem pool", bx2 + box_w / 2, box_top - 12,
        "Helvetica-Bold", 8.5, WHITE, "center")
    sp_items = [
        "n_ativ × c_mob  ·  n_ativ × c_demob",
        "Sem standby (contrato encerrado no [D])",
        "Perda de curva de aprendizado",
    ]
    iy = box_top - 32
    for ln in sp_items:
        txt(c, f"• {ln}", bx2 + 10, iy, "Helvetica", 7.5, DARK)
        iy -= 14


# ── SLIDE 9: Composição da Equipe-Padrão ──────────────────────────────────────

def s_equipe_composição(c):
    slide_frame(c, "Definição: Composição da Equipe-Padrão", "Regras de Negocio", 8)

    MO_C  = BLUE2                         # azul para Mão de Obra
    EQ_C  = ORANGE                        # laranja para Equipamento
    MAT_C = GREEN                         # verde para Material

    def_x = 640
    def_w = CX + CW - def_x              # 280
    dia_w = def_x - CX - 10             # 590

    # ── Header box ─────────────────────────────────────────────────────────────
    hdr_top = CT - 16                    # 476
    hdr_h   = 56
    hdr_bot = hdr_top - hdr_h           # 420

    rect(c, CX, hdr_bot, dia_w, hdr_h, DARK, r=8)
    txt(c, "Equipe-padrão  e_i", CX + dia_w / 2, hdr_top - 15,
        "Helvetica-Bold", 13, WHITE, "center")
    txt(c, "composição formal de recursos associados a uma atividade i",
        CX + dia_w / 2, hdr_top - 30, "Helvetica", 8.5, BLUE_LT, "center")
    txt(c, "unica por atividade  |  instanciada m_ij vezes na semana j",
        CX + dia_w / 2, hdr_top - 44, "Helvetica-Oblique", 7.5, BLUE_LT, "center")

    # ── Three resource-type columns ────────────────────────────────────────────
    col_gap = 13
    col_w   = (dia_w - 2 * col_gap) / 3     # ≈ 188
    col_top = hdr_bot - 16                  # 404
    col_h   = 110
    col_bot = col_top - col_h              # 294

    cols_data = [
        ("MO — Mão de Obra",  MO_C,  "r in R_i^MO",
         [("Operador de maquina",   "x 1"),
          ("Auxiliar de operação",  "x 2"),
          ("Encarregado",           "x 0.5")]),
        ("EQ — Equipamento",  EQ_C,  "e in R_i^EQ",
         [("Retroescavadeira",      "x 1"),
          ("Caminhao basculante",   "x 1"),
          ("Compactador",           "x 1")]),
        ("MAT — Material",    MAT_C, "v in R_i^MAT",
         [("Diesel",                "180 L/sem"),
          ("Lubrificante",          "8 L/sem"),
          ("Peca de consumo",       "verba/sem")]),
    ]

    col_centers = []
    for ci, (col_title, col_color, notation, rows) in enumerate(cols_data):
        cx = CX + ci * (col_w + col_gap)
        col_cx = cx + col_w / 2
        col_centers.append(col_cx)

        rect(c, cx, col_bot, col_w, col_h, GRAY, stroke_color=col_color, lw=0.9, r=5)
        rect(c, cx, col_top - 22, col_w, 22, col_color, r=5)
        txt(c, col_title, col_cx, col_top - 14,
            "Helvetica-Bold", 8.5, WHITE, "center")

        ry = col_top - 36
        for rname, rqty in rows:
            c.setFillColor(WHITE)
            c.setStrokeColor(LGRAY)
            c.setLineWidth(0.4)
            c.roundRect(cx + 5, ry - 15, col_w - 10, 17, 2, fill=1, stroke=1)
            txt(c, rname,        cx + 10,        ry - 7.5, "Helvetica", 7.5, DARK)
            txt(c, rqty,         cx + col_w - 8, ry - 7.5, "Helvetica-Bold", 7.5,
                col_color, "right")
            ry -= 22

        txt(c, f"({notation})", col_cx, col_bot + 8,
            "Helvetica-Oblique", 7, MUTED, "center")

    # ── Org-chart connector lines ─────────────────────────────────────────────
    c.setStrokeColor(MUTED)
    c.setLineWidth(0.8)
    c.setDash([])
    c.line(col_centers[0], hdr_bot, col_centers[2], hdr_bot)
    for col_cx in col_centers:
        c.line(col_cx, hdr_bot, col_cx, col_top)
    ah = 5
    c.setFillColor(MUTED)
    for col_cx in col_centers:
        poly(c, [(col_cx, col_top),
                 (col_cx - ah / 2, col_top + ah),
                 (col_cx + ah / 2, col_top + ah)])

    # ── Cost bridge ───────────────────────────────────────────────────────────
    math_box(c, CX, col_bot - 8, dia_w, "Custo horario da equipe-padrão", [
        {"type": "math",
         "latex": r"\gamma_i = \sum_{r \in R_i} n_r \cdot \gamma_r",
         "size": 12, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"n_r\text{: qtd/equipe} \quad \gamma_r\text{: custo/hora de }r",
         "size": 9, "align": "left"},
        {"type": "math",
         "latex": r"r \in R_i = R_i^{MO} \cup R_i^{EQ} \cup R_i^{MAT}",
         "size": 9, "align": "left"},
    ])

    # ── Right panel: formal definitions ──────────────────────────────────────
    y_r = CT - 16

    y_r = math_box(c, def_x, y_r, def_w, "Composição formal", [
        {"type": "math",
         "latex": r"e_i = (R_i^{MO},\, R_i^{EQ},\, R_i^{MAT})",
         "size": 10, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"R_i^{*} = \{(r,\, n_r)\}_r",
         "size": 10, "align": "center"},
        {"type": "math",
         "latex": r"r\text{: tipo de recurso} \quad n_r\text{: qtd/equipe}",
         "size": 9, "align": "left"},
    ], title_bg=DARK)
    y_r -= 7

    y_r = math_box(c, def_x, y_r, def_w, "Custo horario", [
        {"type": "math",
         "latex": r"\gamma_i = \sum_{r \in R_i} n_r \cdot \gamma_r",
         "size": 11, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"\gamma_r\text{: custo/hora do recurso } r",
         "size": 9, "align": "left"},
    ])
    y_r -= 7

    y_r = math_box(c, def_x, y_r, def_w, "Escala semanal", [
        {"type": "math",
         "latex": r"m_{ij} \text{ equipes} \Rightarrow m_{ij} \cdot n_r \text{ un. de } r",
         "size": 9, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"\text{instancias identicas — mesma }e_i",
         "size": 9, "align": "left"},
        {"type": "math",
         "latex": r"m_{ij}\text{ varia por semana (ramp up/down)}",
         "size": 9, "align": "left"},
    ])
    y_r -= 7

    math_box(c, def_x, y_r, def_w, "Slots no pool (E_i)", [
        {"type": "math",
         "latex": r"|\mathcal{E}_i^r| = m_i^{*} \cdot n_r \quad (r \in R_i)",
         "size": 10, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"m_i^*\text{: peak de }m_{ij} \;\; n_r\text{: qtd do tipo }r",
         "size": 9, "align": "left"},
        {"type": "math",
         "latex": r"\text{ex: }1\,\mathrm{ESC}+2\,\mathrm{OP},\;m^*\!=2\;\Rightarrow\;2\,\mathrm{ESC}+4\,\mathrm{OP}",
         "size": 9, "align": "left"},
        {"type": "math",
         "latex": r"\text{[D] devolve }n_r\text{ slots do tipo }r\text{ ao pool}",
         "size": 9, "align": "left"},
    ], title_bg=colors.HexColor("#1A3A6A"))


# ── SLIDE 9: Custo Operacional ─────────────────────────────────────────────────

def s_regras_custo(c):
    slide_frame(c, "Regras de Negocio: Custo Operacional", "Regras de Negocio", 11)
    lw = 415; rx = CX + lw + 18; rw = CW - lw - 18
    y = CT - 20

    # ── LEFT COLUMN ───────────────────────────────────────────────────────────
    y = math_box(c, CX, y, lw, "Custo horario da equipe", [
        {"type": "math",
         "latex": r"\gamma_i = \sum_{r \in R_i} n_r \gamma_r = \frac{\tilde{C}_i^{sem}}{h_{sem}}",
         "size": 12, "align": "center"},
        {"type": "text", "content": "Decomposto: MO, EQ, combustivel, material"},
    ])
    y -= 6

    y = math_box(c, CX, y, lw, "Eficiencia composta", [
        {"type": "math",
         "latex": r"\eta = \eta_s \cdot \eta_p \cdot \eta_w",
         "size": 12, "align": "center"},
        {"type": "text", "content": "escala (frentes)  |  clima e calendário  |  gestão"},
    ])
    y -= 6

    y = math_box(c, CX, y, lw, "Custo por ciclo de vida da equipe (ADR-125)", [
        {"type": "math",
         "latex": r"C_{prod,i} = \gamma_i \, n_p",
         "size": 11, "align": "center"},
        {"type": "math",
         "latex": r"C_{pool,i} = C_{prod,i} + (\gamma_i^{mo} + \kappa \gamma_i^{eq}) n_s",
         "size": 11, "align": "center"},
        {"type": "math",
         "latex": r"\tilde{C}_i = C_{pool,i} + c_{mob} + c_{dem}",
         "size": 11, "align": "center"},
        {"type": "gap", "height": 3},
        {"type": "text", "content": "n_p: semanas produtivas  |  n_s: semanas standby"},
        {"type": "text", "content": "MO standby: γ_i^mo integral (CLT, irredutível)"},
        {"type": "text", "content": "EQ standby: κ·γ_i^eq  (κ ≤ 1, estacionado)"},
        {"type": "text", "content": "c_mob + c_dem: custo indireto de canteiro (BDI/DI), uma vez por cadeia"},
        {"type": "text", "content": "C_prod ≤ C_pool ≤ custo total (contratual)", "bold": True},
    ])

    # ── RIGHT COLUMN ──────────────────────────────────────────────────────────
    y_r = CT - 20

    # ── Secao: Preços unitários — dois setores lado a lado ────────────────────
    half_w = (rw - 6) / 2
    y_cat = math_box(c, rx, y_r, half_w, "Catálogo", [
        {"type": "math",
         "latex": r"p_i^c = \frac{\gamma_i}{\rho_i}",
         "size": 14, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"\rho_i\text{: produtividade horaria } [\mathrm{un/h}]",
         "size": 9, "align": "left"},
    ], title_bg=ORANGE)
    y_op = math_box(c, rx + half_w + 6, y_r, half_w, "Operacional", [
        {"type": "math",
         "latex": r"p_i^o = \frac{C_{pool,i}}{Q_i}",
         "size": 14, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"C_{pool,i}\text{: custo direto (ativo+ocioso), exclui mob/dem (ADR-125)}",
         "size": 9, "align": "left"},
    ], title_bg=GREEN)
    y_r = min(y_cat, y_op) - 8

    # ── Secao: Relacao entre preço de catálogo e operacional ──────────────────
    y_r = math_box(c, rx, y_r, rw, "Relacao entre preço de catálogo e operacional", [
        {"type": "math",
         "latex": r"p_i^o = p_i^c \cdot \tau_i, \quad \tau_i \geq 1",
         "size": 12, "align": "center"},
        {"type": "math",
         "latex": r"\tau_i = \frac{\sum_j m_{ij}}{\sum_j \delta_j \, \lambda_j \, m_{ij}}",
         "size": 13, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "math",
         "latex": r"\delta_j = \frac{d_j}{d} \;\; \text{(fracao de dias na semana } j\text{)}",
         "size": 10, "align": "left"},
        {"type": "math",
         "latex": r"\lambda_j\text{: praticabilidade climatica da semana } j",
         "size": 10, "align": "left"},
        {"type": "math",
         "latex": r"\tau_i \geq 1 \;\Rightarrow\; \text{custo operacional} \geq \text{catálogo}",
         "size": 10, "align": "left"},
    ])


# ── SLIDE 5: BDI e Valor de Venda ─────────────────────────────────────────────

def s_bdi(c):
    slide_frame(c, "Regras de Negocio: BDI e Valor de Venda", "Regras de Negocio", 12)
    lw = 415; rx = CX + lw + 18; rw = CW - lw - 18
    y = CT - 20

    y = math_box(c, CX, y, lw, "Formula do BDI  (base TCU, Acordao 2622/2013)", [
        {"type": "math",
         "latex": r"\beta = \frac{(1+AC)(1+DF)(1+R)(1+CR)(1+L)}{1 - T} - 1",
         "size": 12, "align": "center"},
        {"type": "text", "content": "AC adm. central  ·  DF desp. financeiras  ·  R risco/seguro/garantia"},
        {"type": "text", "content": "CR contingencia  ·  L lucro  ·  T tributos (PIS+COFINS+ISS+CSLL+IR)"},
        {"type": "text", "content": "Composição multiplicativa; BDI por categoria de custo", "bold": True},
    ])
    y -= 7

    y = math_box(c, CX, y, lw, "Valor de venda", [
        {"type": "text", "content": "Direto — recursos das atividades:", "bold": True},
        {"type": "math",
         "latex": r"V_i^D = \sum_{j=t_i^{\min}}^{t_i^{\max}} \sum_{r \in A_i} \beta_r \, \gamma_r \, h \, d \, m_{ij}",
         "size": 11, "align": "center"},
        {"type": "gap", "height": 3},
        {"type": "text", "content": "Indireto — apoio (topografia, laboratorio, QSMS, adm):", "bold": True},
        {"type": "math",
         "latex": r"V_i^I = \sum_{j=t_i^{\min}}^{t_i^{\max}} \sum_{q \in B_i} \beta_q \, \gamma_q \, h \, d",
         "size": 11, "align": "center"},
    ])
    y -= 7

    y = math_box(c, CX, y, lw, "Métricas gerenciais", [
        {"type": "text", "content": "Razao indireto / direto:", "bold": True},
        {"type": "math", "latex": r"\frac{\tilde{C}^I}{\tilde{C}^D}", "size": 12, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "text", "content": "Participacao do indireto no total:", "bold": True},
        {"type": "math", "latex": r"\frac{\tilde{C}^I}{\tilde{C}^D + \tilde{C}^I}", "size": 12, "align": "center"},
        {"type": "gap", "height": 2},
        {"type": "text", "content": "Margem de operacionalização:", "bold": True},
        {"type": "math", "latex": r"\frac{V - \tilde{C}}{\tilde{C}}", "size": 12, "align": "center"},
    ])

    # RIGHT COLUMN
    y_r = CT - 20

    y_r = math_box(c, rx, y_r, rw, "Memorial de cálculo do BDI", [
        {"type": "text", "content": "Trilha auditavel completa, de ponta a ponta:", "bold": True},
        {"type": "text", "content": "  salário -> encargos -> custo -> BDI -> preço de venda"},
        {"type": "gap", "height": 4},
        {"type": "text", "content": "Assinatura de integridade por versão do perfil"},
        {"type": "text", "content": "Diferencas destacadas entre versões"},
        {"type": "text", "content": "Exportavel em PDF e planilha para o cliente"},
    ])
    y_r -= 6

    y_r = math_box(c, rx, y_r, rw, "Tres niveis de custo", [
        {"type": "text", "content": "1. Equipes isoladas (sem partilha de recursos)"},
        {"type": "text", "content": "2. Com pool partilhado entre atividades"},
        {"type": "text", "content": "3. Custo final por ciclo de vida de cada equipe"},
        {"type": "gap", "height": 4},
        {"type": "text", "content": "Cada nivel e rastreavel — diagnostico de onde vem o custo", "bold": True},
    ])
    y_r -= 6

    y_r = math_box(c, rx, y_r, rw, "Perfil de BDI versionado", [
        {"type": "text", "content": "Cada revisão registra quem confirmou, quando e por que"},
        {"type": "text", "content": "Taxas negociadas (ISS, lucro) geram nova versão"},
        {"type": "gap", "height": 3},
        {"type": "text", "content": "Assinatura de conteudo previne adulteração silenciosa", "bold": True},
    ])


# ── SLIDE 6: Pool RCPSP ────────────────────────────────────────────────────────

def s_pool(c):
    slide_frame(c, "Cenários e Cubo Analítico", "Regras de Negocio", 10)
    lw = 415; rx = CX + lw + 18; rw = CW - lw - 18
    y = CT - 20

    y = math_box(c, CX, y, lw, "Exploracao de cenários (what-if)", [
        {"type": "text", "content": "Executa N cenários em paralelo, variando:", "bold": True},
        {"type": "text", "content": "•  número de frentes de trabalho"},
        {"type": "text", "content": "•  jornada e turnos"},
        {"type": "text", "content": "•  tamanho do pool e composição das equipes"},
        {"type": "gap", "height": 2},
        {"type": "text", "content": "Seleciona a fronteira otima entre custo, prazo e margem", "bold": True},
    ])

    # RIGHT COLUMN: analytical cube — business value framing
    y_r = CT - 20
    y_r = math_box(c, rx, y_r, rw, "Cubo analítico do pool — 7 visoes", [
        {"type": "text", "content": "Responde: por que esta obra custa o que custa?", "bold": True,
         "color": BLUE},
        {"type": "gap", "height": 4},
        {"type": "text", "content": "1. Ciclo de vida de cada equipamento"},
        {"type": "text", "content": "2. Custo por estado: ativo / ocioso / mob. / desmob."},
        {"type": "text", "content": "3. Utilização ao longo do tempo"},
        {"type": "text", "content": "4. Quais atividades usam cada recurso"},
        {"type": "text", "content": "5. Origem do custo: produtivo / ocioso / mobilização"},
        {"type": "text", "content": "6. Economia do pool vs. recurso dedicado"},
        {"type": "text", "content": "7. Como o custo se propaga entre atividades"},
    ])


def s_versionado(c):
    slide_frame(c, "Execução Versionada: Ciclos de Vida e Rastreabilidade", "Execução Versionada", 13)

    # ── Project lifecycle state machine ───────────────────────────────────
    txt(c, "Ciclo de vida do PROJETO", CX, CT-26, "Helvetica-Bold", 10, BLUE)
    state_machine(c, CX, CT-62,
        [("Rascunho",""), ("Em\nvalidação",""), ("Aprovado",""),
         ("Em\nexecução",""), ("Concluido","")],
        node_w=98, node_h=36, gap=30, accent=BLUE, final_color=GREEN)
    # responsibility boundary under the project states
    col_op = ROLE_COLORS["operator"]; col_eng = ROLE_COLORS["engineer"]
    by = CT - 88
    rect(c, CX, by-3, 98, 4, col_op, r=2)              # Rascunho span
    rect(c, CX+128, by-3, 522, 4, col_eng, r=2)        # validação -> concluido span
    txt(c, "Comercial: cria o projeto e produz a estimativa inicial (RFI)",
        CX, by-15, "Helvetica-Bold", 8, col_op)
    txt(c, "A partir da validação a Engenharia assume: planejamento completo (RFP), aprovação e acompanhamento.",
        CX, by-27, "Helvetica", 8, MUTED)

    # ── Plan lifecycle state machine (with archive branch) ────────────────
    txt(c, "Ciclo de vida do PLANO (cenário de planejamento)", CX, CT-130, "Helvetica-Bold", 10, BLUE)
    state_machine(c, CX, CT-184,
        [("Rascunho",""), ("Em\nandamento",""), ("Aprovado","")],
        node_w=104, node_h=36, gap=44, accent=ORANGE, final_color=GREEN,
        branch=(1, "descartado", "Arquivado"))
    # caption to the right of the plan state machine (avoids the branch box)
    txt(c, "Apenas 1 plano aprovado por escopo.", 560, CT-176, "Helvetica-Bold", 8.5, BLUE)
    txt(c, "Aprovar congela tudo: números,", 560, CT-190, "Helvetica", 8.5, MUTED)
    txt(c, "catálogo e BDI usados.", 560, CT-203, "Helvetica", 8.5, MUTED)

    # ── Bottom-left: what a plan preserves ────────────────────────────────
    labeled_box(c, CX, CT-410, 415, 152, "O que cada plano guarda (executivo)", [
        "Resultado completo de cada etapa do cálculo",
        "Premissas usadas (jornada, frentes, pool)",
        "Versão exata do catálogo no momento da execução",
        "Perfil de BDI com assinatura de integridade",
        "Relatórios, planilhas e pacote de auditoria",
        "",
        "Plano aprovado e imutável — histórico preservado.",
    ])

    # ── Bottom-right: reproducibility + comparison ────────────────────────
    rx = CX + 435; rw = CW - 435
    labeled_box(c, rx, CT-330, rw, 72, "Reprodutibilidade", [
        "Cada execução é 'fotografada': re-rodar produz o",
        "mesmo número, mesmo que o catálogo mude depois.",
        "Cliente questionou um valor? Reconstruimos a obra exata.",
    ], title_bg=GREEN)
    labeled_box(c, rx, CT-410, rw, 72, "Comparação entre cenários", [
        "Dois planos lado a lado: custo direto e indireto,",
        "margem bruta, prazo e composição de BDI.",
        "Decisão informada entre alternativas.",
    ])


def s_catalogo(c):
    slide_frame(c, "Gerenciamento de Catálogo: Versionamento e Atualização", "Catálogo", 14)
    lw = 390; rx = CX + lw + 24; rw = CW - lw - 24

    labeled_box(c, CX, CT-130, lw, 130, "O que compõe o catálogo", [
        ("Insumos",        "mão de obra, equipamentos, material e diesel"),
        ("Composições",    "preço unitário por serviço"),
        ("Produtividades", "rendimento calibrado por condição"),
        ("Regimes",        "encargos trabalhistas e tributos"),
        "",
        "Agrupado por contexto (ex.: MendesLobo) e versionado.",
    ], key_w=100)
    labeled_box(c, CX, CT-248, lw, 108, "Diagnostico antes de mudar", [
        ("Saude",          "% de serviços calculáveis"),
        ("Plausibilidade", "preços fora da curva"),
        ("Impacto",        "variação em todos os serviços"),
        ("Simulacao",      "novo preço sem alterar o catálogo"),
        ("Histórico",      "tendencia de cada insumo"),
    ], key_w=105)
    labeled_box(c, CX, CT-362, lw, 106, "Calibracao por obra real", [
        "Produtividade não é palpite: cada rendimento tem",
        "origem rastreavel (obra real, tabela ou estimativa)",
        "e qualidade medida (amostras, intervalo de confianca).",
        "",
        "Equipe alternativa? O rendimento escala junto.",
    ])
    labeled_box(c, rx, CT-106, rw, 106, "Regra dos quatro olhos", [
        "Quem edita NÃO e quem aprova:",
        "",
        ("Engenharia",      "cria e edita o rascunho"),
        ("Suprimentos / TI","aprovam a publicação"),
        "",
        "Segregação de funções — controle e auditoria.",
    ], title_bg=ORANGE, key_w=110)
    labeled_box(c, rx, CT-240, rw, 124, "Fluxo de atualização", [
        "1.  Comparar fonte de mercado com o catálogo atual",
        "2.  Atualizar preço (com quem, quando e por que)",
        "3.  Abrir rascunho de catálogo",
        "4.  Revisar divergencias e impacto",
        "5.  Aprovar a publicação (quatro olhos)",
        "",
        "Resultado: nova versão do catálogo.",
    ])
    labeled_box(c, rx, CT-362, rw, 114, "Isolamento de projetos", [
        "Nova versão do catálogo NÃO afeta projetos ja",
        "existentes — cada projeto guarda a versão que",
        "usou no momento da execução.",
        "",
        "Aplicar preços novos e uma DECISAO explicita:",
        "cria-se um novo plano e compara-se o resultado.",
    ], title_bg=GREEN)


def s_roles(c):
    slide_frame(c, "Papeis: Cinco Perfis de Acesso e Permissoes", "Papeis & Permissoes", 15)

    # Columns: Papel | Responsabilidade | 6 capabilities
    px0 = CX                 # Papel
    pw0 = 112
    px1 = CX + 118           # Responsabilidade
    pw1 = 245
    cap_start = CX + 375
    cap_w = (CW - 375) / 6
    cap_x = [cap_start + i*cap_w for i in range(6)]
    cap_hdr = [("Estimar","(RFI)"), ("Planejar","(RFP)"), ("Aprovar","plano"),
               ("Editar","catálogo"), ("Publicar","catálogo"), ("Consultar","/ auditar")]

    th = 30
    ty = CT - 16
    rect(c, CX, ty-th, CW, th, BLUE, r=3)
    txt(c, "Papel", px0+6, ty-19, "Helvetica-Bold", 9, WHITE)
    txt(c, "Responsabilidade", px1+4, ty-19, "Helvetica-Bold", 9, WHITE)
    for i, (h1, h2) in enumerate(cap_hdr):
        cx = cap_x[i] + cap_w/2
        txt(c, h1, cx, ty-13, "Helvetica-Bold", 8, WHITE, "center")
        txt(c, h2, cx, ty-24, "Helvetica", 7, BLUE_LT, "center")

    # capability flags per papel: E(RFI) P(RFP) Aprovar Editar Publicar Consultar
    rows = [
        ("operator",    "Estimativa de preço ao cliente",        [1,0,0,0,0,1]),
        ("engineer",    "Planejamento técnico completo",         [1,1,1,1,0,1]),
        ("admin",       "Administracao, aprovacoes e usuarios",  [1,1,1,1,1,1]),
        ("auditor",     "Auditoria e leitura (somente consulta)",[0,0,0,0,0,1]),
        ("cat-manager", "Gestão do catálogo (sem projetos)",     [0,0,0,1,1,0]),
    ]
    row_h = 30
    for ri, (role, resp, caps) in enumerate(rows):
        ry = ty - th - (ri+1)*row_h
        bg = GRAY if ri % 2 == 0 else WHITE
        rect(c, CX, ry, CW, row_h, bg, stroke_color=LGRAY, lw=0.3, r=0)
        col = ROLE_COLORS[role]
        rect(c, px0, ry+5, pw0, row_h-10, col, r=10)
        txt(c, ROLE_PT[role], px0+pw0/2, ry+10, "Helvetica-Bold", 9, WHITE, "center")
        txt(c, resp, px1+4, ry+10, "Helvetica", 8.5, BLACK)
        for ci, ok in enumerate(caps):
            glyph = "✓" if ok else "–"
            gcol = GREEN if ok else colors.HexColor("#B0B6BE")
            txt(c, glyph, cap_x[ci]+cap_w/2, ry+9, "Helvetica-Bold", 13, gcol, "center")

    rect(c, CX, CB+4, CW, 20, colors.HexColor("#FFF3E8"), stroke_color=ORANGE, lw=0.8, r=3)
    txt(c, "RFI x RFP:  Comercial faz apenas a estimativa de preço (RFI);  Engenharia e TI fazem o planejamento completo (RFP).",
        CX+8, CB+10, "Helvetica", 8, ORANGE)


def s_matrix(c):
    slide_frame(c, "Matriz Papel x Ferramenta — Visao Completa", "Papeis & Permissoes", 16)
    groups = [
        ("Sistema",             [("ping", "v","v","v","v","v")]),
        ("Projetos leitura",    [("listar_projetos, consultar_status, comparar_planos, explorar_pool...", "v","v","v","v","-")]),
        ("Projetos criacao",    [("criar_projeto, iniciar_orcamento, nova_versao, gerir_escopo", "v","v","v","-","-")]),
        ("Projetos execução",   [("disparar_pipeline", "o","v","v","-","-"),
                                  ("explorar_configuracoes_go", "o","v","v","-","-"),
                                  ("simular_cenário_replan, empacotar_benchmark, salvar_perfil_bdi", "v","v","v","-","-")]),
        ("Projetos aprovação",  [("aprovar_versao", "-","v","v","-","-")]),
        ("Artefatos",           [("listar_artefatos, obter_artefato, auditar_plano, download_zip...", "v","v","v","v","-")]),
        ("Catálogo leitura",    [("pesquisar_catalogo, histórico_preco, calcular_pu, versões...", "v","v","v","-","v")]),
        ("Catálogo escrita",    [("atualizar_preco_insumo, adicionar_variante, criar_rascunho", "-","v","v","-","v")]),
        ("Catálogo merge",      [("aprovar_merge_catalogo, rejeitar_rascunho", "-","-","v","-","v")]),
        ("Financeiro",          [("obter_resultado_campanha, comparar_rfi_catalogo", "v","v","v","v","v")]),
    ]
    col_x = [CX, CX+350, CX+500, CX+565, CX+630, CX+695, CX+760]
    col_w = [345, 145, 60, 60, 60, 60, 60]
    th = 20
    ty = CT - 20
    rect(c, CX, ty-th, CW, th, BLUE, r=3)
    for i, h in enumerate(["Grupo / Ferramenta","Notas","Com","Eng","TI","Fin","Sup"]):
        ax = col_x[i] + (col_w[i]/2 if i >= 2 else 4)
        al = "center" if i >= 2 else "left"
        txt(c, h, ax, ty-14, "Helvetica-Bold", 8.5, WHITE, al)

    ry = ty - th
    rh = 16
    for grp, tools in groups:
        ry -= rh
        rect(c, CX, ry, CW, rh, colors.HexColor("#E0E8F0"), r=0)
        txt(c, grp, CX+6, ry+4, "Helvetica-Bold", 8, BLUE)
        for ti, (tool, *chks) in enumerate(tools):
            ry -= rh
            bg = GRAY if ti % 2 == 0 else WHITE
            rect(c, CX, ry, CW, rh, bg, stroke_color=LGRAY, lw=0.2, r=0)
            txt(c, tool, CX+12, ry+4, "Courier", 7, BLACK)
            for ci, chk in enumerate(chks):
                sym = "✓" if chk == "v" else ("○" if chk == "o" else "–")
                col = GREEN if chk == "v" else (ORANGE if chk == "o" else RED)
                txt(c, sym, col_x[2+ci]+col_w[2+ci]/2, ry+4, "Helvetica-Bold", 9, col, "center")

    rect(c, CX, CB+4, CW, 14, GRAY, r=2)
    txt(c, "Legenda:   ✓ acesso pleno      ○ parcial (apenas RFI)      – sem permissao        "
           "Com Comercial · Eng Engenharia · TI · Fin Financeiro · Sup Suprimentos",
        W/2, CB+8, "Helvetica", 7.5, MUTED, "center")


def _step_row(c, x, y_top, w, num, label, highlight, col, is_last):
    """Draw one step row with numbered badge, optional highlight, and connector arrow."""
    RH = 30
    bg = col if highlight else GRAY
    fc = WHITE if highlight else BLACK
    border = col if highlight else LGRAY
    rect(c, x, y_top - RH, w, RH, bg, stroke_color=border, lw=0.6 if not highlight else 0, r=5)
    # Number badge
    badge_cx = x + 16
    badge_cy = y_top - RH / 2
    c.setFillColor(WHITE if highlight else col)
    c.circle(badge_cx, badge_cy, 9.5, fill=1, stroke=0)
    txt(c, str(num), badge_cx, badge_cy - 4, "Helvetica-Bold", 9,
        col if highlight else WHITE, "center")
    txt(c, label, x + 32, y_top - RH/2 - 3, "Helvetica-Bold" if highlight else "Helvetica", 9.5, fc)
    if not is_last:
        mid_x = x + w / 2
        arrow(c, mid_x, y_top - RH, mid_x, y_top - RH - 3, col, lw=0.8)


def s_workflow_op_eng(c):
    slide_frame(c, "Workflows: Comercial e Engenharia", "Workflows por Papel", 17)
    col1 = ROLE_COLORS["operator"]
    col2 = ROLE_COLORS["engineer"]
    lw = 430; rx = CX + lw + 20; rw = CW - lw - 20
    ROW_GAP = 34

    # ── Comercial ─────────────────────────────────────────────────────────────
    user_figure(c, CX + 20, CT - 70, sz=26, color=col1, label="Comercial")
    rect(c, CX + 52, CT - 56, lw - 52, 24, col1, r=4)
    txt(c, "Estimativa de Preço  (RFI)", CX + 52 + (lw - 52) / 2, CT - 43,
        "Helvetica-Bold", 10, WHITE, "center")

    steps_op = [
        ("Verificar disponibilidade do sistema",          False),
        ("Explorar catálogo e contextos de projeto",      False),
        ("Criar projeto e definir escopo inicial",        False),
        ("Executar pipeline de estimativa  (RFI)",        True),
        ("Acompanhar processamento e verificar status",   False),
        ("Revisar resultados e auditar plano gerado",     False),
        ("Encaminhar para aprovação  — Engenharia / TI",  True),
    ]
    sy = CT - 62
    for i, (label, hi) in enumerate(steps_op, 1):
        _step_row(c, CX, sy, lw, i, label, hi, col1, i == len(steps_op))
        sy -= ROW_GAP

    # Summary
    sum_y = sy - 4
    rect(c, CX, sum_y - 40, lw, 40, colors.HexColor("#E8F0FE"), r=4)
    txt(c, "Escopo de atuacao", CX + 8, sum_y - 13, "Helvetica-Bold", 8.5, col1)
    txt(c, "Estimativas RFI  ·  leitura de catálogo  ·  simulação de cenários  ·  artefatos",
        CX + 8, sum_y - 26, "Helvetica", 8, BLACK)
    txt(c, "Não pode: planejamento RFP  ·  aprovar versões  ·  editar catálogo",
        CX + 8, sum_y - 37, "Helvetica", 8, MUTED)

    # ── Engenharia ──────────────────────────────────────────────────────────────
    user_figure(c, rx + 20, CT - 70, sz=26, color=col2, label="Engenharia")
    rect(c, rx + 52, CT - 56, rw - 52, 24, col2, r=4)
    txt(c, "Planejamento Completo  (RFP)", rx + 52 + (rw - 52) / 2, CT - 43,
        "Helvetica-Bold", 10, WHITE, "center")

    steps_eng = [
        ("Executar escopo, clima e catálogo  (RFI)",       False),
        ("Configurar parametros de planejamento",          False),
        ("Executar pipeline de planejamento  (RFP)",       True),
        ("Analisar pool de recursos e indicadores",        False),
        ("Comparar versões e ajustar conforme necessario", False),
        ("Aprovar versão  — plano e números congelados",   True),
        ("Encaminhar rascunho de catálogo para revisão",   True),
    ]
    sy = CT - 62
    for i, (label, hi) in enumerate(steps_eng, 1):
        _step_row(c, rx, sy, rw, i, label, hi, col2, i == len(steps_eng))
        sy -= ROW_GAP

    sum_y = sy - 4
    rect(c, rx, sum_y - 40, rw, 40, colors.HexColor("#E8F4EC"), r=4)
    txt(c, "Capacidades adicionais vs Comercial", rx + 8, sum_y - 13, "Helvetica-Bold", 8.5, col2)
    txt(c, "Planejamento RFP completo  ·  aprovação de versões  ·  proposta de catálogo",
        rx + 8, sum_y - 26, "Helvetica", 8, BLACK)
    txt(c, "Gestão de perfis BDI  ·  variantes de produção  ·  planejamento de equipes",
        rx + 8, sum_y - 35, "Helvetica", 7.5, BLACK)


def s_workflow_outros(c):
    slide_frame(c, "Workflows: TI, Financeiro e Suprimentos", "Workflows por Papel", 18)
    cw3 = (CW - 20) / 3
    roles_info = [
        ("admin",       "Tudo de Engenharia, e mais:", [
            ("Aprovar publicação do catálogo", True),
            ("Rejeitar rascunho de catálogo", False),
            ("Gestão de usuarios e acessos", False),
            ("Aprovacoes sem restrição", False),
        ], ["Cria o usuario e envia a","configuração de acesso;","o usuario entao conecta","o seu Claude Desktop."]),
        ("auditor",     "Somente consulta e leitura", [
            ("Consultar projetos e versões", False),
            ("Auditar o plano gerado", False),
            ("Baixar pacote de auditoria", False),
            ("Resultado de campanha", True),
            ("Comparar RFI x catálogo", True),
        ], ["NÃO cria, edita, executa","nem aprova.","Caso de uso: auditoria","e analise pos-obra."]),
        ("cat-manager", "Catálogo de ponta a ponta", [
            ("Criar rascunho de catálogo", False),
            ("Atualizar preço de insumo", False),
            ("Revisar divergencias", False),
            ("Aprovar publicação do catálogo", True),
            ("Gerar nova versão do contexto", False),
        ], ["NÃO acessa projetos","ou artefatos de obra.","Foco exclusivo na","curadoria do catálogo."]),
    ]
    for i, (role, subtitle, steps, notes) in enumerate(roles_info):
        col = ROLE_COLORS[role]
        x = CX + i*(cw3+10)
        y = CT - 36
        user_figure(c, x+cw3/2, y-56, sz=30, color=col, label=ROLE_PT[role])
        rect(c, x, y-88, cw3, 22, col, r=5)
        txt(c, subtitle, x+cw3/2, y-77, "Helvetica-Bold", 9, WHITE, "center")
        sy = y-112
        for step, hi in steps:
            bg = col if hi else GRAY
            fc = WHITE if hi else BLACK
            rect(c, x, sy-22, cw3, 21, bg, stroke_color=col if not hi else None, lw=0.5, r=4)
            txt(c, step, x+cw3/2, sy-15, "Helvetica-Bold" if hi else "Helvetica", 8.5, fc, "center")
            arrow(c, x+cw3/2, sy-22, x+cw3/2, sy-26, col, lw=0.7)
            sy -= 27
        ny = sy - 12
        for note in notes:
            txt(c, note, x+cw3/2, ny, "Helvetica-Oblique", 8, MUTED, "center")
            ny -= 13


def s_handoffs(c):
    slide_frame(c, "Handoffs entre Papeis", "Workflows por Papel", 19)
    # (id, color_key_1, label_1, acao_1, color_key_2, label_2, acao_2, descricao)
    handoffs = [
        ("H1","admin","TI",            "Cria o usuario e envia\na configuração de acesso",
              "operator","Novo usuario","Conecta o Claude Desktop\ne inicia a sessao",
              "Onboarding de usuario"),
        ("H2","operator","Comercial",  "Roda a estimativa de\npreco (RFI)",
              "engineer","Engenharia / TI","Revisa e aprova\na versão",
              "Execução -> Aprovação"),
        ("H3","operator","Comercial",  "Explora cenários\niniciais de preço",
              "engineer","Engenharia","Aprofunda no planejamento\ncompleto (RFP)",
              "Estimativa -> Planejamento"),
        ("H4","engineer","Engenharia", "Edita o rascunho do\ncatalogo (preços)",
              "cat-manager","Suprimentos / TI","Aprova a publicação\n(regra dos quatro olhos)",
              "Atualização de catálogo"),
    ]
    rh = 88
    for i, (hid, k1, l1, act1, k2, l2, act2, desc) in enumerate(handoffs):
        y = CT - 20 - i*rh
        txt(c, desc, CX, y-8, "Helvetica-Bold", 8.5, BLUE)
        hline(c, CX, CX+CW, y-12, LGRAY)
        hx = CX
        c1 = ROLE_COLORS.get(k1, BLUE)
        c2 = ROLE_COLORS.get(k2, BLUE)
        rect(c, hx, y-70, 28, 55, ORANGE, r=5)
        txt(c, hid, hx+14, y-36, "Helvetica-Bold", 14, WHITE, "center")
        hx += 36
        user_figure(c, hx+30, y-65, sz=26, color=c1, label=l1)
        hx += 72
        bw = 190
        rect(c, hx, y-70, bw, 55, GRAY, stroke_color=c1, lw=1, r=4)
        for li, ln in enumerate(act1.split("\n")):
            txt(c, ln, hx+8, y-26-li*15, "Helvetica", 8.5, BLACK)
        hx += bw + 4
        aw = 60; mid_y = y-42
        c.setStrokeColor(ORANGE); c.setLineWidth(1.5); c.setDash([5,3])
        c.line(hx, mid_y, hx+aw-6, mid_y); c.setDash()
        c.setFillColor(ORANGE)
        poly(c, [(hx+aw, mid_y),(hx+aw-7, mid_y-4),(hx+aw-7, mid_y+4)])
        txt(c, "HANDOFF", hx+aw/2, mid_y+5, "Helvetica-Bold", 7, ORANGE, "center")
        hx += aw + 4
        user_figure(c, hx+30, y-65, sz=26, color=c2, label=l2)
        hx += 72
        bw2 = CW - (hx - CX)
        rect(c, hx, y-70, bw2, 55, GRAY, stroke_color=c2, lw=1, r=4)
        for li, ln in enumerate(act2.split("\n")):
            txt(c, ln, hx+8, y-26-li*15, "Helvetica", 8.5, BLACK)


def s_deploy(c):
    slide_frame(c, "Processo de Deploy: Blue-Green no Azure ACA", "Infraestrutura", 4)
    steps_ci = [
        ("Code push\n+ PR merge",    BLUE),
        ("CI\nlint / teste / tipo",  BLUE),
        ("Build da\nimagem",         BLUE),
        ("Publica no\nregistro ACR", BLUE),
        ("Revisão de\nstaging (0%)", ORANGE),
    ]
    bw, bh = 130, 46
    gap = (CW - len(steps_ci)*bw) / (len(steps_ci)-1)
    ty = CT - 22
    for i, (label, col) in enumerate(steps_ci):
        x = CX + i*(bw+gap)
        rect(c, x, ty-bh, bw, bh, col, r=5)
        for li, ln in enumerate(label.split("\n")):
            txt(c, ln, x+bw/2, ty-15-li*13, "Helvetica-Bold" if li==0 else "Helvetica", 9, WHITE, "center")
        if i < len(steps_ci)-1:
            arrow(c, x+bw, ty-bh/2, x+bw+gap, ty-bh/2, LGRAY, lw=1.3)

    # ── Smoke gate: the staging revision only takes traffic if all 14 checks pass ──
    last_x = CX + (len(steps_ci)-1)*(bw+gap)
    bx, bw2 = 150, 660
    btop = ty-bh-16
    arrow(c, last_x+bw/2, ty-bh, last_x+bw/2, btop, ORANGE, lw=1.4)
    arrow(c, last_x+bw/2, btop, bx+bw2/2, btop, ORANGE, lw=1.4)
    bh2 = 150
    rect(c, bx, btop-bh2, bw2, bh2, GRAY, stroke_color=ORANGE, lw=1.5, r=6)
    rect(c, bx, btop-22, bw2, 22, ORANGE, r=6)
    txt(c, "Smoke Test — 14 verificacoes automaticas na revisão de staging",
        bx+bw2/2, btop-15, "Helvetica-Bold", 9.5, WHITE, "center")
    checks = [
        "Saude do sistema", "Servidor MCP responde",
        "API REST responde", "Autenticacao por papel",
        "Leitura do catálogo", "Cálculo de preço unitário",
        "Criacao de projeto", "Disparo da pipeline",
        "Conclusao de job", "Geracao de artefatos",
        "Download de pacote", "Versionamento de plano",
        "Limites de taxa (rate limit)", "Conexao com armazenamento",
    ]
    col_w = bw2/2
    for idx, chk in enumerate(checks):
        col = idx % 2
        row = idx // 2
        cxp = bx + 16 + col*col_w
        cyp = btop - 38 - row*16
        txt(c, "✓", cxp, cyp, "Helvetica-Bold", 9, GREEN)
        txt(c, chk, cxp+14, cyp, "Helvetica", 8.5, BLACK)

    # ── Decision branches ─────────────────────────────────────────────────────
    smoke_x = bx+bw2/2; smoke_y = btop-bh2
    arrow(c, smoke_x, smoke_y, smoke_x-180, smoke_y-26, RED, lw=1.5)
    arrow(c, smoke_x, smoke_y, smoke_x+180, smoke_y-26, GREEN, lw=1.5)
    rxb = smoke_x-180-130
    rect(c, rxb, smoke_y-86, 260, 56, RED, r=5)
    txt(c, "FALHOU  ->  Rollback", rxb+130, smoke_y-52, "Helvetica-Bold", 10, WHITE, "center")
    txt(c, "Revisão de staging descartada;", rxb+130, smoke_y-67, "Helvetica", 8, WHITE, "center")
    txt(c, "100% do trafego segue na revisão atual", rxb+130, smoke_y-79, "Helvetica", 8, WHITE, "center")
    pxb = smoke_x+180-130
    rect(c, pxb, smoke_y-86, 260, 56, GREEN, r=5)
    txt(c, "PASSOU  ->  Promove trafego", pxb+130, smoke_y-52, "Helvetica-Bold", 10, WHITE, "center")
    txt(c, "Nova revisão: 0% -> 100% do trafego", pxb+130, smoke_y-67, "Helvetica", 8, WHITE, "center")
    txt(c, "Revisão anterior desmobilizada", pxb+130, smoke_y-79, "Helvetica", 8, WHITE, "center")


def s_catalogo_update(c):
    slide_frame(c, "Processo de Atualização de Catálogo: Regra dos Quatro Olhos", "Catálogo", 20)
    MID = CX + CW / 2  # 480

    # ── 1. Fontes ──────────────────────────────────────────────────────────────
    sources = [
        ("SINAPI",              BLUE),
        ("Pesquisa de mercado", BLUE),
        ("Calibração por obra", GREEN),
        ("Mudança tributária",  ORANGE),
    ]
    sbw, sbh = 148, 36
    gap_s = (CW - len(sources)*sbw) / (len(sources)-1)
    sy0 = CT - 24  # source box tops

    for i, (label, col) in enumerate(sources):
        sx = CX + i*(sbw+gap_s)
        rect(c, sx, sy0-sbh, sbw, sbh, col, r=4)
        txt(c, label, sx+sbw/2, sy0-sbh/2-4, "Helvetica-Bold", 8.5, WHITE, "center")
    txt(c, "Fontes de atualização de preço", CX, sy0+4, "Helvetica-Oblique", 8, MUTED)

    # Bus horizontal: stubs de cada fonte + linha coletora
    src_xs = [CX + i*(sbw+gap_s) + sbw/2 for i in range(len(sources))]
    bus_y = sy0 - sbh - 10
    c.setStrokeColor(LGRAY); c.setLineWidth(1.0)
    for sx_c in src_xs:
        c.line(sx_c, sy0-sbh, sx_c, bus_y)
    c.line(src_xs[0], bus_y, src_xs[-1], bus_y)

    # ── 2. Fluxo de preparação (Engenharia) ────────────────────────────────────
    flow = [
        ("Comparar com\ncatálogo atual",         BLUE2),
        ("Registrar:\nquem · quando · por quê",  BLUE2),
        ("Abrir rascunho\ndo catálogo",           BLUE2),
        ("Revisar impacto\nem composições",       BLUE2),
    ]
    fw, fh = 160, 44
    gap_f = (CW - len(flow)*fw) / (len(flow)-1)
    flow_ty = bus_y - 28  # topo dos boxes de fluxo

    # Conector L: centro do bus → cotovelo → centro do 1º passo
    el_y = bus_y - 12
    step1_cx = CX + fw/2
    c.setStrokeColor(BLUE); c.setLineWidth(1.2)
    c.line(MID, bus_y, MID, el_y)          # stub vertical
    c.line(MID, el_y, step1_cx, el_y)      # perna horizontal
    arrow(c, step1_cx, el_y, step1_cx, flow_ty, BLUE, lw=1.2)  # ↓ 1º passo

    for i, (label, col) in enumerate(flow):
        fx = CX + i*(fw+gap_f)
        rect(c, fx, flow_ty-fh, fw, fh, col, r=4)
        lines = label.split("\n")
        oy = flow_ty-12 if len(lines) > 1 else flow_ty-20
        for li, ln in enumerate(lines):
            txt(c, ln, fx+fw/2, oy-li*13,
                "Helvetica-Bold" if li == 0 else "Helvetica", 8.5, WHITE, "center")
        if i < len(flow)-1:
            arrow(c, fx+fw, flow_ty-fh/2, fx+fw+gap_f, flow_ty-fh/2, LGRAY, lw=1.2)

    txt(c, "← Preparado pela Engenharia", CX, flow_ty-fh-10,
        "Helvetica-Oblique", 8, ROLE_COLORS["engineer"])

    # ── 3. Aprovação — Quatro Olhos ────────────────────────────────────────────
    last_fcx = CX + (len(flow)-1)*(fw+gap_f) + fw/2

    # Conector L: último passo → cotovelo → MID → split
    el2_y = flow_ty - fh - 14
    split_y = el2_y - 14
    c.setStrokeColor(BLUE); c.setLineWidth(1.2)
    c.line(last_fcx, flow_ty-fh, last_fcx, el2_y)   # stub vertical
    c.line(last_fcx, el2_y, MID, el2_y)              # perna horizontal
    arrow(c, MID, el2_y, MID, split_y, BLUE, lw=1.2) # ↓ ponto de split

    ASEP = 160    # afastamento horizontal de cada aprovador a partir do MID
    FIG_SZ = 24
    apv_head_y  = split_y - 52              # topo das cabeças
    fig_feet_y  = apv_head_y - FIG_SZ*0.922
    apv_box_top = fig_feet_y - 6
    apv_box_bot = apv_box_top - 28

    for (apv_cx, role, lbl) in [(MID-ASEP, "cat-manager", "Suprimentos"),
                                  (MID+ASEP, "admin",       "TI")]:
        col = ROLE_COLORS[role]
        arrow(c, MID, split_y, apv_cx, apv_head_y, col, lw=1.0)   # split → figura
        txt(c, lbl, apv_cx, apv_head_y+10, "Helvetica-Bold", 8.5, col, "center")
        user_figure(c, apv_cx, fig_feet_y, sz=FIG_SZ, color=col, label="")
        arrow(c, apv_cx, fig_feet_y, apv_cx, apv_box_top, col, lw=0.9)
        rect(c, apv_cx-95, apv_box_bot, 190, 28, col, r=4)
        txt(c, "Aprova a publicação", apv_cx, apv_box_bot+10,
            "Helvetica-Bold", 8.5, WHITE, "center")

    # Legenda "Quatro Olhos" centralizada entre as figuras
    txt(c, "quem aprova  ≠  quem editou", MID,
        fig_feet_y + FIG_SZ*0.46, "Helvetica-Bold", 8, ORANGE, "center")

    # ── 4. Publicação ──────────────────────────────────────────────────────────
    pub_top = apv_box_bot - 32
    pub_h   = 44
    pub_bot = pub_top - pub_h

    arrow(c, MID-ASEP, apv_box_bot, MID, pub_top+2, GREEN, lw=1.0)
    arrow(c, MID+ASEP, apv_box_bot, MID, pub_top+2, GREEN, lw=1.0)

    rect(c, MID-230, pub_bot, 460, pub_h, GREEN, r=5)
    txt(c, "Nova versão do catálogo publicada",
        MID, pub_bot+pub_h-16, "Helvetica-Bold", 11, WHITE, "center")
    txt(c, "Projetos existentes permanecem isolados — só novos planos usam a nova versão",
        MID, pub_bot+pub_h-30, "Helvetica", 8.5, WHITE, "center")


def s_resumo(c):
    slide_frame(c, "Resumo Executivo", "Visao Geral", 2)
    bw = (CW - 20) / 2
    by = CB + 36
    bh = (CT - 16) - by
    labeled_box(c, CX, by, bw, bh, "O que entregamos", [
        "1.  Pipeline auditavel, do escopo ao resultado financeiro",
        "",
        "2.  Versionamento de planos, catálogo e BDI",
        "",
        "3.  Regras de custo e BDI formalizadas e reconciliadas",
        "",
        "4.  Cinco papeis de acesso e regra dos quatro olhos",
        "",
        "5.  Entrega de codigo separada da atualização de dados",
        "",
        "6.  Monitoramento fim a fim com testes automaticos",
        "",
        "7.  Exploracao de cenários para decisão de negocio",
    ], tsz=10, bsz=9.5)
    labeled_box(c, CX+bw+20, by, bw, bh, "Garantias do sistema", [
        "Reprodutibilidade",
        "   cada execução e fotografada e pode ser refeita",
        "",
        "Auditabilidade",
        "   trilha completa do salário ao preço de venda",
        "",
        "Isolamento",
        "   mudar o catálogo não quebra projetos existentes",
        "",
        "Otimização",
        "   o cronograma e calculado para minimizar o prazo",
        "",
        "Rastreabilidade",
        "   quem mudou o que, quando e por que",
        "",
        "Resiliencia",
        "   retorno automatico e seguro se algo falhar",
    ], title_bg=GREEN, tsz=10, bsz=9.5)
    rect(c, CX, CB+4, CW, 22, BLUE, r=3)
    txt(c, "Concilium — Orcamentacao de infraestrutura: auditavel, versionada e otimizada.",
        W/2, CB+11, "Helvetica-Bold", 10, WHITE, "center")


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD
# ═══════════════════════════════════════════════════════════════════════════════

def build():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "concilium-tech-overview.pdf")
    c = pdfcanvas.Canvas(out, pagesize=(W, H))
    slides = [
        s_title, s_resumo, s_interaction, s_deploy,
        s_pipeline, s_cronograma, s_pool_reuso, s_equipe_composição,
        s_pool_timeline, s_pool, s_regras_custo, s_bdi,
        s_versionado, s_catalogo,
        s_roles, s_matrix,
        s_workflow_op_eng, s_workflow_outros,
        s_handoffs, s_catalogo_update,
    ]
    for fn in slides:
        fn(c)
        c.showPage()
    c.save()
    print(f"PDF: {out}  ({len(slides)} slides,  {os.path.getsize(out)//1024}KB)")


if __name__ == "__main__":
    build()
