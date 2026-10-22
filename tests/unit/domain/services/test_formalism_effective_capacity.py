"""P10-B: effective team capacity is not a productivity-loss factor."""
from __future__ import annotations

import pytest

from concilium.domain.services.sinergia_equipe import capacidade_efetiva_frentes


def test_two_fronts_are_eight_hundred_units_not_four_hundred() -> None:
    # Certified peak F(4)=40 units/hour; F(2)=20 units/hour.
    assert capacidade_efetiva_frentes(None, 2, 4, 40) == 20
    assert capacidade_efetiva_frentes(None, 2, 4, 40) * 40 == 800


def test_zero_and_peak_mobilization() -> None:
    assert capacidade_efetiva_frentes(None, 0, 4, 40) == 0
    assert capacidade_efetiva_frentes(None, 4, 4, 40) == 40


@pytest.mark.parametrize(
    ("count", "peak", "capacity"),
    [(-1, 4, 40), (5, 4, 40), (2, 0, 40), (2, 4, 0), (2, 4, float("nan"))],
)
def test_invalid_calibration_fails_closed(count: float, peak: float, capacity: float) -> None:
    with pytest.raises(ValueError):
        capacidade_efetiva_frentes(None, count, peak, capacity)


def test_shared_downstream_graph_saturates() -> None:
    from concilium.domain.models.catalog.producao import GrafoSinergiaEquipe

    # The supply grows with teams, but a shared physical process limits it to 15.
    graph = GrafoSinergiaEquipe.model_validate(
        {
            "fonte": "s",
            "sorvedouro": "t",
            "dominio": ["s", "middle", "t"],
            "arestas_fluxo": [
                {"aresta_id": "a", "origem": "s", "destino": "middle", "capacidade_horaria": 40},
                {"aresta_id": "b", "origem": "middle", "destino": "t", "capacidade_horaria": 15},
            ],
        }
    )
    assert capacidade_efetiva_frentes(graph, 2, 4, 15) == 15
    assert capacidade_efetiva_frentes(graph, 4, 4, 15) == 15
