"""P15: zero-output Q release and Skill 04 -> Skill 05 integration properties."""
from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import pytest

from concilium.application.skills import run_cronograma, run_equipes_e_alocacao
from concilium.domain.models.canonical import (
    DistribuicaoSemanal,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
)

WEEKS = (
    "2026-W01",
    "2026-W02",
    "2026-W03",
    "2026-W04",
    "2026-W05",
)
SKILL05_TEAM_RESOURCE = "EQUIPE-COMP-P15-MATRIX"


class Predecessor:
    def __init__(self, item_id: str, threshold: float, lag: int) -> None:
        self.item_id = item_id
        self.tipo = "FS"
        self.lag = lag
        self.completion_threshold_pct = threshold


class Item:
    def __init__(
        self,
        item_id: str,
        quantity: float,
        predecessors: tuple[Predecessor, ...] = (),
    ) -> None:
        self.item_id = item_id
        self.cpu_id = f"CPU-{item_id}"
        self.quantitativo = quantity
        self._predecessors = predecessors

    def predecessores_tipados(self) -> tuple[Predecessor, ...]:
        return self._predecessors


def _cell(
    q: float,
    cumulative: float,
    capacity: float,
    teams: int,
) -> DistribuicaoSemanal:
    return DistribuicaoSemanal(
        num_equipes=teams,
        qtd_executada=q,
        qtd_acumulada=cumulative,
        pct=cumulative / 2,
        q_max_celula=capacity,
        capacidade_disponivel_semana=capacity,
    )


def _candidate() -> ScheduleCandidateCanonical:
    return ScheduleCandidateCanonical(
        heuristic="p15-skill04-skill05-matrix",
        scheduled_activities=[
            ScheduledActivityCanonical(
                activity_id="A",
                start_week=0,
                end_week=0,
                duration_weeks=1,
                assigned_resources={"excavator": 1},
            ),
            ScheduledActivityCanonical(
                activity_id="B",
                start_week=0,
                end_week=0,
                duration_weeks=1,
                assigned_resources={"crane": 1},
            ),
        ],
        makespan=1,
        quality_score=1.0,
    )


