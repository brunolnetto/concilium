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


def test_mobilization_simulator_uses_graph_capacity_instead_of_double_team_count() -> None:
    from concilium.domain.models.planning.mobilizacao import WorkforcePolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    simulator = WorkforcePolicySimulator()
    policy = WorkforcePolicy.imediato(4)
    curve = simulator.simulate(
        policy=policy,
        atividade_id="EAP-1",
        quantitativo=600.0,
        producao_horaria=15.0,  # calibrated peak F(4), *not* 15 per front
        dias_semana=5,
        horas_dia=8,
        capacidade_horaria_por_frentes=lambda m: min(10.0 * m, 15.0),
    )
    assert curve.is_complete
    assert curve.duration_weeks == 1
    assert curve.semanas[0].qtd_executada == 600.0


def test_mobilization_ramp_uses_bottleneck_from_second_week() -> None:
    from concilium.domain.models.planning.mobilizacao import WorkforcePolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    curve = WorkforcePolicySimulator().simulate(
        policy=WorkforcePolicy.padrao(4),
        atividade_id="EAP-ramp",
        quantitativo=1000.0,
        producao_horaria=15.0,
        dias_semana=5,
        horas_dia=8,
        capacidade_horaria_por_frentes=lambda m: min(10.0 * m, 15.0),
    )
    assert curve.is_complete
    assert curve.duration_weeks == 2
    assert [cell.qtd_executada for cell in curve.semanas] == [400.0, 600.0]


def test_mobilization_rejects_nonfinite_capacity_callback() -> None:
    from concilium.domain.models.planning.mobilizacao import WorkforcePolicy
    from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator

    with pytest.raises(ValueError, match="finite"):
        WorkforcePolicySimulator().simulate(
            policy=WorkforcePolicy.imediato(2),
            atividade_id="EAP-invalid",
            quantitativo=1000.0,
            producao_horaria=10.0,
            dias_semana=5,
            horas_dia=8,
            capacidade_horaria_por_frentes=lambda _: float("nan"),
        )


@pytest.mark.parametrize(
    ("edges", "peak", "active", "expected"),
    [
        # Series: the least productive physical stage governs throughput.
        (
            [("s", "a", 40), ("a", "b", 25), ("b", "t", 20)],
            20.0, 1, 10.0,
        ),
        # Two independent parallel paths add their capacities.
        (
            [("s", "a", 20), ("s", "b", 20), ("a", "t", 20), ("b", "t", 20)],
            40.0, 2, 20.0,
        ),
        # Mixed: branches share a common internal 25 u/h restriction.
        (
            [
                ("s", "hub", 40), ("hub", "fork", 25),
                ("fork", "a", 20), ("fork", "b", 20),
                ("a", "t", 20), ("b", "t", 20),
            ],
            25.0, 3, 25.0,
        ),
    ],
    ids=["serial-bottleneck", "parallel-branches", "mixed-shared-bottleneck"],
)
def test_series_parallel_and_mixed_maxflow_capacity(
    edges: list[tuple[str, str, float]], peak: float, active: int, expected: float
) -> None:
    from concilium.domain.models.catalog.producao import GrafoSinergiaEquipe

    nodes = sorted({node for origin, destination, _ in edges for node in (origin, destination)})
    graph = GrafoSinergiaEquipe.model_validate(
        {
            "fonte": "s",
            "sorvedouro": "t",
            "dominio": nodes,
            "arestas_fluxo": [
                {
                    "aresta_id": f"edge_{idx}",
                    "origem": origin,
                    "destino": destination,
                    "capacidade_horaria": capacity,
                }
                for idx, (origin, destination, capacity) in enumerate(edges)
            ],
        }
    )
    assert capacidade_efetiva_frentes(graph, active, 4, peak) == pytest.approx(expected)
    assert capacidade_efetiva_frentes(graph, 4, 4, peak) == pytest.approx(peak)
