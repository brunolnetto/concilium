"""scurve_custo.png — S-Curve de Custo Operacional.

Subplot 1 (barras): custo mensal por categoria com legenda "{Natureza} - {Categoria}".
Subplot 2 (stack): custo acumulado como duas bandas — Direto Acumulado + Indireto Acumulado.
"""

from __future__ import annotations

from collections import defaultdict

from ._common import COLORS, init_mpl
from concilium.application.services.cube_projection_views import (
    _indireto_component_shares,
    _iter_scaled_cubo_cells,
)


_CAT_LABELS = {
    "mao_obra": "Direto - Mão de Obra",
    "equipamento": "Direto - Equipamentos",
    "diesel": "Direto - Combustível",
    "material": "Direto - Material",
    "indireto_mao_obra": "Indireto - Mão de Obra",
    "indireto_equipamento": "Indireto - Equipamentos",
    "indireto_verbas": "Indireto - Verbas",
}
_CAT_DIRECT = ["mao_obra", "equipamento", "diesel", "material"]
_CAT_INDIRECT = ["indireto_mao_obra", "indireto_equipamento", "indireto_verbas"]
_CAT_ORDER = _CAT_DIRECT + _CAT_INDIRECT


def _bucket_from_week_iso(week_iso: str) -> str:
    from datetime import date
    year_str, week_str = week_iso.split("-W", 1)
    anchor = date.fromisocalendar(int(year_str), int(week_str), 1)
    return f"{anchor.year:04d}-{anchor.month:02d}"


def build(canonical, cubo) -> bytes | None:
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    try:
        monthly_by_cat: dict[str, dict[str, float]] = {
            cat: defaultdict(float) for cat in _CAT_ORDER
        }
        for celula, valor_cell in _iter_scaled_cubo_cells(canonical, cubo):
            if getattr(celula, "componente_bdi", None) != "custo_direto":
                continue
            cat = str(getattr(celula, "categoria", "") or "")
            if cat not in monthly_by_cat:
                continue
            bucket = _bucket_from_week_iso(str(celula.semana_iso))
            monthly_by_cat[cat][bucket] += float(valor_cell)

        # Custo indireto semanal distribuído em (mao_obra, equipamento, verbas)
        indir_shares = _indireto_component_shares(canonical)
        acts = []
        cronograma = getattr(canonical, "cronograma", None)
        if cronograma:
            acts = getattr(cronograma, "scheduled_activities", None) or []
        semanas_set: set[str] = set()
        for act in acts:
            for wk in (getattr(act, "distribuicao_semanal", None) or {}):
                semanas_set.add(wk)
        semanas_sorted = sorted(semanas_set)
        for ind in (getattr(canonical, "indiretos_semanal", None) or []):
            offset = ind.semana
            if 0 <= offset < len(semanas_sorted):
                bucket = _bucket_from_week_iso(semanas_sorted[offset])
                custo_sem = float(ind.custo_semanal or 0.0)
                monthly_by_cat["indireto_mao_obra"][bucket] += custo_sem * float(indir_shares.get("mao_obra", 0.0))
                monthly_by_cat["indireto_equipamento"][bucket] += custo_sem * float(indir_shares.get("equipamento", 0.0))
                monthly_by_cat["indireto_verbas"][bucket] += custo_sem * float(indir_shares.get("verbas", 0.0))

        periodos = sorted({b for cat_dict in monthly_by_cat.values() for b in cat_dict})
        if not periodos:
            return None

        scale = 1e6
        x = list(range(len(periodos)))

        fig, (ax_bar, ax_line) = plt.subplots(
            2, 1, figsize=(max(10, len(periodos) * 0.9 + 2), 9), sharex=True
        )

        # ── Subplot 1: barras mensais empilhadas por categoria ──────────────
        baseline = [0.0] * len(periodos)
        for cat_idx, cat in enumerate(_CAT_ORDER):
            cat_dict = monthly_by_cat[cat]
            values = [cat_dict.get(per, 0.0) / scale for per in periodos]
            label = _CAT_LABELS.get(cat, cat)
            bars = ax_bar.bar(
                x, values, bottom=baseline,
                color=COLORS[cat_idx % len(COLORS)],
                alpha=0.85, label=label, width=0.7,
            )
            for bar, val in zip(bars, values):
                if val > 0.005:
                    mid_y = bar.get_y() + bar.get_height() / 2
                    ax_bar.text(
                        bar.get_x() + bar.get_width() / 2,
                        mid_y,
                        f"{val:.2f}",
                        ha="center", va="center",
                        fontsize=7, color="white", fontweight="bold",
                    )
            baseline = [b + v for b, v in zip(baseline, values)]

        ax_bar.set_title("Custo por Mês (Custo Operacional)", fontsize=11, fontweight="bold")
        ax_bar.set_ylabel("R$ (Mi)", fontsize=9)
        ax_bar.legend(loc="upper right", fontsize=8)
        ax_bar.grid(axis="y", alpha=0.3)
        ax_bar.tick_params(labelbottom=False)

        # ── Subplot 2: stack plot cumulativo — Direto + Indireto ────────────
        total_direto_per = [
            sum(monthly_by_cat[cat].get(per, 0.0) for cat in _CAT_DIRECT)
            for per in periodos
        ]
        total_indireto_per = [
            sum(monthly_by_cat[k].get(per, 0.0) for k in _CAT_INDIRECT)
            for per in periodos
        ]

        acc_direto, acc_indireto = [], []
        run_d = 0.0
        run_i = 0.0
        for vd, vi in zip(total_direto_per, total_indireto_per):
            run_d += vd / scale
            run_i += vi / scale
            acc_direto.append(run_d)
            acc_indireto.append(run_i)

        # two-band fill_between: direto from 0→acc_direto, indireto stacked on top
        acc_total = [d + i for d, i in zip(acc_direto, acc_indireto)]
        ax_line.fill_between(x, 0, acc_direto, alpha=0.75,
                             color=COLORS[0], label="Direto Acum.")
        ax_line.fill_between(x, acc_direto, acc_total, alpha=0.75,
                             color=COLORS[4], label="Indireto Acum.")
        ax_line.plot(x, acc_total, color="#333", linewidth=1.5, alpha=0.8)

        # Reference lines from canonical.resultado when available
        try:
            resultado = getattr(canonical, "resultado", None)
            if resultado:
                venda_total = float(getattr(getattr(resultado, "venda", None), "total_com_bdi", 0.0) or 0.0)
                custo_total = float(getattr(getattr(resultado, "custo", None), "total", 0.0) or 0.0)
                if venda_total > 0:
                    ax_line.axhline(venda_total / scale, color="#e74c3c", linewidth=1.2,
                                    linestyle=":", alpha=0.8, label=f"Venda c/BDI: {venda_total/scale:.1f} Mi")
                if custo_total > 0:
                    ax_line.axhline(custo_total / scale, color="#27ae60", linewidth=1.2,
                                    linestyle="--", alpha=0.8, label=f"Custo catalogo: {custo_total/scale:.1f} Mi")
        except Exception:
            pass

        ax_line.set_ylabel("R$ (Mi) Acumulado", fontsize=9)
        ax_line.set_xlabel("Mês", fontsize=9)
        ax_line.set_title(
            "Custo Acumulado por Natureza (Direto + Indireto Operacional)",
            fontsize=11, fontweight="bold",
        )
        ax_line.set_xticks(x)
        ax_line.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax_line.legend(fontsize=8, loc="upper left")
        ax_line.grid(axis="y", alpha=0.3)

        fig.suptitle("S-Curve de Custo Operacional", fontsize=13, fontweight="bold")
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
