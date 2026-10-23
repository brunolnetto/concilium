"""One installed capacity F(m), one realizable rate shaped by week conditions."""
from __future__ import annotations

import pytest

from concilium.domain.models.planning.mobilizacao import WorkforcePolicy
from concilium.domain.services.planning.mobilizacao_simulator import WorkforcePolicySimulator
from concilium.domain.services.planning.produtividade import produtividade_realizavel


def test_unique_hourly_productivity_rate() -> None:
    # F(2)=20 units/hour, 75% physical practicability and 80% calendar.
    rho = produtividade_realizavel(20.0, 0.75, 0.80)
    assert rho == pytest.approx(12.0)
    assert rho * 40 == pytest.approx(480.0)


def test_only_calendar_or_practicability_change_the_week() -> None:
    assert produtividade_realizavel(20.0, 1, 1) == 20
    assert produtividade_realizavel(20.0, 0, 1) == 0
    assert produtividade_realizavel(20.0, 1, 0) == 0
    assert produtividade_realizavel(20.0, 0.75, 0.8, 0.5) == pytest.approx(6)


@pytest.mark.parametrize(
    ("capacity", "prat", "calendar", "working"),
    [(float("nan"), 1, 1, 1), (20, 1.01, 1, 1), (20, 1, -0.2, 1), (20, 1, 1, float("inf"))],
)
def test_availability_invalid_is_not_a_certifiable_schedule(
    capacity: float, prat: float, calendar: float, working: float
) -> None:
    with pytest.raises(ValueError):
        produtividade_realizavel(capacity, prat, calendar, working)


def test_wmp_uses_same_practicability_and_calendar_law_as_scheduling() -> None:
    # F(2)=20/h; H=40 hours; physical availability .75 * .8.
    curve = WorkforcePolicySimulator().simulate(
        policy=WorkforcePolicy.imediato(2),
        atividade_id="EAP",
        quantitativo=960.0,
        producao_horaria=10.0,  # independent front basis
        dias_semana=5,
        horas_dia=8,
        semanas_iso_por_offset={0: "2026-W41", 1: "2026-W42"},
        prat_semanal={"2026-W41": 0.75, "2026-W42": 0.75},
        calendario_semanal={"2026-W41": 0.8, "2026-W42": 0.8},
    )
    assert curve.is_complete
    assert [week.qtd_executada for week in curve.semanas] == pytest.approx([480, 480])
    assert [week.eficiencia for week in curve.semanas] == pytest.approx([0.6, 0.6])


def test_wmp_shared_bottleneck_calendar_and_final_week_closure() -> None:
    # Shared F(2)=15/h; effective available production = 15*40*.75*.8=360.
    curve = WorkforcePolicySimulator().simulate(
        policy=WorkforcePolicy.imediato(2),
        atividade_id="EAP",
        quantitativo=500.0,
        producao_horaria=15.0,
        dias_semana=5,
        horas_dia=8,
        capacidade_horaria_por_frentes=lambda m: min(10 * m, 15),
        semanas_iso_por_offset={0: "2026-W41", 1: "2026-W42"},
        prat_semanal={"2026-W41": 0.75, "2026-W42": 0.75},
        calendario_semanal={"2026-W41": 0.8, "2026-W42": 0.8},
    )
    assert curve.is_complete
    assert [week.qtd_executada for week in curve.semanas] == pytest.approx([360, 140])


def test_wmp_refuses_calendar_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match="availability factors"):
        WorkforcePolicySimulator().simulate(
            policy=WorkforcePolicy.imediato(2),
            atividade_id="EAP",
            quantitativo=1000,
            producao_horaria=10,
            dias_semana=5,
            horas_dia=8,
            semanas_iso_por_offset={0: "2026-W41"},
            calendario_semanal={"2026-W41": 1.2},
        )


@pytest.mark.parametrize("jornada", [-0.1, 1.01, float("nan"), float("inf")])
def test_wmp_fails_closed_on_invalid_jornada(jornada: float) -> None:
    with pytest.raises(ValueError, match="eta_jornada"):
        WorkforcePolicySimulator().simulate(
            policy=WorkforcePolicy.imediato(2),
            atividade_id="EAP",
            quantitativo=100,
            producao_horaria=10,
            dias_semana=5,
            horas_dia=8,
            eta_jornada=jornada,
        )


@pytest.mark.parametrize(
    ("scope", "rate"),
    [(float("nan"), 10.0), (float("inf"), 10.0), (100.0, float("nan")), (100.0, float("inf"))],
)
def test_wmp_fails_closed_on_nonfinite_scope_or_rate(scope: float, rate: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        WorkforcePolicySimulator().simulate(
            policy=WorkforcePolicy.imediato(2),
            atividade_id="EAP",
            quantitativo=scope,
            producao_horaria=rate,
            dias_semana=5,
            horas_dia=8,
        )


@pytest.mark.parametrize(("days", "hours"), [(0, 8), (5, 0), (-1, 8)])
def test_wmp_fails_closed_on_nonproductive_calendar_dimensions(
    days: int, hours: int
) -> None:
    with pytest.raises(ValueError, match="strictly positive"):
        WorkforcePolicySimulator().simulate(
            policy=WorkforcePolicy.imediato(2),
            atividade_id="EAP",
            quantitativo=100,
            producao_horaria=10,
            dias_semana=days,
            horas_dia=hours,
        )
