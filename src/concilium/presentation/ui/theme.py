"""Identidade visual Concilium — MendesLobo Construtora.

CSS injetado a cada rerun (st.markdown é efêmero por design).
Suporta tema light (corporativo) e dark (baixa luminosidade).
Tokens CSS custom properties garantem cobertura de todos os componentes.
"""

from __future__ import annotations

import streamlit as st

# ── Paletas ───────────────────────────────────────────────────────────────────

_LIGHT = """\
    --ml-bg:          #F7F8FC;
    --ml-panel:       #FFFFFF;
    --ml-ink:         #1A3A5C;
    --ml-muted:       #5B6878;
    --ml-border:      #D1D9E6;
    --ml-row-alt:     #F0F5FA;
    --ml-navy-lt:     #EBF2FA;
    --ml-input-bg:    #FFFFFF;
    --ml-select-bg:   #FFFFFF;
    --ml-verde-lt:    #DCEEE5;
    --ml-verm-lt:     #FADDDD;
    --ml-amar-lt:     #FEF3C7;
    --ml-verde:       #276749;
    --ml-vermelho:    #9B1C1C;
    --ml-amarelo:     #92400E;
    color-scheme: light;"""

_DARK = """\
    --ml-bg:          #0D1520;
    --ml-panel:       #152030;
    --ml-ink:         #EAF1FA;
    --ml-muted:       #9BB5CC;
    --ml-border:      #2E4A68;
    --ml-row-alt:     #1A2D40;
    --ml-navy-lt:     #1E3550;
    --ml-input-bg:    #1A2D40;
    --ml-select-bg:   #1A2D40;
    --ml-verde-lt:    #1B3A2A;
    --ml-verm-lt:     #3A1C1C;
    --ml-amar-lt:     #3A2A10;
    --ml-verde:       #68D391;
    --ml-vermelho:    #FC8181;
    --ml-amarelo:     #F6AD55;
    color-scheme: dark;"""

_SHARED = """\
    --ml-navy:        #1A3A5C;
    --ml-navy-md:     #2B6CB0;
    --ml-orange:      #C05C18;
    --ml-orange-lt:   #F5E6D8;
    --ml-font:        'IBM Plex Sans', system-ui, sans-serif;
    --ml-mono:        'IBM Plex Mono', 'Fira Code', monospace;
    --ml-ease:        cubic-bezier(0.22, 1, 0.36, 1);
    --ml-dur-sm:      180ms;
    --ml-dur-md:      260ms;"""


def _css(theme: str) -> str:
    palette = _DARK if theme == "dark" else _LIGHT
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* ── Design tokens ──────────────────────────────────────────────────────── */
:root {{
    {_SHARED}
    {palette}
}}

/* ── Base ────────────────────────────────────────────────────────────────── */
html, body, .stApp, [data-testid="stAppViewContainer"] {{
    font-family: var(--ml-font) !important;
    background-color: var(--ml-bg) !important;
    color: var(--ml-ink) !important;
}}
.stApp > div {{ background-color: var(--ml-bg) !important; }}

/* ── Sidebar ────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div {{ background: var(--ml-panel) !important; border-right: 2px solid var(--ml-border) !important; }}
[data-testid="stSidebar"] * {{ font-family: var(--ml-font) !important; color: var(--ml-ink); }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: var(--ml-navy) !important; }}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {{ padding: 0 !important; gap: 0 !important; }}

/* ── Marca MENDES LOBO ───────────────────────────────────────────────────── */
[data-testid="stSidebar"]::before {{
    content: "MENDES LOBO";
    display: block;
    padding: 0.75rem 1rem 0.5rem;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    color: var(--ml-orange);
    border-bottom: 1px solid var(--ml-border);
    margin-bottom: 0.5rem;
}}

/* ── Sidebar header custom ──────────────────────────────────────────────── */
.ml-sidebar-header {{
    display: flex;
    align-items: center;
    padding: 0.25rem 0 0.5rem;
}}
.ml-sidebar-logo {{
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--ml-navy);
}}

