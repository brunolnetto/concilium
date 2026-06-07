"""scurve_custo.png — S-Curve de custo com fonte única operacional.

Usa a mesma base do domínio (SCurveBuilder):
- Direto: agregação instancial de recursos (pool) quando disponível.
- Indireto: permanência semanal (indiretos_semanal).
"""

from __future__ import annotations

from collections import defaultdict

from ._common import COLORS, build_payload, init_mpl


def _bucket_from_week_iso(week_iso: str) -> str:
    from datetime import date

    year_str, week_str = week_iso.split("-W", 1)
    anchor = date.fromisocalendar(int(year_str), int(week_str), 1)
    return f"{anchor.year:04d}-{anchor.month:02d}"


def build(canonical, cubo) -> bytes | None:
    del cubo
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        from concilium.domain.services.s_curve_builder import SCurveBuilder

        s_curve = getattr(canonical, "s_curve", None) or SCurveBuilder().build(canonical)
        agreg = list(getattr(s_curve, "agregacao_semanal", ()) or ())
        if not agreg:
            return None

        payload = build_payload("tempo_natureza", "mes", 120, canonical, None)
        rows = payload.get("rows") or []
        columns = payload.get("columns") or []
        if not rows:
            return None

        periodos = sorted({str(row.get("periodo", "")) for row in rows})
        monthly: dict[str, dict[str, float]] = defaultdict(lambda: {"direto": 0.0, "indireto": 0.0})
        for row in rows:
            monthly[str(row.get("periodo", ""))][str(row.get("natureza", ""))] += float(row.get("valor_rs", 0.0) or 0.0)

        scale = 1e6
        x = list(range(len(periodos)))
        direto = [monthly[p]["direto"] / scale for p in periodos]
        indireto = [monthly[p]["indireto"] / scale for p in periodos]

        fig, (ax_bar, ax_line) = plt.subplots(2, 1, figsize=(max(10, len(periodos) * 0.9 + 2), 9), sharex=True)

        ax_bar.bar(x, direto, color=COLORS[0], alpha=0.88, width=0.7, label="Direto")
        ax_bar.bar(x, indireto, bottom=direto, color=COLORS[4], alpha=0.88, width=0.7, label="Indireto")
        ax_bar.set_title("Custo por Mês (base única operacional)", fontsize=11, fontweight="bold")
        ax_bar.set_ylabel("R$ (Mi)", fontsize=9)
        ax_bar.legend(loc="upper right", fontsize=8)
        ax_bar.grid(axis="y", alpha=0.3)
        ax_bar.tick_params(labelbottom=False)

        acc_direto: list[float] = []
        acc_indireto: list[float] = []
        run_d = 0.0
        run_i = 0.0
        for d, i in zip(direto, indireto):
            run_d += d
            run_i += i
            acc_direto.append(run_d)
            acc_indireto.append(run_i)
        acc_total = [d + i for d, i in zip(acc_direto, acc_indireto)]

        ax_line.fill_between(x, 0, acc_direto, alpha=0.75, color=COLORS[0], label="Direto Acum.")
        ax_line.fill_between(x, acc_direto, acc_total, alpha=0.75, color=COLORS[4], label="Indireto Acum.")
        ax_line.plot(x, acc_total, color="#333", linewidth=1.5, alpha=0.85)

        resultado = getattr(canonical, "resultado", None)
        venda_total = float(getattr(getattr(resultado, "venda", None), "total_com_bdi", 0.0) or 0.0)
        custo_total = float(getattr(getattr(resultado, "custo", None), "total", 0.0) or 0.0)
        if venda_total > 0:
            ax_line.axhline(
                venda_total / scale,
                color="#e74c3c",
                linewidth=1.2,
                linestyle=":",
                alpha=0.8,
                label=f"Venda c/BDI: {venda_total / scale:.1f} Mi",
            )
        if custo_total > 0:
            ax_line.axhline(
                custo_total / scale,
                color="#27ae60",
                linewidth=1.2,
                linestyle="--",
                alpha=0.8,
                label=f"Custo operacional: {custo_total / scale:.1f} Mi",
            )

        ax_line.set_ylabel("R$ (Mi) Acumulado", fontsize=9)
        ax_line.set_xlabel("Mês", fontsize=9)
        ax_line.set_title("Custo Acumulado por Natureza (direto + indireto)", fontsize=11, fontweight="bold")
        ax_line.set_xticks(x)
        ax_line.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax_line.legend(fontsize=8, loc="upper left")
        ax_line.grid(axis="y", alpha=0.3)

        total_explicito = (sum(direto) + sum(indireto)) * scale
        delta_total = total_explicito - custo_total if custo_total > 0 else 0.0
        fig.suptitle("S-Curve de Custo Operacional", fontsize=13, fontweight="bold")
        if custo_total > 0 and abs(delta_total) > 1.0:
            fig.text(
                0.01,
                0.01,
                f"Divergência explícita: Direto+Indireto={total_explicito / scale:.3f} Mi vs Custo operacional={custo_total / scale:.3f} Mi (Δ={delta_total / scale:+.3f} Mi).",
                fontsize=7.5,
                color="#555",
                ha="left",
            )

        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
