"""Histogramas de recursos: equipamentos e mão de obra."""

from __future__ import annotations

from ..chart_markdown_support import weekly_to_monthly_labels
from ._common import HIST_COLORS, clean_series_label, init_mpl


def _plot_stacked_breakdown(ax, x: list[int], labels: list[str], breakdown: dict) -> None:
    """Desenha barras empilhadas por série (ex.: tipo de equipamento, função)."""
    series_names = sorted(breakdown.keys())
    baseline = [0.0] * len(labels)
    for sidx, sname in enumerate(series_names):
        svals = [float(v) if v is not None else 0.0 for v in breakdown[sname]]
        svals = (svals + [0.0] * len(labels))[: len(labels)]
        raw_label = clean_series_label(sname)
        display_label = raw_label if len(raw_label) <= 22 else raw_label[:21] + "\u2026"
        ax.bar(
            x,
            svals,
            bottom=baseline,
            alpha=0.85,
            width=0.8,
            label=display_label,
            color=HIST_COLORS[sidx % len(HIST_COLORS)],
        )
        baseline = [b + v for b, v in zip(baseline, svals, strict=False)]
    ax.legend(fontsize=7, loc="upper right")


def _style_hist_axes(ax, display_labels: list[str], title: str, ylabel: str, n_values: int) -> None:
    """Aplica títulos, ticks e grid ao eixo do histograma."""
    tick_positions = [i for i, lbl in enumerate(display_labels) if lbl != "."]
    tick_labels = [lbl for lbl in display_labels if lbl != "."]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xlabel("Período", fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    ax.set_xlim(-0.5, n_values - 0.5)


def _build_hist(
    section: dict,
    title: str,
    ylabel: str,
    base_color: str,
    by_key: str,
) -> bytes | None:
    labels = [str(lbl) for lbl in section.get("labels", [])]
    values = [float(v) if v is not None else 0.0 for v in section.get("values", [])]
    if not labels or not values:
        return None
    display_labels = weekly_to_monthly_labels(labels)
    breakdown = section.get(by_key)
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    try:
        fig, ax = plt.subplots(figsize=(14, 5))
        x = list(range(len(values)))
        if breakdown and isinstance(breakdown, dict):
            _plot_stacked_breakdown(ax, x, labels, breakdown)
        else:
            ax.bar(x, values, color=base_color, alpha=0.85, width=0.8)
        _style_hist_axes(ax, display_labels, title, ylabel, len(values))
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None


def build_hist_equipamentos(graficos: dict) -> bytes | None:
    section = graficos.get("equipamentos") or {}
    if not isinstance(section, dict):
        return None
    return _build_hist(section, "Histograma de Equipamentos", "Unidades", "#1a3a5c", "by_type")


def build_hist_mao_obra(graficos: dict) -> bytes | None:
    section = graficos.get("mao_obra") or {}
    if not isinstance(section, dict):
        return None
    return _build_hist(section, "Histograma de Mao de Obra", "Pessoas", "#c05c18", "by_funcao")
