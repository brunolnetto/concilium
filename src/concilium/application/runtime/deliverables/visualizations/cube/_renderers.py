"""Pure chart renderers shared by cube face leaf modules.

Each function accepts a `plt` handle (already bootstrapped to Agg backend)
and returns a Figure or None. The caller is responsible for converting the
figure to bytes via ``fig_to_bytes`` from ``_common.init_mpl()``.
"""

from __future__ import annotations

from collections import defaultdict

from ..chart_markdown_support import weekly_to_monthly_labels
from ._common import COLORS, SERIE_LABEL_MAP, apply_monthly_ticks, col_label, get_column_id


def _stacked_bar_keys(columns: list[dict]) -> tuple[str, str, str, str | None]:
    """Resolve x/series/value keys and xlabel for render_stacked_bar.

    Supports x/series/value roles and heatmap-style x/y/value roles
    (categoria_componente, atividade_componente).
    """
    x_key_role = get_column_id(columns, "x")
    y_key_role = get_column_id(columns, "y")
    series_key_role = get_column_id(columns, "series")
    if y_key_role and not series_key_role:
        x_key = y_key_role
        series_key = x_key_role or "serie"
        xlabel = col_label(columns, y_key_role)
    else:
        x_key = x_key_role or "periodo"
        series_key = series_key_role or "serie"
        xlabel = col_label(columns, x_key_role)
    return x_key, series_key, xlabel, x_key_role


