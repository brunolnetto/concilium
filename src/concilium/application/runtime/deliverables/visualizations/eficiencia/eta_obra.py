"""NEP-036 — Nível 1: η_obra(t) como série temporal semanal.

Público-alvo: diretoria, planejamento executivo.
Exibe a eficiência global da obra semana a semana com banda de variância
(mín/máx entre atividades) para sinalizar dispersão semanal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.services.analytics.eficiencia_field_builder import CampoEficiencia


def _valores_semana(eta_field: dict, atividades: Any, sem: str) -> list[float]:
    """Coleta os valores de η_plan de uma semana entre todas as atividades."""
    vals = [
        (eta_field.get(iid) or {}).get(sem) for iid in atividades if (eta_field.get(iid) or {}).get(sem) is not None
    ]
    return [v for v in vals if v is not None]


def _compute_semanas_band(campo: CampoEficiencia, semanas: list[str]) -> tuple[list[float], list[float]]:
    """Calcula banda [min, max] de η_plan por semana entre atividades."""
    minimos = []
    maximos = []
    eta_field = campo.E or campo.Eta_plan  # E=None no planejamento
    for sem in semanas:
        vals = _valores_semana(eta_field, campo.atividades, sem)
        minimos.append(min(vals) if vals else float("nan"))
        maximos.append(max(vals) if vals else float("nan"))
    return minimos, maximos


def _render_eta_obra_figure(
    plt: Any,
    semanas: list[str],
    valores: list[float],
    minimos: list[float],
    maximos: list[float],
    title: str,
) -> Any:
    """Desenha a figura matplotlib de η_obra com banda de variância."""
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

    minimos, maximos = _compute_semanas_band(campo, semanas)

    return _render_eta_obra_figure(plt, semanas, valores, minimos, maximos, title)