/* ── Navegação: botões nav no sidebar ───────────────────────────────────── */
/* Botão ativo (primary) já tem estilo navy preenchido da regra global.    */
/* Botões inativos (secondary): remover borda, deixar discreto.            */
[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
    border: 1px solid var(--ml-border) !important;
    border-radius: 8px !important;
    padding: 0.55rem 0.9rem !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    color: var(--ml-muted) !important;
    background: transparent !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {{
    background: var(--ml-navy-lt) !important;
    border-color: var(--ml-navy) !important;
    color: var(--ml-navy) !important;
    border-left: 3px solid var(--ml-orange) !important;
    padding-left: 0.7rem !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: var(--ml-navy-lt) !important;
    border: none !important;
    border-left: 3px solid var(--ml-orange) !important;
    border-radius: 8px !important;
    padding: 0.55rem 0.7rem !important;
    font-size: 0.9rem !important;
    font-weight: 700 !important;
    color: var(--ml-navy) !important;
    text-align: left !important;
    justify-content: flex-start !important;
}}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
    background: var(--ml-navy-lt) !important;
    transform: none !important;
    box-shadow: none !important;
}}

/* Contexto do projeto ativo */
.ml-project-ctx {{
    padding: 0.6rem 0.9rem;
    border-radius: 8px;
    background: var(--ml-navy-lt);
    border-left: 3px solid var(--ml-orange);
    margin: 0.25rem 0;
}}
.ml-project-ctx-name {{ font-weight: 700; color: var(--ml-navy); font-size: 0.9rem; }}
.ml-project-ctx-meta {{ color: var(--ml-muted); font-size: 0.75rem; margin-top: 0.2rem; }}
.ml-project-ctx-meta code {{ font-family: var(--ml-mono); font-size: 0.75em; background: var(--ml-border); padding: 0.05em 0.3em; border-radius: 3px; }}

/* ── Botões — padrão semântico ──────────────────────────────────────────── */
/* primary = salvar / criar / executar / confirmar exclusão              */
/* secondary = carregar / comparar / filtrar / navegar / cancelar        */
.stButton > button, .stFormSubmitButton > button {{
    font-family: var(--ml-font) !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
    padding: 0.4rem 1.1rem !important;
    transition: all var(--ml-dur-sm) var(--ml-ease) !important;
    font-size: 0.875rem !important;
    letter-spacing: 0.01em !important;
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
    background: var(--ml-navy) !important;
    border: 1.5px solid var(--ml-navy) !important;
    color: #FFFFFF !important;
}}
.stButton > button[kind="primary"]:hover {{
    background: var(--ml-navy-md) !important;
    border-color: var(--ml-navy-md) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 3px 12px rgba(26,58,92,0.22) !important;
}}
.stButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondary"] {{
    background: transparent !important;
    border: 1.5px solid var(--ml-border) !important;
    color: var(--ml-ink) !important;
}}
.stButton > button[kind="secondary"]:hover {{
    background: var(--ml-navy-lt) !important;
    border-color: var(--ml-navy-md) !important;
    color: var(--ml-navy) !important;
}}

/* ── Tipografia ─────────────────────────────────────────────────────────── */
h1, h2, h3, h4 {{ font-family: var(--ml-font) !important; font-weight: 700 !important; color: var(--ml-navy) !important; letter-spacing: -0.01em; }}
p, li, label, .stMarkdown {{ font-family: var(--ml-font) !important; color: var(--ml-ink); line-height: 1.6; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: var(--ml-muted) !important; font-size: 0.8rem !important; }}
code, pre {{ font-family: var(--ml-mono) !important; background: var(--ml-navy-lt) !important; border-radius: 3px; padding: 0.1em 0.3em; color: var(--ml-ink) !important; }}

/* ── Métricas ───────────────────────────────────────────────────────────── */
[data-testid="stMetricValue"] {{ font-size: clamp(1.1rem, 2vw, 1.6rem) !important; font-weight: 700 !important; color: var(--ml-navy) !important; }}
[data-testid="stMetricLabel"] {{ font-size: 0.75rem !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ml-muted) !important; }}
[data-testid="stMetricContainer"] {{ background: var(--ml-panel) !important; }}

