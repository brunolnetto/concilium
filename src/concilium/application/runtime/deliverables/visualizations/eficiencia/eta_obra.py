"""NEP-036 — Nível 1: η_obra(t) como série temporal semanal.

Público-alvo: diretoria, planejamento executivo.
Exibe a eficiência global da obra semana a semana com banda de variância
(mín/máx entre atividades) para sinalizar dispersão semanal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.services.analytics.eficiencia_field_builder import CampoEficiencia


def plot_eta_obra(campo: CampoEficiencia, *, title: str = "Eficiência Global da Obra η_obra(t)") -> Any:
    """Linha temporal de η_obra com banda [η_min, η_max] semanal.

    Retorna figura matplotlib ou None se matplotlib não instalado.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    eta_serie = campo.eta_obra()
    if not eta_serie:
        return None

    semanas = campo.semanas
    valores = [eta_serie.get(s, float("nan")) for s in semanas]

    # Banda: mín/máx de η por semana entre atividades
    minimos = []
    maximos = []
    for sem in semanas:
        vals = [
            (campo.E.get(iid) or {}).get(sem)
            for iid in campo.atividades
            if (campo.E.get(iid) or {}).get(sem) is not None
        ]
        vals = [v for v in vals if v is not None]
        minimos.append(min(vals) if vals else float("nan"))
        maximos.append(max(vals) if vals else float("nan"))

    x = list(range(len(semanas)))
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(x, minimos, maximos, alpha=0.15, color="#1976D2", label="Intervalo [min, max]")
    ax.plot(x, valores, color="#1976D2", linewidth=2, label="η_obra")
    ax.axhline(1.0, color="green", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axhline(0.8, color="orange", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.set_ylim(0, 1.05)
    ax.set_xticks(x[::4])
    ax.set_xticklabels([semanas[i] for i in x[::4]], rotation=45, ha="right", fontsize=7)
    ax.set_xlabel("Semana ISO")
    ax.set_ylabel("η_obra")
    ax.set_title(title)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return fig
