"""pool_ciclo_vida.png — Ciclo de Vida das Instâncias de Pool (Gantt de mobilização).

Cada linha é um slot de recurso (ex: ESC-3CAT-03). A barra colorida vai da semana
de mobilização à de desmobilização, dividida em prod (verde) + idle (âmbar).
Semanas OFF ficam fora da barra — o espaço vazio expressa a mobilização tardia.
"""

from __future__ import annotations

from ._common import init_mpl

_COLOR_PROD = "#1a6e3c"
_COLOR_IDLE = "#e8a030"


def _iget(d, key):
    return int(d.get(key) or 0)


def _fget(d, key):
    return float(d.get(key) or 0.0)


def _try_project(canonical):
    try:
        from concilium.application.services.analytics.cubo_pool_projection import resolve_cubo_pool_projection

        proj = resolve_cubo_pool_projection(canonical, face="instancia_ciclo_vida", granularidade="mes", top_n=100)
        return proj.get("rows") or []
    except Exception:
        return []


def _try_init_mpl():
    try:
        return init_mpl()
    except ImportError:
        return None


def _draw_row(ax, idx, r):
    prod_w = _iget(r, "prod_w")
    idle_w = _iget(r, "idle_w")
    off_w = _iget(r, "off_w")
    total_w = prod_w + idle_w + off_w
    ax.barh(idx, prod_w, left=off_w, height=0.55, color=_COLOR_PROD, alpha=0.85)
    # Barra idle (após prod — simplificação visual; idle real pode ser intercalado)
    if idle_w:
        ax.barh(idx, idle_w, left=off_w + prod_w, height=0.55, color=_COLOR_IDLE, alpha=0.85)
    custo = _fget(r, "custo_total")
    label = f"R$ {custo / 1e6:.1f}M" if custo >= 1e6 else f"R$ {custo / 1e3:.0f}k"
    ax.text(total_w + 0.3, idx, label, va="center", fontsize=7.5, color="#333")


def _setup_axes(ax, n, rows):
    from matplotlib.patches import Patch

    labels = [str(r.get("instancia_id", "")) for r in reversed(rows)]
    ax.set_yticks(list(range(n)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Semanas de contrato (OFF + PROD + IDLE)", fontsize=9)
    ax.set_title(
        "Ciclo de Vida das Instâncias de Pool\n(sem. off = mob. tardia; amarelo = ocioso CLT+EQ; verde = produtivo)",
        fontsize=11,
        fontweight="bold",
    )
    legend_elems = [
        Patch(facecolor=_COLOR_IDLE, alpha=0.85, label="Ocioso (CLT integral + EQ reduzida)"),
        Patch(facecolor=_COLOR_PROD, alpha=0.85, label="Produtivo"),
        Patch(facecolor="white", edgecolor="#aaa", label="Off (desmobilizado, custo 0)"),
    ]
    ax.legend(handles=legend_elems, fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.25)


def _render_chart(plt, fig_to_bytes, rows):
    try:
        n = min(len(rows), 20)  # limita a 20 instâncias para legibilidade
        rows = rows[:n]
        fig_height = max(4, 0.5 * n + 2)
        fig, ax = plt.subplots(figsize=(13, fig_height))
        for idx, r in enumerate(reversed(rows)):
            _draw_row(ax, idx, r)
        _setup_axes(ax, n, rows)
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None


def build(canonical, cubo=None) -> bytes | None:
    rows = _try_project(canonical)
    if not rows:
        return None
    mpl = _try_init_mpl()
    if mpl is None:
        return None
    return _render_chart(*mpl, rows)
