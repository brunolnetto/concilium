"""Helpers extracted from chart_generator.py.

Gerador de gráficos PNG para benchmarks.

Integra a lógica de charts ao pipeline de benchmarks, invocável via
output_packager, CLI ou MCP. Requer matplotlib (dependência opcional).
"""

from __future__ import annotations

from pathlib import Path

from ._chart_colors import _CORES, BG


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
