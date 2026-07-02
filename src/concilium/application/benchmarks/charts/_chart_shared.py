"""Dados e helpers compartilhados entre os módulos de chart de benchmark.

Estas definições existiam no chart_generator.py original e foram perdidas
quando os helpers foram extraídos para _chart_generator_helpers_a/b.py
(commit 104db64) — restauradas aqui a partir do histórico (d1b6282).
"""

from __future__ import annotations

import json
from pathlib import Path

from ._chart_colors import _CORES


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
        "INSIGHT\n\nMINSLK converge para\nmakespan=52 semanas\nem todos cenários\n(pool ≥ mínimo).\n\n"
        "ESC-3CAT ≥ 10\n= condição suficiente.\n\nFolga: 4 semanas.",
        ha="center",
        va="center",
        fontsize=9.5,
        color="white",
        linespacing=1.6,
        transform=ax.transAxes,
    )
