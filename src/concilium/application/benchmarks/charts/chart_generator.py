"""
Gerador de gráficos PNG para benchmarks.

Integra a lógica de charts ao pipeline de benchmarks, invocável via
output_packager, CLI ou MCP. Requer matplotlib (dependência opcional).
"""

from __future__ import annotations

from pathlib import Path

from ._chart_colors import _CORES
from ._chart_generator_helpers_a import (
    _chart_eap_crit,
    _chart_indiretos,
    _chart_plan_space,
    _chart_times,
    _chart_waterfall,
    _setup_matplotlib,
)
from ._chart_generator_helpers_b import (
    _chart_gantt,
    _load_cenarios,
)

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
