"""pool_custo_estado.png — Custo do Pool por Estado × Componente.

Evidencia a diferença de composição de custo entre estado produtivo (todos os
componentes) e ocioso (MO integral obrigatório por CLT + EQ a taxa de locação
reduzida; combustível e material zerados sem operação).
"""

from __future__ import annotations

from ._common import COLORS, init_mpl

_COMP_LABELS = {"mo": "MO (CLT)", "eq": "Equip.", "comb": "Combustível", "mat": "Material"}
_ESTADO_LABELS = {"prod": "Produtivo", "idle": "Ocioso", "off": "Desmobilizado"}


def build(canonical, cubo=None) -> bytes | None:
    try:
        from concilium.application.services.cubo_pool_projection import resolve_cubo_pool_projection
        proj = resolve_cubo_pool_projection(canonical, face="custo_estado_componente")
    except Exception:
        return None

    rows = proj.get("rows") or []
    if not rows:
        return None

    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        # Constrói matriz: estado → {comp → valor}
        from collections import defaultdict
        matrix: dict[str, dict[str, float]] = defaultdict(dict)
        for r in rows:
            estado = r.get("estado", "")
            comp = r.get("componente", "")
            val = float(r.get("valor_rs", 0.0) or 0.0)
            matrix[estado][comp] = val

        estados = [e for e in ("Produtivo", "Ocioso") if e in matrix and sum(matrix[e].values()) > 0]
        if not estados:
            return None

        comps = list(_COMP_LABELS.values())
        comp_keys = list(_COMP_LABELS.keys())

        fig, ax = plt.subplots(figsize=(9, 5))
        bar_width = 0.35
        x = list(range(len(estados)))
        bottoms = [0.0] * len(estados)

        for ci, (comp_key, comp_label) in enumerate(zip(comp_keys, comps)):
            vals = [matrix[e].get(comp_label, matrix[e].get(comp_key, 0.0)) / 1e6 for e in estados]
            ax.bar(x, vals, bar_width, bottom=bottoms, color=COLORS[ci % len(COLORS)],
                   alpha=0.85, label=comp_label)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        ax.set_xticks(x)
        ax.set_xticklabels(estados, fontsize=10)
        ax.set_ylabel("Custo (R$ M)", fontsize=10)
        ax.set_title("Custo do Pool por Estado × Componente\n"
                     "(ocioso = MO integral CLT + EQ locação reduzida; comb/mat = 0)",
                     fontsize=11, fontweight="bold")
        ax.legend(fontsize=9)
        ax.grid(axis="y", alpha=0.3)

        narrativa = (proj.get("narrativa") or [])
        for i, n_txt in enumerate(narrativa[:2]):
            fig.text(0.02, -0.04 - i * 0.05, n_txt, fontsize=7.5, color="#555",
                     transform=ax.transAxes, ha="left")

        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