/* ── Abas ────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] {{ background: transparent !important; }}
[data-testid="stTabs"] [data-baseweb="tab-list"] {{ gap: 0.125rem !important; border-bottom: 2px solid var(--ml-border) !important; background: transparent !important; }}
[data-testid="stTabs"] [data-baseweb="tab"] {{ border-radius: 6px 6px 0 0 !important; font-family: var(--ml-font) !important; font-weight: 500 !important; font-size: 0.85rem !important; color: var(--ml-muted) !important; padding: 0.5rem 1rem !important; background: transparent !important; transition: all var(--ml-dur-sm) var(--ml-ease) !important; }}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {{ color: var(--ml-navy) !important; background: var(--ml-navy-lt) !important; }}
[data-testid="stTabs"] [aria-selected="true"] {{ color: var(--ml-navy) !important; font-weight: 700 !important; background: var(--ml-navy-lt) !important; border-bottom: 2px solid var(--ml-orange) !important; }}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {{ background: transparent !important; color: var(--ml-ink) !important; }}

/* ── DataFrames ─────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{ border-radius: 8px !important; border: 1px solid var(--ml-border) !important; }}
/* Nota: não sobrescrever internals do AG Grid — interfere na renderização das células */

/* ── Inputs / Select / Textarea ─────────────────────────────────────────── */
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea {{
    background-color: var(--ml-input-bg) !important;
    color: var(--ml-ink) !important;
    border-color: var(--ml-border) !important;
    border-radius: 6px !important;
}}
[data-baseweb="input"]:focus-within, [data-baseweb="select"]:focus-within {{
    border-color: var(--ml-navy-md) !important;
    box-shadow: 0 0 0 3px rgba(43,108,176,0.15) !important;
}}
[data-baseweb="select"] [data-baseweb="select-container"],
[data-baseweb="select"] {{ background-color: var(--ml-select-bg) !important; color: var(--ml-ink) !important; border-color: var(--ml-border) !important; border-radius: 6px !important; }}
[data-baseweb="select"] div {{ color: var(--ml-ink) !important; background-color: var(--ml-select-bg) !important; }}
[data-baseweb="popover"] ul, [data-baseweb="menu"] {{ background-color: var(--ml-panel) !important; border: 1px solid var(--ml-border) !important; }}
[data-baseweb="menu"] li, [data-baseweb="menu"] li:hover {{ background-color: var(--ml-navy-lt) !important; color: var(--ml-ink) !important; }}
[data-baseweb="slider"] [data-testid="stSlider"] {{ color: var(--ml-navy) !important; }}
.stNumberInput input, .stTextInput input, .stTextArea textarea {{
    background-color: var(--ml-input-bg) !important;
    color: var(--ml-ink) !important;
    border-color: var(--ml-border) !important;
}}
.stMultiSelect [data-baseweb="tag"] {{ background-color: var(--ml-navy-lt) !important; color: var(--ml-navy) !important; }}

/* ── Alertas / Info boxes ───────────────────────────────────────────────── */
[data-testid="stInfo"]    {{ background: var(--ml-navy-lt) !important; border-left: 4px solid var(--ml-navy-md) !important; border-radius: 0 6px 6px 0 !important; color: var(--ml-ink) !important; }}
[data-testid="stWarning"] {{ background: var(--ml-amar-lt) !important; border-left: 4px solid var(--ml-amarelo) !important; color: var(--ml-ink) !important; }}
[data-testid="stSuccess"] {{ background: var(--ml-verde-lt) !important; border-left: 4px solid var(--ml-verde) !important; color: var(--ml-ink) !important; }}
[data-testid="stError"]   {{ background: var(--ml-verm-lt) !important; border-left: 4px solid var(--ml-vermelho) !important; color: var(--ml-ink) !important; }}