def _patch_skill04_materializer(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    module = sys.modules[helper.__module__]

    def distribution_for(scheduled, item):
        start = scheduled.start_week
        if item.item_id == "A":
            if start + 1 >= len(WEEKS):
                return {}, 0.0
            # A is physically idle in W01; Q is delivered only in W02.
            return {
                WEEKS[start]: _cell(0.0, 0.0, 0.0, 1),
                WEEKS[start + 1]: _cell(1.0, 1.0, 1.0, 1),
            }, 1.0

        if start + 1 >= len(WEEKS):
            return {}, 0.0
        # B's resolved Skill 04 workforce profile ramps from one to two
        # fronts; Skill 05 must derive the matching [1, 2] weekly demand.
        return {
            WEEKS[start]: _cell(1.0, 1.0, 1.0, 1),
            WEEKS[start + 1]: _cell(1.0, 2.0, 2.0, 2),
        }, 2.0

    def build_distribution(scheduled, item, *_args, **_kwargs):
        return distribution_for(scheduled, item)

    def convert(selected, canonical, _weeks, *_args, **_kwargs):
        result = {}
        items_by_id = {item.item_id: item for item in canonical.eap}
        for scheduled in selected.scheduled_activities:
            distribution, _delivered = distribution_for(
                scheduled, items_by_id[scheduled.activity_id]
            )
            if distribution:
                result[scheduled.activity_id] = distribution
        return result, set()

    monkeypatch.setattr(module, "_build_activity_distribuicao", build_distribution)
    monkeypatch.setattr(module, "_convert_schedule_to_distribuicao", convert)
    monkeypatch.setattr(module, "_resolve_productivity", lambda *_: (1.0, False))
    monkeypatch.setattr(module, "_compute_activity_n_max", lambda *_: 1)
    monkeypatch.setattr(
        module,
        "_origem_capacidade",
        lambda *_args, **_kwargs: "P15_TEST_PHYSICAL_PRODUCTIVITY",
    )


def _resolve_skill04(
    monkeypatch: pytest.MonkeyPatch,
    *,
    threshold: float,
    lag: int,
):
    _patch_skill04_materializer(monkeypatch)
    predecessor = Predecessor("A", threshold, lag)
    items = (
        Item("A", 1.0),
        Item("B", 2.0, (predecessor,)),
    )
    canonical = SimpleNamespace(
        eap=list(items),
        atividades=[],
        recurso_pool=[
            SimpleNamespace(
                proveniencia="CONFIGURADO",
                tipo_id=resource,
                quantidade_total=1,
            )
            for resource in ("crane", "excavator")
        ],
        projeto=SimpleNamespace(data_inicio=date(2026, 1, 5)),
    )
    regime = SimpleNamespace(horas_dia=1.0, dias_semana=1.0, eta_jornada=1.0)
    validations = []

    result = run_cronograma.__globals__["resolve_skill04_physical_schedule"](
        canonical=canonical,
        inputs={
            "rcpsp_spec": {
                "resource_pool": {"crane": 1, "excavator": 1},
            },
        },
        mode="AUTO_SCHEDULE",
        schedule_selected=_candidate(),
        distribution_by_item={},
        fallback_item_ids=set(),
        weeks=list(WEEKS),
        cpu_lookup={
            "CPU-A": {"codigo": "CPU-A", "producao_id_ref": "prod"},
            "CPU-B": {"codigo": "CPU-B", "producao_id_ref": "prod"},
        },
        production_lookup={"prod": {}},
        regime=regime,
        practicability_weekly={week: 1.0 for week in WEEKS},
        practicability_monthly={},
        calendar_factor_weekly={week: 1.0 for week in WEEKS},
        validacoes=validations,
    )
    assert result.status == "PASS", result.reason
    assert any(value.codigo == "VAL-RCPSP-RESOLVED" for value in validations)
    return result


def _scheduled_by_item(result, item_id: str):
    return next(
        activity
        for activity in result.schedule_selected.scheduled_activities
        if activity.activity_id == item_id
    )


def test_auto_q_precedence_never_releases_from_a_zero_production_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _resolve_skill04(monkeypatch, threshold=1.0, lag=0)

    predecessor = _scheduled_by_item(result, "A")
    successor = _scheduled_by_item(result, "B")
    assert predecessor.distribuicao_semanal[WEEKS[0]].qtd_executada == 0.0
    assert predecessor.distribuicao_semanal[WEEKS[0]].qtd_acumulada == 0.0
    assert predecessor.distribuicao_semanal[WEEKS[1]].qtd_executada == 1.0
    # A finishes Q in W02. FS release is the following boundary, W03.
    assert successor.start_week == 2
    assert successor.distribuicao_semanal == {
        WEEKS[2]: successor.distribuicao_semanal[WEEKS[2]],
        WEEKS[3]: successor.distribuicao_semanal[WEEKS[3]],
    }


@pytest.mark.parametrize(
    ("threshold", "lag", "expected_start"),
    [
        (0.5, 0, 2),
        (1.0, 0, 2),
        (1.0, 1, 3),
    ],
)
def test_resolved_skill04_calendar_drives_skill05_weekly_pool_demand(
    monkeypatch: pytest.MonkeyPatch,
    threshold: float,
    lag: int,
    expected_start: int,
) -> None:
    """Property matrix: Q threshold/lag shift must reach Skill 05 unchanged."""
    result = _resolve_skill04(
        monkeypatch,
        threshold=threshold,
        lag=lag,
    )
    successor = _scheduled_by_item(result, "B")
    expected_weeks = WEEKS[expected_start : expected_start + 2]

    assert successor.start_week == expected_start
    assert successor.duration_weeks == 2
    assert tuple(successor.distribuicao_semanal) == expected_weeks
    assert [
        successor.distribuicao_semanal[week].num_equipes
        for week in expected_weeks
    ] == [1, 2]

    # Invoke Skill 05's production weekly-demand derivation with the exact
    # ScheduledActivity emitted by the P15 Skill 04 resolver (not a scheduler
    # stub or a hand-built parallel distribution).
    skill05_helpers = run_equipes_e_alocacao.__globals__["_skill_helpers"]
    equipe = SimpleNamespace(
        custo_operacional_agregado=300.0,
        custo_mao_obra_mensal=100.0,
        custo_equipamentos_mensal=0.0,
        custo_combustivel_total_mensal=0.0,
        custo_material_mensal=0.0,
    )
    tipo_items, weekly_demand, validations = {}, {}, []
    skill05_helpers._process_item_tipo_map(
        "B",
        {SKILL05_TEAM_RESOURCE: 2},
        {"B": equipe},
        {SKILL05_TEAM_RESOURCE: 2},
        {"B": successor},
        tipo_items,
        weekly_demand,
        validations,
    )

    assert not validations
    assert weekly_demand == {
        SKILL05_TEAM_RESOURCE: {
            expected_weeks[0]: 1,
            expected_weeks[1]: 2,
        }
    }
    demand_record = tipo_items[SKILL05_TEAM_RESOURCE][0]
    assert demand_record["active_weeks"] == list(expected_weeks)
    assert demand_record["demand_per_week"] == {
        expected_weeks[0]: 1,
        expected_weeks[1]: 2,
    }
    assert demand_record["machine_weeks"] == 3