def _stacked_bar_absolute_panel(
    ax,
    x: list[int],
    labels: list[str],
    series_names: list[str],
    value_maps: dict[str, dict[str, float]],
    scale: float,
    title: str,
    use_millions: bool,
    xlabel: str | None,
    is_normalized_layout: bool,
) -> None:
    """Draw the absolute-values panel of render_stacked_bar."""
    baseline = [0.0] * len(labels)
    for idx, series_name in enumerate(series_names):
        values = [value_maps[series_name].get(lbl, 0.0) / scale for lbl in labels]
        lbl_display = SERIE_LABEL_MAP.get(series_name, series_name.replace("_", " "))
        ax.bar(x, values, bottom=baseline, alpha=0.85, label=lbl_display, color=COLORS[idx % len(COLORS)], width=0.7)
        baseline = [base + value for base, value in zip(baseline, values, strict=False)]
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_ylabel("R$ (Mi)" if use_millions else "Valor", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    if not is_normalized_layout:
        ax.set_xlabel(xlabel or "Item", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        apply_monthly_ticks(ax, labels, weekly_to_monthly_labels)
    else:
        ax.tick_params(bottom=False, labelbottom=False)


def _stacked_bar_normalized_panel(
    ax_norm,
    x: list[int],
    labels: list[str],
    series_names: list[str],
    value_maps: dict[str, dict[str, float]],
    xlabel: str | None,
) -> None:
    """Draw the 100%-normalised panel of render_stacked_bar."""
    totals = [sum(value_maps[s].get(lbl, 0.0) for s in series_names) for lbl in labels]
    baseline_pct = [0.0] * len(labels)
    for idx, series_name in enumerate(series_names):
        values_pct = [
            (value_maps[series_name].get(lbl, 0.0) / totals[i] * 100.0) if totals[i] else 0.0
            for i, lbl in enumerate(labels)
        ]
        ax_norm.bar(x, values_pct, bottom=baseline_pct, alpha=0.85, color=COLORS[idx % len(COLORS)], width=0.7)
        baseline_pct = [b + v for b, v in zip(baseline_pct, values_pct, strict=False)]
    ax_norm.set_ylim(0, 105)
    ax_norm.set_ylabel("Participacao (%)", fontsize=9)
    ax_norm.set_xlabel(xlabel or "Item", fontsize=9)
    ax_norm.set_title("Composicao Relativa (%)", fontsize=11, fontweight="bold")
    ax_norm.set_xticks(x)
    ax_norm.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    apply_monthly_ticks(ax_norm, labels, weekly_to_monthly_labels)
    ax_norm.grid(axis="y", alpha=0.3)


def _stacked_bar_annotate_bdi(fig, note_ax) -> None:
    """Add the BDI sigla legend below the stacked-bar chart."""
    sigla_note = (
        "Siglas BDI — AC: Adm.Central | DF: Desp.Fin. | R: Risco/Seg. | L: Lucro\n"
        "Tributos — ISS: Imp.Servicos | CSSL: C.Social | IR: Imp.Renda"
    )
    note_ax.annotate(
        sigla_note,
        xy=(0.5, -0.28),
        xycoords="axes fraction",
        ha="center",
        va="top",
        fontsize=7,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#f9f9f9", alpha=0.9, edgecolor="#cccccc"),
    )
    fig.subplots_adjust(bottom=0.22)


def _stacked_bar_prepare(
    rows: list[dict], columns: list[dict]
) -> tuple[list[str], list[str], dict[str, dict[str, float]], str | None] | None:
    """Resolve labels/series/value_maps/xlabel for render_stacked_bar, or None if empty."""
    value_key = get_column_id(columns, "value") or "valor_rs"
    x_key, series_key, xlabel, _x_key_role = _stacked_bar_keys(columns)
    labels = sorted({str(row.get(x_key, "")) for row in rows})
    series_names = sorted({str(row.get(series_key, "")) for row in rows})
    if not labels or not series_names:
        return None
    value_maps: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        value_maps[str(row.get(series_key, ""))][str(row.get(x_key, ""))] = float(row.get(value_key, 0.0) or 0.0)
    return labels, series_names, value_maps, xlabel


def render_stacked_bar(
    plt,
    rows: list[dict],
    columns: list[dict],
    title: str,
    use_millions: bool = False,
    show_normalized: bool = False,
    annotate_bdi: bool = False,
):
    """Stacked bar chart with optional 100% normalised subplot.

    Supports x/series/value roles and heatmap-style x/y/value roles
    (categoria_componente, atividade_componente).  When *show_normalized* is
    True a second subplot shows relative composition (%).  When *annotate_bdi*
    is True adds a BDI sigla legend below the chart.
    """
    prepared = _stacked_bar_prepare(rows, columns)
    if prepared is None:
        return None
    labels, series_names, value_maps, xlabel = prepared
    scale = 1e6 if use_millions else 1.0
    x = list(range(len(labels)))
    fig_w = max(8, len(labels) * 0.8 + 2)
    if show_normalized:
        fig, (ax, ax_norm) = plt.subplots(2, 1, figsize=(fig_w, 10))
    else:
        fig, ax = plt.subplots(figsize=(fig_w, 5))
        ax_norm = None
    _stacked_bar_absolute_panel(
        ax, x, labels, series_names, value_maps, scale, title, use_millions, xlabel, ax_norm is not None
    )
    if ax_norm is not None:
        _stacked_bar_normalized_panel(ax_norm, x, labels, series_names, value_maps, xlabel)
    if annotate_bdi:
        note_ax = ax_norm if ax_norm is not None else ax
        _stacked_bar_annotate_bdi(fig, note_ax)
    fig.tight_layout()
    return fig


def _stacked_area_value_map(
    rows: list[dict], x_key: str, series_key: str, value_key: str
) -> dict[str, dict[str, float]]:
    """Build the series->label->value map shared by the area renderers."""
    value_map: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        value_map[str(row.get(series_key, ""))][str(row.get(x_key, ""))] = float(row.get(value_key, 0) or 0)
    return value_map


def _stacked_area_absolute_panel(
    ax,
    x: list[int],
    labels: list[str],
    all_series: list[str],
    value_map: dict[str, dict[str, float]],
    scale: float,
    title: str,
    use_millions: bool,
) -> None:
    """Draw the absolute-values panel of render_stacked_area."""
    stack = [0.0] * len(labels)
    for idx, series_name in enumerate(all_series):
        values = [value_map[series_name].get(lbl, 0.0) / scale for lbl in labels]
        top = [base + v for base, v in zip(stack, values, strict=False)]
        col = COLORS[idx % len(COLORS)]
        lbl_display = SERIE_LABEL_MAP.get(series_name, series_name.replace("_", " "))
        ax.fill_between(x, top, stack, alpha=0.72, label=lbl_display, color=col)
        ax.plot(x, top, color=col, linewidth=0.9, alpha=0.5)
        stack = top
    ax.set_ylabel("R$ (Mi)" if use_millions else "Valor", fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0)
    ax.grid(axis="y", alpha=0.3)
    ax.set_xticks(x)
    ax.tick_params(labelbottom=False)


def _stacked_area_normalized_panel(
    ax_norm,
    x: list[int],
    labels: list[str],
    all_series: list[str],
    value_map: dict[str, dict[str, float]],
    totals: list[float],
) -> None:
    """Draw the 100%-normalised panel of render_stacked_area."""
    stack_pct = [0.0] * len(labels)
    for idx, series_name in enumerate(all_series):
        values_pct = [
            (value_map[series_name].get(lbl, 0.0) / totals[i] * 100.0) if totals[i] else 0.0
            for i, lbl in enumerate(labels)
        ]
        top_pct = [base + v for base, v in zip(stack_pct, values_pct, strict=False)]
        col = COLORS[idx % len(COLORS)]
        ax_norm.fill_between(x, top_pct, stack_pct, alpha=0.72, color=col)
        ax_norm.plot(x, top_pct, color=col, linewidth=0.9, alpha=0.5)
        stack_pct = top_pct
    ax_norm.set_ylim(0, 100)
    ax_norm.set_ylabel("Participacao (%)", fontsize=9)
    ax_norm.set_xlabel("Periodo", fontsize=9)
    ax_norm.set_title("Composicao Relativa (%)", fontsize=11, fontweight="bold")
    ax_norm.grid(axis="y", alpha=0.3)
    ax_norm.set_xticks(x)
    ax_norm.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    apply_monthly_ticks(ax_norm, labels, weekly_to_monthly_labels)


def _stacked_area_prepare(
    rows: list[dict], columns: list[dict]
) -> tuple[list[str], list[str], dict[str, dict[str, float]]] | None:
    """Resolve labels/all_series/value_map for the area renderers, or None if empty/no series."""
    x_key = get_column_id(columns, "x") or "periodo"
    series_key = get_column_id(columns, "series")
    value_key = get_column_id(columns, "value") or "valor_rs"
    if not series_key:
        return None
    labels = sorted({str(row.get(x_key, "")) for row in rows})
    all_series = sorted({str(row.get(series_key, "")) for row in rows})
    if not labels or not all_series:
        return None
    value_map = _stacked_area_value_map(rows, x_key, series_key, value_key)
    return labels, all_series, value_map


def render_stacked_area(
    plt,
    rows: list[dict],
    columns: list[dict],
    title: str,
    use_millions: bool = False,
):
    """Stacked area chart with 100% normalised subplot."""
    prepared = _stacked_area_prepare(rows, columns)
    if prepared is None:
        return None
    labels, all_series, value_map = prepared
    scale = 1e6 if use_millions else 1.0
    x = list(range(len(labels)))
    totals = [sum(value_map[s].get(lbl, 0.0) for s in all_series) for lbl in labels]
    fig, (ax, ax_norm) = plt.subplots(2, 1, figsize=(12, 10))
    _stacked_area_absolute_panel(ax, x, labels, all_series, value_map, scale, title, use_millions)
    _stacked_area_normalized_panel(ax_norm, x, labels, all_series, value_map, totals)
    fig.tight_layout()
    return fig


def _stacked_area_100pct_panel(
    ax,
    x: list[int],
    labels: list[str],
    all_series: list[str],
    value_map: dict[str, dict[str, float]],
    totals: list[float],
    title: str,
) -> None:
    """Draw the single normalised panel of render_stacked_area_100pct."""
    stack = [0.0] * len(labels)
    for idx, series_name in enumerate(all_series):
        values = [
            (value_map[series_name].get(lbl, 0.0) / totals[i] * 100.0) if totals[i] else 0.0
            for i, lbl in enumerate(labels)
        ]
        top = [base + v for base, v in zip(stack, values, strict=False)]
        col = COLORS[idx % len(COLORS)]
        lbl_display = SERIE_LABEL_MAP.get(series_name, series_name.replace("_", " "))
        ax.fill_between(x, top, stack, alpha=0.72, label=lbl_display, color=col)
        ax.plot(x, top, color=col, linewidth=0.9, alpha=0.5)
        stack = top
    ax.set_ylim(0, 100)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    apply_monthly_ticks(ax, labels, weekly_to_monthly_labels)
    ax.set_ylabel("Participacao (%)", fontsize=9)
    ax.set_xlabel("Periodo", fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1), borderaxespad=0)
    ax.grid(axis="y", alpha=0.3)


def render_stacked_area_100pct(
    plt,
    rows: list[dict],
    columns: list[dict],
    title: str,
    use_millions: bool = False,
):
    """Single 100%-normalised stacked area chart."""
    prepared = _stacked_area_prepare(rows, columns)
    if prepared is None:
        return None
    labels, all_series, value_map = prepared
    x = list(range(len(labels)))
    totals = [sum(value_map[s].get(lbl, 0.0) for s in all_series) for lbl in labels]
    fig, ax = plt.subplots(figsize=(12, 5))
    _stacked_area_100pct_panel(ax, x, labels, all_series, value_map, totals, title)
    fig.tight_layout()
    return fig


def _line_bar_multi_series(
    ax, rows: list[dict], labels: list[str], x_key: str, series_key: str, value_key: str, liter_scale: float
) -> None:
    """Draw one line per series for render_line_bar."""
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        grouped[str(row.get(series_key, "serie"))][str(row.get(x_key, ""))] = (
            float(row.get(value_key, 0.0) or 0.0) / liter_scale
        )
    for idx, (series_name, value_map) in enumerate(sorted(grouped.items())):
        points = [value_map.get(label, 0.0) for label in labels]
        ax.plot(
            list(range(len(labels))),
            points,
            linewidth=2,
            marker="o",
            markersize=4,
            label=series_name,
            color=COLORS[idx % len(COLORS)],
        )
    ax.legend(fontsize=8)


def _line_bar_single_series(
    ax, rows: list[dict], labels: list[str], x_key: str, value_key: str, liter_scale: float
) -> None:
    """Draw a single bar series for render_line_bar."""
    points = [
        float(next((row.get(value_key, 0.0) for row in rows if str(row.get(x_key, "")) == label), 0.0) or 0.0)
        / liter_scale
        for label in labels
    ]
    ax.bar(list(range(len(labels))), points, color="#1a3a5c", alpha=0.85, width=0.8)


def _line_bar_prepare(
    rows: list[dict], columns: list[dict]
) -> tuple[str, str | None, str, str | None, bool, float, list[str]] | None:
    """Resolve keys/labels/scale for render_line_bar, or None if there's nothing to plot."""
    x_key = get_column_id(columns, "x") or "periodo"
    series_key = get_column_id(columns, "series")
    value_key = get_column_id(columns, "value")
    if not value_key:
        return None
    value_col_label = col_label(columns, value_key)
    is_liters = "diesel" in (value_key or "").lower() or "(l)" in (value_col_label or "").lower()
    liter_scale = 1000.0 if is_liters else 1.0
    labels = sorted({str(row.get(x_key, "")) for row in rows})
    if not labels:
        return None
    return x_key, series_key, value_key, value_col_label, is_liters, liter_scale, labels


def render_line_bar(
    plt,
    rows: list[dict],
    columns: list[dict],
    title: str,
    use_millions: bool = False,
):
    """Generic line/bar chart — used for faces like diesel_temporal."""
    prepared = _line_bar_prepare(rows, columns)
    if prepared is None:
        return None
    x_key, series_key, value_key, value_col_label, is_liters, liter_scale, labels = prepared
    fig, ax = plt.subplots(figsize=(12, 5))
    if series_key:
        _line_bar_multi_series(ax, rows, labels, x_key, series_key, value_key, liter_scale)
    else:
        _line_bar_single_series(ax, rows, labels, x_key, value_key, liter_scale)
    ax.set_xticks(list(range(len(labels))))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    apply_monthly_ticks(ax, labels, weekly_to_monthly_labels)
    ax.set_ylabel("Volume (kL)" if is_liters else value_col_label, fontsize=9)
    ax.set_xlabel("Periodo", fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig
