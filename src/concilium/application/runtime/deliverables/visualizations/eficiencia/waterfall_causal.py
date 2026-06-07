"""NEP-036 — Nível 2: Waterfall causal η_s / η_p / η_w.

Decompõe a perda de eficiência global em três fatores causais mais o termo
cruzado (acoplamento). Público-alvo: gerência, planejamento.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.services.eficiencia_field_builder import CampoEficiencia


def plot_waterfall_causal(
    campo: CampoEficiencia,
    *,
    title: str = "Decomposição Causal da Eficiência",
) -> Any:
    """Waterfall η_s × η_p × η_w → η_global, com barra eps_cross.

    Mostra a contribuição multiplicativa de cada fator à eficiência global.
    Retorna figura matplotlib ou None.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    dec = campo.decomposicao_causal()
    eta_s = dec.get("eta_s_global", 1.0)
    eta_p = dec.get("eta_p_global", 1.0)
    eta_w = dec.get("eta_w_global", 1.0)
    eta_g = dec.get("eta_global", 1.0)
    eps = dec.get("eps_cross", 0.0)

    labels = ["η_s\n(alocação)", "η_p\n(praticabilidade)", "η_w\n(gestão)", "ε_cross\n(acoplamento)", "η_global"]
    values = [eta_s, eta_p, eta_w, abs(eps), eta_g]
    colors = ["#1976D2", "#43A047", "#FB8C00", "#E53935" if eps < 0 else "#9E9E9E", "#37474F"]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.bar(labels, values, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax.axhline(1.0, color="green", linewidth=0.8, linestyle="--", alpha=0.5)
    for bar, val in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Eficiência (0–1)")
    ax.set_title(title)
    if dec.get("acoplamento_material"):
        ax.annotate(
            "⚠ Acoplamento material entre fatores (|ε_cross| > 5%)",
            xy=(0.5, 0.02),
            xycoords="axes fraction",
            ha="center",
            color="red",
            fontsize=8,
        )
    fig.tight_layout()
    return fig
