"""scurve_custo.png — S-Curve de custo + camadas BDI convergindo para o preço de venda.

Painel superior (barras mensais):
  Direto | Indireto | Overhead BDI | Lucro (L) | Tributos

Painel inferior (acumulado):
  Áreas empilhadas das mesmas 5 camadas → curva converge para o preço de venda.
"""

from __future__ import annotations

from collections import defaultdict

from ._common import COLORS, build_payload, init_mpl

# Paleta: direto, indireto, overhead, lucro, tributos
_PALETTE = ["#1a3a5c", "#5adc8e", "#5aabdc", "#e8a030", "#c05c18"]
_BDI_COMPS = ["Overhead BDI", "Lucro (L)", "Tributos"]
_BDI_COLORS = {"Overhead BDI": _PALETTE[2], "Lucro (L)": _PALETTE[3], "Tributos": _PALETTE[4]}


def build(canonical, cubo) -> bytes | None:
    del cubo
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None

    try:
        # ── Custo operacional (direto + indireto) por mês via tempo_natureza ──────
        payload_nat = build_payload("tempo_natureza", "mes", 120, canonical, None)
        rows_nat = payload_nat.get("rows") or []
        if not rows_nat:
            return None

        periodos = sorted({str(r.get("periodo", "")) for r in rows_nat})
        monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for r in rows_nat:
            monthly[str(r.get("periodo", ""))][str(r.get("natureza", ""))] += float(r.get("valor_rs", 0.0) or 0.0)

        # ── Camadas BDI por mês via tempo_componente ────────────────────────────
        cubo_analitico = getattr(canonical, "cubo_analitico", None)
        payload_comp = build_payload("tempo_componente", "mes", 300, canonical, cubo_analitico)
        rows_comp = payload_comp.get("rows") or []
        bdi_monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for r in rows_comp:
            comp = str(r.get("componente_bdi", ""))
            if comp in _BDI_COMPS:
                bdi_monthly[str(r.get("periodo", ""))][comp] += float(r.get("valor_rs", 0.0) or 0.0)
        # Estender periodos com meses de BDI que possam existir além do período operacional
        periodos = sorted(set(periodos) | set(bdi_monthly.keys()))

        scale = 1e6
        x = list(range(len(periodos)))
        direto   = [monthly[p]["direto"]   / scale for p in periodos]
        indireto = [monthly[p]["indireto"] / scale for p in periodos]
        bdi_layers = {c: [bdi_monthly[p][c] / scale for p in periodos] for c in _BDI_COMPS}

        fig, (ax_bar, ax_line) = plt.subplots(2, 1, figsize=(max(10, len(periodos) * 0.9 + 2), 10), sharex=True)

        # ── Painel 1: barras mensais empilhadas ────────────────────────────────
        ax_bar.bar(x, direto,   color=_PALETTE[0], alpha=0.88, width=0.7, label="Direto")
        ax_bar.bar(x, indireto, bottom=direto, color=_PALETTE[1], alpha=0.88, width=0.7, label="Indireto")
        bottoms = [d + i for d, i in zip(direto, indireto)]
        for comp in _BDI_COMPS:
            vals = bdi_layers[comp]
            ax_bar.bar(x, vals, bottom=bottoms, color=_BDI_COLORS[comp], alpha=0.80, width=0.7, label=comp)
            bottoms = [b + v for b, v in zip(bottoms, vals)]
        ax_bar.set_title("Custo por Mês (base única operacional)", fontsize=11, fontweight="bold")
        ax_bar.set_ylabel("R$ (Mi)", fontsize=9)
        ax_bar.legend(loc="upper right", fontsize=8)
        ax_bar.grid(axis="y", alpha=0.3)
        ax_bar.tick_params(labelbottom=False)

        # ── Painel 2: acumulado empilhado convergindo para preço de venda ──────
        def _accum(series: list[float]) -> list[float]:
            out, s = [], 0.0
            for v in series:
                s += v
                out.append(s)
            return out

        acc_d   = _accum(direto)
        acc_i   = [d + i for d, i in zip(acc_d, _accum(indireto))]
        acc_bdi = dict(acc_i=acc_i)
        prev = acc_i
        for comp in _BDI_COMPS:
            nxt = [p + v for p, v in zip(prev, _accum(bdi_layers[comp]))]
            acc_bdi[comp] = nxt
            prev = nxt
        acc_total_bdi = prev  # topo das camadas = preço operacional+BDI

        ax_line.fill_between(x, 0,     acc_d,            alpha=0.75, color=_PALETTE[0], label="Direto Acum.")
        ax_line.fill_between(x, acc_d, acc_i,            alpha=0.75, color=_PALETTE[1], label="Indireto Acum.")
        prev_acc = acc_i
        for comp in _BDI_COMPS:
            nxt_acc = acc_bdi[comp]
            ax_line.fill_between(x, prev_acc, nxt_acc, alpha=0.70, color=_BDI_COLORS[comp], label=f"{comp} Acum.")
            prev_acc = nxt_acc

        ax_line.plot(x, acc_total_bdi, color="#333", linewidth=1.8, alpha=0.9, zorder=5)

        resultado = getattr(canonical, "resultado", None)
        # Preço pool+BDI = soma acumulada das 5 camadas (convergência natural da curva)
        preco_pool_bdi = acc_total_bdi[-1] if acc_total_bdi else 0.0
        # Preço de contrato (PUxQ) = referência de mercado
        preco_catalogo = float(getattr(getattr(resultado, "venda", None), "total_com_bdi", 0.0) or 0.0) / scale
        custo_op       = float(getattr(getattr(resultado, "custo", None), "total", 0.0) or 0.0) / scale

        if preco_pool_bdi > 0:
            ax_line.axhline(preco_pool_bdi, color="#e74c3c", linewidth=1.8, linestyle="-",
                            alpha=0.9, label=f"Preço de venda: {preco_pool_bdi:.1f} Mi")
        if custo_op > 0:
            ax_line.axhline(custo_op, color="#27ae60", linewidth=1.2, linestyle="--",
                            alpha=0.6, label=f"Custo s/BDI: {custo_op:.1f} Mi")

        ax_line.set_ylabel("R$ (Mi) Acumulado", fontsize=9)
        ax_line.set_xlabel("Mês", fontsize=9)
        ax_line.set_title("Custo Acumulado por Natureza (direto + indireto + BDI → preço de venda)",
                          fontsize=11, fontweight="bold")
        ax_line.set_xticks(x)
        ax_line.set_xticklabels(periodos, rotation=45, ha="right", fontsize=8)
        ax_line.legend(fontsize=7.5, loc="upper left", ncol=2)
        ax_line.grid(axis="y", alpha=0.3)

        fig.suptitle("S-Curve de Custo Operacional", fontsize=13, fontweight="bold")
        fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
