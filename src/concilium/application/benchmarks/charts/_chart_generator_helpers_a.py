"""Helpers extracted from chart_generator.py.

Gerador de gráficos PNG para benchmarks.

Integra a lógica de charts ao pipeline de benchmarks, invocável via
output_packager, CLI ou MCP. Requer matplotlib (dependência opcional).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ._chart_colors import _CORES, BG
from ._chart_shared import (
    _CRIT_COR,
    _EAP_DATA,
    _INDIR_COR_DATA,
    _INDIR_DATA,
    _TIMES_DATA,
    _ps_draw_deadline_makespan,
    _ps_draw_delta_cd,
    _ps_draw_insight,
    _ps_draw_pool_bars,
    _ps_draw_viabilidade,
)


def _chart_plan_space(plt, out_dir: Path, slug: str, cenarios: list, np) -> Path:
    fig = plt.figure(figsize=(18, 10), facecolor=BG)
    fig.suptitle(
        f"{slug.upper()} — Espaço de Plano (12 cenários MINSLK)",
        fontsize=13,
        fontweight="bold",
        color=_CORES["azul_escuro"],
        y=0.98,
    )
    gs = fig.add_gridspec(2, 3, hspace=0.45, wspace=0.35, left=0.07, right=0.97, top=0.92, bottom=0.08)
    labels = [c["slug"].split("_")[0] + "\n" + "_".join(c["slug"].split("_")[1:3]) for c in cenarios]
    x = np.arange(len(cenarios))
    _ps_draw_pool_bars(fig.add_subplot(gs[0, 0]), x, cenarios, "ESC3", 10, "Pool ESC-3CAT (crítico)", labels)
    _ps_draw_pool_bars(fig.add_subplot(gs[0, 1]), x, cenarios, "ATERRO", 5, "Pool ATERRO", labels)
    _ps_draw_deadline_makespan(fig.add_subplot(gs[0, 2]), x, cenarios, labels)
    _ps_draw_delta_cd(fig.add_subplot(gs[1, 0]), x, cenarios, labels)
    _ps_draw_viabilidade(fig.add_subplot(gs[1, 1]), x, cenarios, labels)
    _ps_draw_insight(fig.add_subplot(gs[1, 2]))
    p = out_dir / "02_plan_space.png"
    fig.savefig(p, dpi=180, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return p


def _chart_waterfall(plt, out_dir: Path, slug: str) -> Path:
    import matplotlib.ticker as mticker

    WF = [
        ("MO direto", 16934378, _CORES["azul"]),
        ("Diesel", 29837052, _CORES["teal"]),
        ("Custo Direto", 0, _CORES["azul_escuro"]),
        ("ADM", 13695825, _CORES["cinza_escuro"]),
        ("TOP", 858758, _CORES["cinza"]),
        ("LAB", 139568, _CORES["cinza"]),
        ("QSMS", 755778, _CORES["cinza"]),
        ("MOB", 4054600, _CORES["cinza"]),
        ("Custo Total", 0, _CORES["laranja"]),
        ("Margem", 10478021, _CORES["verde"]),
        ("Preço Venda", 0, _CORES["verde_claro"]),
    ]
    SUBS = {"Custo Direto": 46771430, "Custo Total": 66275960, "Preço Venda": 76753981}
    cumsum = 0
    bases = []
    heights = []
    lbls = []
    cors = []
    for nome, val, cor in WF:
        if nome in SUBS:
            bases.append(0)
            heights.append(SUBS[nome])
            cumsum = SUBS[nome]
        else:
            bases.append(cumsum)
            heights.append(val)
            cumsum += val
        lbls.append(nome)
        cors.append(cor)
    fig, ax = plt.subplots(figsize=(15, 7), facecolor=BG)
    fig.suptitle(f"{slug.upper()} — Cascata Financeira", fontsize=13, fontweight="bold", color=_CORES["azul_escuro"])
    for i, (b, h, cor, nome) in enumerate(zip(bases, heights, cors, lbls, strict=False)):
        is_sub = nome in SUBS
        ax.bar(
            i,
            h,
            bottom=b,
            color=cor,
            alpha=1.0 if is_sub else 0.85,
            edgecolor=_CORES["cinza_escuro"] if is_sub else cor,
            lw=1.5 if is_sub else 0.5,
            width=0.7,
        )
        ax.text(
            i,
            b + h + 0.3e6,
            f"R${(b + h) / 1e6:.1f}M",
            ha="center",
            va="bottom",
            fontsize=7.5,
            fontweight="bold" if is_sub else "normal",
            color=_CORES["cinza_escuro"],
        )
        if i < len(lbls) - 1 and lbls[i + 1] not in SUBS:
            ax.plot([i + 0.35, i + 0.65], [b + h, b + h], color=_CORES["cinza"], lw=0.8, ls="--", alpha=0.5)
    ax.set_xticks(range(len(lbls)))
    ax.set_xticklabels(lbls, rotation=18, ha="right", fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R${v / 1e6:.0f}M"))
    ax.set_ylim(0, 85e6)
    ax.text(
        9,
        66275960 + 10478021 / 2,
        "Margem: 13,65%\nStatus: VERDE",
        fontsize=9,
        color=_CORES["verde"],
        fontweight="bold",
        ha="center",
        va="center",
    )
    plt.tight_layout()
    p = out_dir / "03_waterfall_financeiro.png"
    fig.savefig(p, dpi=180, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return p


def _chart_eap_crit(plt, out_dir: Path, slug: str, np) -> Path:
    import matplotlib.patches as mpatches
    import matplotlib.ticker as mticker

    fig, ax = plt.subplots(figsize=(13, 8), facecolor=BG)
    fig.suptitle(
        f"{slug.upper()} — EAP: Custo × Criticidade × Ponto de Equilíbrio",
        fontsize=13,
        fontweight="bold",
        color=_CORES["azul_escuro"],
    )
    nomes = [d["nome"] for d in _EAP_DATA]
    custos = [d["custo"] / 1e6 for d in _EAP_DATA]
    pe_ops = [d["pe_op"] / 1e6 for d in _EAP_DATA]
    crits = [d["crit"] for d in _EAP_DATA]
    y = np.arange(len(nomes))
    ax.barh(y, custos, color=[_CRIT_COR[c] for c in crits], alpha=0.85, height=0.55, edgecolor="white", lw=0.5)
    for i, (pe, c) in enumerate(zip(pe_ops, custos, strict=False)):
        ax.plot(pe, y[i], marker="|", markersize=14, color=_CORES["cinza_escuro"], lw=2.5, zorder=5)
        if pe > c:
            ax.annotate(
                "",
                xy=(pe, y[i]),
                xytext=(c, y[i]),
                arrowprops=dict(arrowstyle="->", color=_CORES["vermelho"] + "70", lw=1),
            )
        ax.text(
            c + 0.1,
            y[i],
            f"R${c:.1f}M [{crits[i]}]",
            va="center",
            fontsize=8.5,
            color=_CORES["cinza_escuro"],
            fontweight="bold" if crits[i] == "A" else "normal",
        )
    ax.set_yticks(y)
    ax.set_yticklabels(nomes, fontsize=9)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R${v:.0f}M"))
    ax.invert_yaxis()
    handles2 = [mpatches.Patch(color=_CRIT_COR[k], label=f"Criticidade {k}") for k in ["A", "B", "C"]]
    handles2.append(
        plt.Line2D([0], [0], marker="|", color=_CORES["cinza_escuro"], markersize=12, lw=2.5, label="PE Operacional")
    )
    ax.legend(handles=handles2, fontsize=9, loc="lower right")
    plt.tight_layout()
    p = out_dir / "04_eap_criticidade.png"
    fig.savefig(p, dpi=180, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return p


def _chart_indiretos(plt, out_dir: Path, slug: str, np) -> Path:
    import matplotlib.ticker as mticker

    vals = list(_INDIR_DATA.values())
    lbls_d = list(_INDIR_DATA.keys())
    cors_d = [_INDIR_COR_DATA[k] for k in lbls_d]
    total = sum(vals)
    fig, (ax_pie, ax_bar) = plt.subplots(1, 2, figsize=(14, 7), facecolor=BG)
    fig.suptitle(
        f"{slug.upper()} — Custos Indiretos (R${total / 1e6:.1f}M total)",
        fontsize=13,
        fontweight="bold",
        color=_CORES["azul_escuro"],
    )
    wedges, texts, ats = ax_pie.pie(
        vals,
        labels=lbls_d,
        autopct=lambda p: f"{p:.1f}%",
        colors=cors_d,
        startangle=90,
        wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2),
        textprops=dict(fontsize=10),
    )
    [at.set_fontweight("bold") for at in ats]
    ax_pie.text(
        0,
        0,
        f"R${total / 1e6:.1f}M\nTotal Indir.",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color=_CORES["azul_escuro"],
    )
    ax_pie.set_title("Distribuição (%)", fontsize=11, pad=12)
    y_b = np.arange(len(lbls_d))
    bars_i = ax_bar.barh(y_b, [v / 1e6 for v in vals], color=cors_d, alpha=0.88, height=0.55, edgecolor="white")
    for i, (_bar, v) in enumerate(zip(bars_i, [v / 1e6 for v in vals], strict=False)):
        ax_bar.text(
            v + 0.1, y_b[i], f"R${v:.2f}M", va="center", fontsize=9.5, fontweight="bold", color=_CORES["cinza_escuro"]
        )
    ax_bar.set_yticks(y_b)
    ax_bar.set_yticklabels(lbls_d, fontsize=11)
    ax_bar.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R${v:.0f}M"))
    ax_bar.set_title("Valor Absoluto", fontsize=11, pad=12)
    ax_bar.invert_yaxis()
    plt.tight_layout()
    p = out_dir / "05_indiretos_composicao.png"
    fig.savefig(p, dpi=180, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return p


def _times_build_ax0(ax, y_t, tot_mes: list, cor_b: list, nomes_t: list, mticker) -> None:
    """Subplot 0: Custo Mensal (log) por time."""
    for i, (y, v, cor) in enumerate(zip(y_t, tot_mes, cor_b, strict=False)):
        ax.barh(
            y,
            v,
            color=cor,
            height=0.6,
            alpha=0.88,
            edgecolor="none",
            hatch=("////" if _TIMES_DATA[i]["sazonal"] else ""),
        )
        ax.text(
            v * 1.05,
            y,
            f"R${v:.0f}k{'★' if _TIMES_DATA[i]['sazonal'] else ''}",
            va="center",
            fontsize=8.5,
            color=_CORES["cinza_escuro"],
        )
    ax.set_xscale("log")
    ax.set_yticks(y_t)
    ax.set_yticklabels(nomes_t, fontsize=11)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R${v:.0f}k"))
    ax.set_title("Custo Mensal (log)", fontsize=11)
    ax.invert_yaxis()


def _times_build_ax1(ax, y_b2, nomes_b: list, mo_p: list, eq_p: list, vb_p: list) -> None:
    """Subplot 1: Breakdown % Custo por time permanente."""
    ax.barh(y_b2, mo_p, color=_CORES["azul"], height=0.6, label="MO")
    ax.barh(y_b2, eq_p, left=mo_p, color=_CORES["teal"], height=0.6, label="EQ")
    ax.barh(
        y_b2,
        vb_p,
        left=[m + e for m, e in zip(mo_p, eq_p, strict=False)],
        color=_CORES["cinza"],
        height=0.6,
        label="Verbas",
    )
    for i, (m, e, v) in enumerate(zip(mo_p, eq_p, vb_p, strict=False)):
        if m > 5:
            ax.text(m / 2, y_b2[i], f"{m:.0f}%", ha="center", va="center", fontsize=8, color="white", fontweight="bold")
        if e > 5:
            ax.text(
                m + e / 2, y_b2[i], f"{e:.0f}%", ha="center", va="center", fontsize=8, color="white", fontweight="bold"
            )
        if v > 5:
            ax.text(
                m + e + v / 2,
                y_b2[i],
                f"{v:.0f}%",
                ha="center",
                va="center",
                fontsize=8,
                color="white",
                fontweight="bold",
            )
    ax.set_yticks(y_b2)
    ax.set_yticklabels(nomes_b, fontsize=11)
    ax.set_title("Breakdown % Custo", fontsize=11)
    ax.legend(fontsize=9)
    ax.invert_yaxis()


def _times_build_ax2(ax, mticker) -> None:
    """Subplot 2: Headcount × Custo Total scatter."""
    for t in _TIMES_DATA:
        cor = _CORES["azul_escuro"] if not t["sazonal"] else _CORES["azul_claro"]
        mk = "^" if t["sazonal"] else "o"
        y_val = (t["custo_mo"] + t["custo_eq"] + t["verbas"]) * t["perm"] / 1e6
        ax.scatter(t["pessoas"], y_val, s=180, color=cor, marker=mk, zorder=5, edgecolors="white", lw=1.5)
        ax.annotate(
            t["nome"],
            xy=(t["pessoas"], y_val),
            xytext=(4, 6),
            textcoords="offset points",
            fontsize=9,
            color=_CORES["cinza_escuro"],
        )
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v)}p"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"R${v:.1f}M"))
    ax.set_title("Headcount × Custo Total Obra", fontsize=11)


def _compute_times_totaux(np):
    """Compute per-time series arrays for ax0 (all teams)."""
    nomes_t = [t["nome"] for t in _TIMES_DATA]
    tot_mes = [(t["custo_mo"] + t["custo_eq"] + t["verbas"]) / 1e3 for t in _TIMES_DATA]
    cor_b = [_CORES["azul_escuro"] if not t["sazonal"] else _CORES["azul_claro"] for t in _TIMES_DATA]
    y_t = np.arange(len(nomes_t))
    return nomes_t, tot_mes, cor_b, y_t


def _compute_perm_breakdown(np):
    """Compute breakdown % arrays for permanent teams (ax1)."""
    tb = [t for t in _TIMES_DATA if not t["sazonal"]]
    nomes_b = [t["nome"] for t in tb]
    tots = [t["custo_mo"] + t["custo_eq"] + t["verbas"] for t in tb]
    mo_p = [t["custo_mo"] / tots[i] * 100 for i, t in enumerate(tb)]
    eq_p = [t["custo_eq"] / tots[i] * 100 for i, t in enumerate(tb)]
    vb_p = [t["verbas"] / tots[i] * 100 for i, t in enumerate(tb)]
    y_b2 = np.arange(len(nomes_b))
    return nomes_b, mo_p, eq_p, vb_p, y_b2


def _chart_times(plt, out_dir: Path, slug: str, np) -> Path:
    import matplotlib.ticker as mticker

    fig, axes = plt.subplots(1, 3, figsize=(18, 7), facecolor=BG)
    fig.suptitle(f"{slug.upper()} — Times Indiretos", fontsize=13, fontweight="bold", color=_CORES["azul_escuro"])
    nomes_t, tot_mes, cor_b, y_t = _compute_times_totaux(np)
    nomes_b, mo_p, eq_p, vb_p, y_b2 = _compute_perm_breakdown(np)
    _times_build_ax0(axes[0], y_t, tot_mes, cor_b, nomes_t, mticker)
    _times_build_ax1(axes[1], y_b2, nomes_b, mo_p, eq_p, vb_p)
    _times_build_ax2(axes[2], mticker)
    plt.tight_layout()
    p = out_dir / "06_times_indiretos.png"
    fig.savefig(p, dpi=180, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return p


def _setup_matplotlib():
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.facecolor": BG,
            "axes.facecolor": BG,
            "axes.edgecolor": _CORES["cinza_claro"],
            "axes.grid": True,
            "grid.color": _CORES["cinza_claro"],
            "grid.linewidth": 0.7,
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlecolor": _CORES["azul_escuro"],
            "figure.dpi": 150,
        }
    )
    return plt


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}