/* ── Expander ───────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    border: 1px solid var(--ml-border) !important;
    border-radius: 8px !important;
    background: var(--ml-panel) !important;
}}
[data-testid="stExpander"] summary {{
    font-weight: 600 !important;
    color: var(--ml-navy) !important;
    background: var(--ml-panel) !important;
}}
[data-testid="stExpander"] > div {{ background: var(--ml-panel) !important; }}
/* Botões dentro de expanders herdam o mesmo estilo semântico da regra global.  */
/* Força override para garantir que o tema prevaleça sobre estilos default do   */
/* Streamlit que possam sobrescrever dentro de containers aninhados.             */
[data-testid="stExpander"] .stButton > button[kind="primary"],
[data-testid="stExpander"] .stFormSubmitButton > button[kind="primary"] {{
    background: var(--ml-navy) !important;
    border: 1.5px solid var(--ml-navy) !important;
    color: #FFFFFF !important;
}}
[data-testid="stExpander"] .stButton > button[kind="secondary"],
[data-testid="stExpander"] .stFormSubmitButton > button[kind="secondary"] {{
    background: transparent !important;
    border: 1.5px solid var(--ml-border) !important;
    color: var(--ml-ink) !important;
}}

/* ── Container / Block ──────────────────────────────────────────────────── */
[data-testid="stVerticalBlock"], [data-testid="stHorizontalBlock"] {{ background: transparent !important; }}
.stContainer, [data-testid="stBlock"] {{ background: var(--ml-panel) !important; border-radius: 8px; }}
div[data-testid="stContainer"] {{ background: var(--ml-panel) !important; border: 1px solid var(--ml-border) !important; border-radius: 8px !important; padding: 1rem !important; }}

/* ── Divider ────────────────────────────────────────────────────────────── */
hr, [data-testid="stDivider"] {{ border-color: var(--ml-border) !important; }}

/* ── Radio / Checkbox (non-sidebar) ────────────────────────────────────── */
.stRadio label, .stCheckbox label {{ color: var(--ml-ink) !important; }}

/* ── Componentes customizados ───────────────────────────────────────────── */
.ui-page-hero {{
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
    border-left: 4px solid var(--ml-orange);
    background: linear-gradient(135deg, var(--ml-navy-lt) 0%, var(--ml-panel) 100%);
    border-radius: 0 8px 8px 0;
}}
.ui-page-hero h1, .ui-page-hero h2 {{ margin: 0 0 0.25rem; font-size: 1.35rem !important; }}
.ui-page-hero p {{ margin: 0; color: var(--ml-muted) !important; font-size: 0.85rem; }}
.ui-app-hero {{
    padding: 1.5rem 0 1rem;
    border-bottom: 1px solid var(--ml-border);
    margin-bottom: 1.5rem;
}}
.ui-app-hero h1 {{ font-size: clamp(1.4rem, 2.5vw, 1.9rem) !important; font-weight: 800 !important; color: var(--ml-navy) !important; }}
.ui-app-hero p {{ color: var(--ml-muted) !important; font-size: 0.9rem; margin: 0; }}
.ui-kpi-card {{ background: var(--ml-panel); border: 1px solid var(--ml-border); border-radius: 10px; padding: 1rem 1.25rem; }}
.ui-table-title {{ font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ml-muted); margin-bottom: 0.5rem; }}
.ui-badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.7rem; font-weight: 700; }}
.ui-badge-verde    {{ background: var(--ml-verde-lt);  color: var(--ml-verde);    }}
.ui-badge-amarelo  {{ background: var(--ml-amar-lt);   color: var(--ml-amarelo);  }}
.ui-badge-vermelho {{ background: var(--ml-verm-lt);   color: var(--ml-vermelho); }}
.ui-badge-navy     {{ background: var(--ml-navy-lt);   color: var(--ml-navy);     }}

/* ── Animações ──────────────────────────────────────────────────────────── */
@keyframes ml-fade-up  {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@keyframes ml-fade-in  {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }} }}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar {{ width: 6px; height: 6px; }}
::-webkit-scrollbar-track {{ background: var(--ml-bg); }}
::-webkit-scrollbar-thumb {{ background: var(--ml-border); border-radius: 999px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--ml-navy-md); }}
</style>"""


def apply_visual_identity(theme: str = "light") -> None:
    """Inject MendesLobo visual identity CSS with full dark/light support.

    Args:
        theme: "light" (default) or "dark"
    """
    st.markdown(_css(theme), unsafe_allow_html=True)
