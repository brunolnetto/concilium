"""Fluxo de caixa e break-even acumulado."""

from __future__ import annotations

from ._common import init_mpl


def build_fluxo_financeiro(financeiro: dict) -> bytes | None:
    if not isinstance(financeiro, dict) or not financeiro.get("labels"):
        return None
    labels = [str(lbl) for lbl in financeiro.get("labels", [])]
    receita = [float(v) / 1e6 if v is not None else 0.0 for v in financeiro.get("receita", [])]
    saldo = [float(v) / 1e6 if v is not None else 0.0 for v in financeiro.get("saldo", [])]
    if not labels or not saldo:
        return None
    try:
        plt, fig_to_bytes = init_mpl()
    except ImportError:
        return None
    try:
        fig, (ax1, ax_saldo, ax2) = plt.subplots(3, 1, figsize=(12, 13), sharex=False)
        x = list(range(len(labels)))
        bar_colors = ["#c05c18" if v < 0 else "#1a3a5c" for v in saldo]
        ax1.bar(x, saldo, color=bar_colors, alpha=0.8)
        ax1.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
        ax1.set_title("Fluxo de Caixa (Saldo Receita - Despesa)", fontsize=11, fontweight="bold")
        ax1.set_ylabel("R$ (Mi)", fontsize=9)
        ax1.grid(axis="y", alpha=0.3)
        ax1.tick_params(bottom=False, labelbottom=False)
        if receita:
            n = min(len(receita), len(saldo))
            despesa_per = [receita[i] - saldo[i] for i in range(n)]
            receita_acum, despesa_acum = [], []
            r_cum, d_cum = 0.0, 0.0
            for r, d in zip(receita[:n], despesa_per, strict=False):
                r_cum += r
                d_cum += d
                receita_acum.append(r_cum)
                despesa_acum.append(d_cum)
            x2 = list(range(n))
            # ── Subplot 2: saldo acumulado (receita - despesa) ──────────────────
            saldo_acum = [r - d for r, d in zip(receita_acum, despesa_acum, strict=False)]
            bar_colors_saldo = ["#27ae60" if v >= 0 else "#c05c18" for v in saldo_acum]
            ax_saldo.bar(x2, saldo_acum, color=bar_colors_saldo, alpha=0.8)
            ax_saldo.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
            be_zero_idx = next((i for i, v in enumerate(saldo_acum) if v >= 0), None)
            if be_zero_idx is not None:
                ax_saldo.axvline(
                    be_zero_idx,
                    color="#27ae60",
                    linewidth=1.5,
                    linestyle="--",
                    alpha=0.8,
                    label=f"Break-even: {labels[be_zero_idx]}",
                )
                ax_saldo.legend(fontsize=8)
            ax_saldo.set_title("Saldo Acumulado (Receita Acum. - Despesa Acum.)", fontsize=11, fontweight="bold")
            ax_saldo.set_ylabel("R$ (Mi)", fontsize=9)
            ax_saldo.tick_params(bottom=False, labelbottom=False)
            ax_saldo.grid(axis="y", alpha=0.3)
            # ── Subplot 3: break-even receita vs despesa ────────────────────────
            be_idx = next(
                (i for i, (r, d) in enumerate(zip(receita_acum, despesa_acum, strict=False)) if r >= d),
                None,
            )
            ax2.plot(x2, receita_acum, color="#1a3a5c", linewidth=2, marker="o", markersize=3, label="Receita Acum.")
            ax2.plot(x2, despesa_acum, color="#c05c18", linewidth=2, marker="s", markersize=3, label="Despesa Acum.")
            ax2.fill_between(
                x2,
                receita_acum,
                despesa_acum,
                where=[r < d for r, d in zip(receita_acum, despesa_acum, strict=False)],
                color="#c05c18",
                alpha=0.12,
                label="Exposicao",
            )
            ax2.fill_between(
                x2,
                receita_acum,
                despesa_acum,
                where=[r >= d for r, d in zip(receita_acum, despesa_acum, strict=False)],
                color="#1a3a5c",
                alpha=0.12,
                label="Superavit Acum.",
            )
            if be_idx is not None:
                ax2.axvline(be_idx, color="#27ae60", linewidth=1.5, linestyle="--", alpha=0.8)
                ax2.annotate(
                    f"Break-even: {labels[be_idx]}",
                    xy=(be_idx, receita_acum[be_idx]),
                    xytext=(be_idx + 0.5, receita_acum[be_idx]),
                    fontsize=7,
                    color="#27ae60",
                    arrowprops=dict(arrowstyle="->", color="#27ae60", lw=0.8),
                )
            ax2.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
            ax2.set_title("Break-Even: Receita vs. Despesa Acumulada", fontsize=11, fontweight="bold")
            ax2.set_ylabel("R$ (Mi)", fontsize=9)
            ax2.set_xlabel("Periodo", fontsize=9)
            ax2.legend(fontsize=8)
            ax2.grid(axis="y", alpha=0.3)
            ax2.set_xticks(x2)
            ax2.set_xticklabels(labels[:n], rotation=45, ha="right", fontsize=8)
        else:
            ax_saldo.set_visible(False)
            ax2.set_visible(False)
        fig.suptitle("Analise Financeira", fontsize=13, fontweight="bold")
        # tight_layout emite UserWarning (não levanta) quando as margens não
        # cabem; suprimimos via catch_warnings em vez de try/except.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            fig.tight_layout()
        return fig_to_bytes(fig)
    except Exception:
        plt.close("all")
        return None
