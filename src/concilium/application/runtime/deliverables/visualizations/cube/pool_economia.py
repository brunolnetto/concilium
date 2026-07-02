"""pool_economia.png — Economia do Pool vs. Baseline Homogênea por Atividade.

Exibe baseline homogênea do planejamento (sem BDI) vs. custo instancial (pool compartilhado)
por atividade. O delta negativo indica overhead de ociosidade; o positivo indica economia
real de compartilhamento. Sempre mostra o baseline para honestidade (ADR-086 H4).
"""

from __future__ import annotations

import numpy as np

from ._common import init_mpl

_COLOR_AUT = "#1a3a5c"  # azul escuro — baseline homogênea
_COLOR_INST = "#5aabdc"  # azul claro — instancial (pool)
_COLOR_POS = "#1a6e3c"  # verde — economia positiva
_COLOR_NEG = "#c05c18"  # laranja — overhead (pool mais caro)


def build(canonical, cubo=None) -> bytes | None:
    try:
        from concilium.application.services.analytics.cubo_pool_projection import resolve_cubo_pool_projection

        proj = resolve_cubo_pool_projection(canonical, face="economia_pool", top_n=30)
    except Exception:
        return None

    rows = proj.get("rows") or []
    if not rows:
        return None
    # Filtra atividades sem baseline
    rows = [r for r in rows if float(r.get("custo_autonomo", 0.0) or 0.0) > 0]
    if not rows:
        return None

    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        n = min(len(rows), 15)
        rows = rows[:n]

        labels = [str(r.get("atividade_id", "")) for r in rows]
        aut = [float(r.get("custo_autonomo", 0.0) or 0.0) / 1e3 for r in rows]
        inst = [float(r.get("custo_instancial", 0.0) or 0.0) / 1e3 for r in rows]
        eco = [float(r.get("economia", 0.0) or 0.0) / 1e3 for r in rows]

        x = np.arange(n)
        w = 0.35
        fig, (ax_bars, ax_eco) = plt.subplots(2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

        ax_bars.bar(x - w / 2, aut, w, color=_COLOR_AUT, alpha=0.85, label="Baseline homogênea")
        ax_bars.bar(x + w / 2, inst, w, color=_COLOR_INST, alpha=0.85, label="Instancial (pool)")
        ax_bars.set_ylabel("Custo (R$ k)", fontsize=9)
        ax_bars.set_title(
            "Origem da Economia do Pool por Atividade\n(comparação entre baseline homogênea e instancial)",
            fontsize=11,
            fontweight="bold",
        )
        ax_bars.legend(fontsize=9)
        ax_bars.grid(axis="y", alpha=0.3)

        colors_eco = [_COLOR_NEG if v < 0 else _COLOR_POS for v in eco]
        ax_eco.bar(x, eco, color=colors_eco, alpha=0.85)
        ax_eco.axhline(0, color="#888", linewidth=0.8)
        ax_eco.set_ylabel("Δ (R$ k)", fontsize=9)
        ax_eco.grid(axis="y", alpha=0.3)

        ax_eco.set_xticks(x)
        ax_eco.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax_eco.set_xlabel("Atividade", fontsize=9)

        # Anotação de pct no gráfico de barras
        for xi, (a, ins, e) in enumerate(zip(aut, inst, eco, strict=False)):
            pct = (e / a * 100) if a > 0 else 0
            col = _COLOR_POS if pct >= 0 else _COLOR_NEG
            ax_bars.text(xi, max(a, ins) * 1.02, f"{pct:+.1f}%", ha="center", fontsize=7, color=col, fontweight="bold")

        om = proj.get("operator_meta", {})
        tot_aut = om.get("custo_autonomo_total", 0.0)
        tot_inst = om.get("custo_instancial_total", 0.0)
        tot_inst_prod = om.get("custo_instancial_produtivo_total", 0.0)
        tot_burden = om.get("burden_pool_total", 0.0)
        tot_eco = om.get("economia_total", 0.0)
        tot_eco_prod = om.get("economia_produtiva_total", 0.0)
        top_pos = [r for r in rows if float(r.get("economia", 0.0) or 0.0) > 0][:3]
        top_neg = [r for r in rows if float(r.get("economia", 0.0) or 0.0) < 0][:2]
        origem_tokens = [f"{r.get('atividade_id')}: +R$ {float(r.get('economia', 0.0)) / 1e3:.0f}k" for r in top_pos]
        origem_tokens += [f"{r.get('atividade_id')}: R$ {float(r.get('economia', 0.0)) / 1e3:.0f}k" for r in top_neg]
        origem_txt = " | ".join(origem_tokens) if origem_tokens else "Sem economia positiva relevante por atividade."
        fig.text(
            0.01,
            0.01,
            f"Baseline homogênea: R$ {tot_aut / 1e6:.2f}M  |  Instancial: R$ {tot_inst / 1e6:.2f}M  |  "
            f"Economia líquida: R$ {tot_eco / 1e6:.2f}M",
            fontsize=8,
            color="#555",
            ha="left",
        )
        fig.text(
            0.01,
            0.022,
            f"Instancial produtivo: R$ {tot_inst_prod / 1e6:.2f}M  |  "
            f"Burden pool (ocioso+mob/demob): R$ {tot_burden / 1e6:.2f}M  |  "
            f"Economia produtiva: R$ {tot_eco_prod / 1e6:.2f}M",
            fontsize=7.7,
            color="#555",
            ha="left",
        )
        fig.text(0.01, 0.035, f"Origem da economia: {origem_txt}", fontsize=7.5, color="#555", ha="left")

        fig.tight_layout(rect=(0, 0.08, 1, 1))
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
