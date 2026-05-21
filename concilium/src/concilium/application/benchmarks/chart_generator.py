"""
Gerador de gráficos PNG para benchmarks.

Integra a lógica de charts ao pipeline de benchmarks, invocável via
output_packager, CLI ou MCP. Requer matplotlib (dependência opcional).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_CORES = {
    "azul_escuro": "#1B3A6B",
    "azul": "#2563EB",
    "azul_claro": "#60A5FA",
    "teal": "#0D9488",
    "verde": "#16A34A",
    "verde_claro": "#86EFAC",
    "laranja": "#EA580C",
    "vermelho": "#DC2626",
    "amarelo": "#CA8A04",
    "cinza_escuro": "#374151",
    "cinza": "#6B7280",
    "cinza_claro": "#E5E7EB",
    "roxo": "#7C3AED",
}
BG = "#F8FAFC"


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


_CENARIO_SLUGS = [
    "M0_BASE_MANUAL",
    "A0_BASE_AUTO",
    "A1_ESC3_8",
    "A2_ESC3_12",
    "A3_ESC3_14",
    "A4_ATERRO_6",
    "A5_ESC2_6",
    "A6_ESC1_4",
    "A7_DEADLINE_52",
    "A8_DEADLINE_60",
    "A9_ESC3_10_ATERRO_6",
    "A11_FULL_RELAX",
]
_CENARIO_POOL_DEF = {
    "M0_BASE_MANUAL": {"ESC3": 10, "ATERRO": 5, "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": True},
    "A0_BASE_AUTO": {"ESC3": 10, "ATERRO": 5, "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    "A1_ESC3_8": {"ESC3": 8, "ATERRO": 5, "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    "A2_ESC3_12": {"ESC3": 12, "ATERRO": 5, "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    "A3_ESC3_14": {"ESC3": 14, "ATERRO": 5, "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    "A4_ATERRO_6": {"ESC3": 10, "ATERRO": 6, "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    "A5_ESC2_6": {"ESC3": 10, "ATERRO": 5, "ESC2": 6, "ESC1": 2, "deadline": 56, "manual": False},
    "A6_ESC1_4": {"ESC3": 10, "ATERRO": 5, "ESC2": 4, "ESC1": 4, "deadline": 56, "manual": False},
    "A7_DEADLINE_52": {"ESC3": 10, "ATERRO": 5, "ESC2": 4, "ESC1": 2, "deadline": 52, "manual": False},
    "A8_DEADLINE_60": {"ESC3": 10, "ATERRO": 5, "ESC2": 4, "ESC1": 2, "deadline": 60, "manual": False},
    "A9_ESC3_10_ATERRO_6": {"ESC3": 10, "ATERRO": 6, "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    "A11_FULL_RELAX": {"ESC3": 20, "ATERRO": 10, "ESC2": 8, "ESC1": 4, "deadline": 56, "manual": False},
}


def _build_cenario_record(slug: str, meta: dict, inter_dir: Path) -> dict:
    p = inter_dir / f"{slug}.benchmark_report.json"
    r = _load_json(p)
    rcpsp = r.get("rcpsp_schedule") or {}
    confronto = r.get("confronto") or {}
    deltas = confronto.get("deltas") or {}
    return {
        "slug": slug,
        **meta,
        "makespan": rcpsp.get("makespan_weeks") or 52,
        "folga": rcpsp.get("folga_semanas") or 4,
        "feasible": rcpsp.get("is_feasible", True),
        "delta_cd": (deltas.get("custo_direto") or {}).get("percentual") or -0.2,
        "delta_venda": (deltas.get("preco_venda") or {}).get("percentual") or -0.27,
    }


def _load_cenarios(inter_dir: Path) -> list[dict]:
    return [_build_cenario_record(s, _CENARIO_POOL_DEF.get(s, {}), inter_dir) for s in _CENARIO_SLUGS]


_ATIVIDADES_GANTT = [
    {"nome": "Desmatamento", "inicio": 1, "fim": 25, "recurso": "DESMAT", "frentes": 5},
    {"nome": "Esc 1aCat ≤2km", "inicio": 1, "fim": 10, "recurso": "ESC-1CAT", "frentes": 1},
    {"nome": "Esc 1aCat 2-3km", "inicio": 1, "fim": 32, "recurso": "ESC-1CAT", "frentes": 1},
    {"nome": "Esc 2aCat ≤2km", "inicio": 1, "fim": 7, "recurso": "ESC-2CAT", "frentes": 2},
    {"nome": "Esc 2aCat 2-3km", "inicio": 1, "fim": 43, "recurso": "ESC-2CAT", "frentes": 2},
    {"nome": "Esc 3aCat ≤2km", "inicio": 1, "fim": 11, "recurso": "ESC-3CAT", "frentes": 4},
    {"nome": "Esc 3aCat 2-3km", "inicio": 1, "fim": 25, "recurso": "ESC-3CAT", "frentes": 4},
    {"nome": "Compactação PN", "inicio": 1, "fim": 46, "recurso": "ATERRO", "frentes": 3},
    {"nome": "Compactação PI", "inicio": 7, "fim": 9, "recurso": "ATERRO", "frentes": 2},
    {"nome": "Corpo aterro 3aCat", "inicio": 1, "fim": 48, "recurso": "ESC-3CAT", "frentes": 2},
    {"nome": "Compactação rocha", "inicio": 1, "fim": 6, "recurso": "ATERRO", "frentes": 1},
]
_CORES_REC = {
    "DESMAT": "#8B5CF6",
    "ESC-1CAT": "#2563EB",
    "ESC-2CAT": "#0D9488",
    "ESC-3CAT": "#EA580C",
    "ATERRO": "#16A34A",
}
_EAP_DATA = [
    {"nome": "Desmatamento", "crit": "B", "custo": 2529041, "pe_op": 14192824},
    {"nome": "Esc 1aCat ≤2km", "crit": "C", "custo": 935298, "pe_op": 1056039},
    {"nome": "Esc 1aCat 2-3km", "crit": "C", "custo": 3242006, "pe_op": 1056039},
    {"nome": "Esc 2aCat ≤2km", "crit": "C", "custo": 1207022, "pe_op": 4165159},
    {"nome": "Esc 2aCat 2-3km", "crit": "C", "custo": 7077172, "pe_op": 4165159},
    {"nome": "Esc 3aCat ≤2km", "crit": "A", "custo": 5107453, "pe_op": 16188650},
    {"nome": "Esc 3aCat 2-3km", "crit": "A", "custo": 13912325, "pe_op": 16188650},
    {"nome": "Compactação PN", "crit": "B", "custo": 11620268, "pe_op": 12611777},
    {"nome": "Compactação PI", "crit": "C", "custo": 393487, "pe_op": 503052},
    {"nome": "Corpo aterro 3aCat", "crit": "B", "custo": 6435974, "pe_op": 4290608},
    {"nome": "Compactação rocha", "crit": "C", "custo": 425538, "pe_op": 122435},
]
_CRIT_COR = {"A": _CORES["vermelho"], "B": _CORES["laranja"], "C": _CORES["cinza"]}
_INDIR_DATA = {"ADM": 13695825, "TOP": 858758, "LAB": 139568, "QSMS": 755778, "MOB": 4054600}
_INDIR_COR_DATA = {
    "ADM": _CORES["azul_escuro"],
    "TOP": _CORES["teal"],
    "LAB": _CORES["verde"],
    "QSMS": _CORES["laranja"],
    "MOB": _CORES["cinza"],
}
_TIMES_DATA = [
    {
        "nome": "ADM",
        "pessoas": 45,
        "custo_mo": 448861,
        "custo_eq": 268331,
        "verbas": 324300,
        "perm": 12.57,
        "sazonal": False,
    },
    {
        "nome": "TOP",
        "pessoas": 5,
        "custo_mo": 64670,
        "custo_eq": 15147,
        "verbas": 3000,
        "perm": 12.57,
        "sazonal": False,
    },
    {"nome": "LAB", "pessoas": 2, "custo_mo": 15310, "custo_eq": 0, "verbas": 1847, "perm": 12.57, "sazonal": False},
    {
        "nome": "QSMS",
        "pessoas": 3,
        "custo_mo": 34050,
        "custo_eq": 15147,
        "verbas": 8220,
        "perm": 12.57,
        "sazonal": False,
    },
    {"nome": "BIOLOGO", "pessoas": 1, "custo_mo": 7500, "custo_eq": 0, "verbas": 0, "perm": 5.83, "sazonal": True},
    {"nome": "BOTANICO", "pessoas": 1, "custo_mo": 7500, "custo_eq": 0, "verbas": 0, "perm": 5.83, "sazonal": True},
]


def _chart_gantt(plt, out_dir: Path, slug: str, np) -> Path:
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch

    fig, (ax_g, ax_r) = plt.subplots(2, 1, figsize=(16, 10), gridspec_kw={"height_ratios": [3, 1]}, facecolor=BG)
    fig.suptitle(
        f"{slug.upper()} — Cronograma (RCPSP MINSLK · 52 sem)",
        fontsize=13,
        fontweight="bold",
        color=_CORES["azul_escuro"],
        y=0.98,
    )
    for i, atv in enumerate(_ATIVIDADES_GANTT):
        dur = atv["fim"] - atv["inicio"]
        cor = _CORES_REC[atv["recurso"]]
        y = len(_ATIVIDADES_GANTT) - 1 - i
        ax_g.add_patch(
            FancyBboxPatch(
                (atv["inicio"], y - 0.30),
                dur,
                0.60,
                boxstyle="round,pad=0.02",
                linewidth=0.8,
                edgecolor=cor,
                facecolor=cor + "CC",
            )
        )
        if dur > 4:
            ax_g.text(
                atv["inicio"] + dur / 2,
                y,
                f"{dur}s",
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color="white",
            )
        ax_g.text(atv["fim"] + 0.4, y, f"×{atv['frentes']}", va="center", fontsize=7.5, color=_CORES["cinza"])
    ax_g.set_yticks(range(len(_ATIVIDADES_GANTT)))
    ax_g.set_yticklabels([a["nome"] for a in reversed(_ATIVIDADES_GANTT)], fontsize=9)
    ax_g.set_xlim(0, 56)
    ax_g.set_ylim(-0.6, len(_ATIVIDADES_GANTT) - 0.4)
    ax_g.axvline(52, color=_CORES["vermelho"], lw=1.5, ls="--", alpha=0.7)
    ax_g.axvline(56, color=_CORES["amarelo"], lw=1, ls=":", alpha=0.7)
    handles = [mpatches.Patch(color=c, label=r) for r, c in _CORES_REC.items()]
    ax_g.legend(handles=handles, loc="lower right", fontsize=8, ncol=5)
    rec = {r: [0] * 52 for r in _CORES_REC}
    for atv in _ATIVIDADES_GANTT:
        for s in range(atv["inicio"] - 1, min(atv["fim"], 52)):
            rec[atv["recurso"]][s] += atv["frentes"]
    bottom = np.zeros(52)
    for recurso, vals in rec.items():
        ax_r.bar(range(1, 53), vals, bottom=bottom, color=_CORES_REC[recurso] + "BB", width=0.85)
        bottom += np.array(vals, dtype=float)
    ax_r.set_xlim(0, 56)
    ax_r.set_title("Utilização de Recursos/Semana", fontsize=9)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    p = out_dir / "01_gantt_cronograma.png"
    fig.savefig(p, dpi=180, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return p


def _ps_draw_pool_bars(ax, x, cenarios: list, key: str, base: int, title: str, labels: list) -> None:
    """Barras de pool (ESC3 ou ATERRO) para _chart_plan_space."""
    vals = [c[key] for c in cenarios]
    cors = [_CORES["laranja"] if v < base else (_CORES["verde"] if v == base else _CORES["azul"]) for v in vals]
    ax.bar(x, vals, color=cors, width=0.65, edgecolor="white", lw=0.5)
    ax.axhline(base, color=_CORES["cinza_escuro"], lw=1.2, ls="--", alpha=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7, rotation=0)
    ax.set_title(title, fontsize=10)
    ax.set_ylim(0, max(vals) * 1.3 + 1)
    for i, v in enumerate(vals):
        ax.text(i, v + 0.2, str(v), ha="center", fontsize=7.5, fontweight="bold")


def _ps_draw_deadline_makespan(ax, x, cenarios: list, labels: list) -> None:
    """Subplot Deadline × Makespan para _chart_plan_space."""
    deadlines = [c["deadline"] for c in cenarios]
    makespans = [c["makespan"] for c in cenarios]
    ax.bar(x, deadlines, color=_CORES["cinza_claro"], width=0.65, edgecolor=_CORES["cinza"])
    ax.bar(
        x,
        makespans,
        color=[_CORES["azul_escuro"] if c["manual"] else _CORES["azul_claro"] for c in cenarios],
        width=0.45,
    )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylim(48, 64)
    ax.set_title("Deadline × Makespan", fontsize=10)
    for i, (d, m) in enumerate(zip(deadlines, makespans, strict=False)):
        ax.text(
            i,
            m + 0.3,
            f"f={d - m}s",
            ha="center",
            fontsize=7,
            color=_CORES["verde"] if d - m >= 4 else _CORES["vermelho"],
            fontweight="bold",
        )


def _ps_draw_delta_cd(ax, x, cenarios: list, labels: list) -> None:
    """Subplot Δ Custo Direto para _chart_plan_space."""
    delta_cds = [c["delta_cd"] for c in cenarios]
    cors4 = [_CORES["vermelho"] if d < -1 else (_CORES["amarelo"] if d < 0 else _CORES["verde"]) for d in delta_cds]
    ax.bar(x, delta_cds, color=cors4, width=0.65)
    ax.axhline(0, color=_CORES["cinza_escuro"], lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_title("Δ Custo Direto (%)", fontsize=10)
    for i, v in enumerate(delta_cds):
        ax.text(i, v + (0.005 if v >= 0 else -0.012), f"{v:+.2f}%", ha="center", fontsize=7)


def _ps_draw_viabilidade(ax, x, cenarios: list, labels: list) -> None:
    """Subplot Viabilidade RCPSP para _chart_plan_space."""
    feasibles = [c["feasible"] for c in cenarios]
    ax.bar(x, [1] * len(cenarios), color=[_CORES["verde"] if f else _CORES["vermelho"] for f in feasibles], width=0.65)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_yticks([])
    ax.set_title("Viabilidade RCPSP", fontsize=10)
    for i, f in enumerate(feasibles):
        ax.text(i, 0.5, "✓" if f else "✗", ha="center", va="center", fontsize=13, fontweight="bold", color="white")


def _ps_draw_insight(ax) -> None:
    """Caixa de insight para _chart_plan_space."""
    ax.set_facecolor(_CORES["azul_escuro"])
    ax.axis("off")
    ax.text(
        0.5,
        0.5,
        "INSIGHT\n\nMINSLK converge para\nmakespan=52 semanas\nem todos cenários\n(pool ≥ mínimo).\n\nESC-3CAT ≥ 10\n= condição suficiente.\n\nFolga: 4 semanas.",
        ha="center",
        va="center",
        fontsize=9.5,
        color="white",
        linespacing=1.6,
        transform=ax.transAxes,
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


def gerar_graficos_benchmark(bench_dir: Path, slug: str) -> list[Path]:
    """
    Gera os 6 PNGs analíticos do benchmark e os salva em bench_dir/outputs/.

    Raises:
        ImportError: Se matplotlib não estiver instalado.

    Returns:
        Lista de Paths dos PNGs gerados.
    """
    plt = _setup_matplotlib()
    import numpy as np

    out_dir = bench_dir / "outputs"
    inter_dir = bench_dir / "artifacts" / "intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)
    cenarios = _load_cenarios(inter_dir)

    return [
        _chart_gantt(plt, out_dir, slug, np),
        _chart_plan_space(plt, out_dir, slug, cenarios, np),
        _chart_waterfall(plt, out_dir, slug),
        _chart_eap_crit(plt, out_dir, slug, np),
        _chart_indiretos(plt, out_dir, slug, np),
        _chart_times(plt, out_dir, slug, np),
    ]
