"""bar_atividade_componente.png — Composição de Custo por Atividade.

Barras horizontais empilhadas [Custo operacional, Overhead BDI, Lucro (L), Tributos],
ordenadas por custo total decrescente, com regiões A/B/C da curva ABC.
"""

from __future__ import annotations

from collections import defaultdict

from ._common import build_payload, init_mpl, safe_close_mpl

# Ordem e cores dos componentes (base → topo)
_COMPS = ["Custo operacional", "Overhead BDI", "Lucro (L)", "Tributos"]
_COLORS = {
    "Custo operacional": "#1a3a5c",
    "Overhead BDI": "#5aabdc",
    "Lucro (L)": "#e8a030",
    "Tributos": "#c05c18",
}
# Limiares ABC (acumulado do total)
_ABC_A = 0.70  # 70% acumulado → Classe A
_ABC_B = 0.90  # 90% acumulado → Classe B  (B = 70–90%)
# C = restante (90–100%)


def build(canonical, cubo) -> bytes | None:
    try:
        payload = build_payload("atividade_componente", "mes", 80, canonical, cubo)
    except Exception:
        return None
    rows = payload.get("rows") or []
    if not rows:
        return None

    try:
        plt, fig_to_bytes = init_mpl()
        fig = _render(plt, rows)
        return fig_to_bytes(fig) if fig is not None else None
    except Exception:
        safe_close_mpl()
        return None


def _aggregate_by_atividade_componente(rows: list) -> tuple[dict[str, dict[str, float]], dict[str, float], list[str]]:
    """Agrega valores por atividade/componente e ordena atividades por total decrescente."""
    by_atv: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        atv = str(r.get("atividade_id", "?"))
        comp = str(r.get("componente_bdi", "?"))
        by_atv[atv][comp] += float(r.get("valor_rs", 0.0) or 0.0)

    totals = {a: sum(v.values()) for a, v in by_atv.items()}
    atividades = sorted(totals, key=lambda a: -totals[a])
    return by_atv, totals, atividades


def _compute_abc_classes(
    atividades: list[str], totals: dict[str, float], grand_total: float
) -> tuple[dict[str, str], int, int]:
    """Classifica cada atividade em A/B/C pelo acumulado do total e retorna os índices de corte."""
    acum = 0.0
    abc_class: dict[str, str] = {}
    for a in atividades:
        acum += totals[a]
        pct = acum / grand_total if grand_total > 0 else 0.0
        if pct <= _ABC_A:
            abc_class[a] = "A"
        elif pct <= _ABC_B:
            abc_class[a] = "B"
        else:
            abc_class[a] = "C"

    cut_ab = next((i for i, a in enumerate(atividades) if abc_class[a] == "B"), len(atividades))
    cut_bc = next((i for i, a in enumerate(atividades) if abc_class[a] == "C"), len(atividades))
    return abc_class, cut_ab, cut_bc


def _draw_stacked_bars(
    ax, by_atv: dict[str, dict[str, float]], atividades: list[str], y_pos: list[int], scale: float
) -> list[float]:
    """Desenha as barras horizontais empilhadas por componente e retorna os limites direitos."""
    lefts = [0.0] * len(atividades)
    for comp in _COMPS:
        vals = [by_atv[a].get(comp, 0.0) / scale for a in atividades]
        ax.barh(y_pos, vals, left=lefts, color=_COLORS[comp], label=comp, height=0.65, alpha=0.88)
        lefts = [ln + v for ln, v in zip(lefts, vals, strict=False)]
    return lefts


def _draw_abc_regions(ax, cut_ab: int, cut_bc: int, n: int, max_val: float) -> None:
    """Desenha as faixas de fundo, linhas de corte e labels das regiões ABC."""
    ax.axhspan(-0.5, cut_ab - 0.5, color="#1a3a5c", alpha=0.06, zorder=0)
    ax.axhspan(cut_ab - 0.5, cut_bc - 0.5, color="#e8a030", alpha=0.06, zorder=0)
    ax.axhspan(cut_bc - 0.5, n - 0.5, color="#c05c18", alpha=0.04, zorder=0)

    for cut in (cut_ab, cut_bc):
        if 0 < cut < n:
            ax.axhline(cut - 0.5, color="#555", linewidth=1.2, linestyle="--", alpha=0.6, zorder=4)

    for start, end, label, color in [
        (0, cut_ab, "A", "#1a3a5c"),
        (cut_ab, cut_bc, "B", "#e8a030"),
        (cut_bc, n, "C", "#c05c18"),
    ]:
        if start < end:
            mid = (start + end - 1) / 2
            ax.text(
                max_val * 1.10,
                mid,
                label,
                ha="center",
                va="center",
                fontsize=13,
                fontweight="bold",
                color=color,
                alpha=0.75,
            )


