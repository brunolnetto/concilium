"""ADR-124 / NEP-036 — Nível 2: Waterfall causal η_clima / δ (planejamento).

Decompõe a eficiência global do planejamento em dois fatores causais:
  η_clima — praticabilidade climática (estocástico, não controlável)
  δ       — coeficiente calendário (determinístico, controlável pelo gestor)

Público-alvo: gerência, planejamento.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.services.analytics.eficiencia_field_builder import CampoEficiencia


def plot_waterfall_causal(
    campo: CampoEficiencia,
    *,
    title: str = "Decomposição Causal da Eficiência de Planejamento",
) -> Any:
    """Waterfall η_clima × δ → η_plan_global.

    Exibe a contribuição de cada fator à eficiência global do plano.
    Retorna figura matplotlib ou None.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    dec = campo.decomposicao_causal()
    eta_clima = dec.get("eta_clima_global", 1.0)
    delta = dec.get("delta_global", 1.0)
    eta_plan = dec.get("eta_plan_global", 1.0)

    labels = ["η_clima\n(praticabilidade)", "δ\n(calendário)", "η_plan\n(global)"]
    values = [eta_clima, delta, eta_plan]
    colors = ["#1976D2", "#43A047", "#37474F"]

    fig, ax = plt.subplots(figsize=(7, 4))
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
    fig.tight_layout()
    return fig