def _annotate_bar_totals(
    ax, atividades: list[str], totals: dict[str, float], lefts: list[float], max_val: float, scale: float
) -> None:
    """Anota o custo total (em milhões) ao final de cada barra."""
    for i, a in enumerate(atividades):
        tot = totals[a] / scale
        ax.text(lefts[i] + max_val * 0.005, i, f"{tot:.2f} Mi", va="center", ha="left", fontsize=7.5, color="#333")


def _build_atividade_yaxis_labels(atividades: list[str], abc_class: dict[str, str]) -> list[str]:
    """Constrói os labels do eixo Y combinando a classe ABC e o nome curto da atividade."""
    labels = []
    for a in atividades:
        cls = abc_class[a]
        short = a.replace("direto.", "").replace("indireto.", "ind.")
        labels.append(f"[{cls}] {short}")
    return labels


def _build_legend_patches(mpatches):
    """Monta os patches de legenda para componentes de custo e classes ABC."""
    comp_patches = [mpatches.Patch(color=_COLORS[c], label=c) for c in _COMPS]
    abc_patches = [
        mpatches.Patch(color="#1a3a5c", alpha=0.25, label=f"Classe A (≤{_ABC_A * 100:.0f}% acum.)"),
        mpatches.Patch(color="#e8a030", alpha=0.25, label=f"Classe B ({_ABC_A * 100:.0f}–{_ABC_B * 100:.0f}%)"),
        mpatches.Patch(color="#c05c18", alpha=0.20, label=f"Classe C (>{_ABC_B * 100:.0f}%)"),
    ]
    return comp_patches + abc_patches


def _render(plt, rows: list):
    import warnings

    import matplotlib.patches as mpatches

    # ── Agregar por atividade e componente ────────────────────────────────────
    by_atv, totals, atividades = _aggregate_by_atividade_componente(rows)
    grand_total = sum(totals.values())

    # ── Calcular regiões ABC ──────────────────────────────────────────────────
    abc_class, cut_ab, cut_bc = _compute_abc_classes(atividades, totals, grand_total)

    scale = 1e6
    n = len(atividades)
    y_pos = list(range(n))

    fig_h = max(5.0, n * 0.52 + 1.5)
    fig, ax = plt.subplots(figsize=(13, fig_h))

    # ── Barras empilhadas horizontais ─────────────────────────────────────────
    lefts = _draw_stacked_bars(ax, by_atv, atividades, y_pos, scale)

    # ── Regiões ABC com linhas tracejadas e labels ────────────────────────────
    # Desenhar as barras primeiro, depois ajustar xlim para labels
    max_val = max(max(lefts), 1e-9) if lefts else 1.0
    ax.set_xlim(0, max_val * 1.12)
    _draw_abc_regions(ax, cut_ab, cut_bc, n, max_val)

    # ── Anotações de custo total por barra ────────────────────────────────────
    _annotate_bar_totals(ax, atividades, totals, lefts, max_val, scale)

    # ── Eixo Y: labels de atividade ───────────────────────────────────────────
    labels = _build_atividade_yaxis_labels(atividades, abc_class)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.invert_yaxis()

    ax.set_xlabel("R$ (Mi)", fontsize=9)
    ax.set_title("Composição de Custo por Atividade (Curva ABC)", fontsize=12, fontweight="bold")
    ax.grid(axis="x", alpha=0.25)

    # Legenda componentes + ABC
    ax.legend(handles=_build_legend_patches(mpatches), fontsize=7.5, loc="lower right", ncol=2)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        fig.tight_layout()
    return fig
