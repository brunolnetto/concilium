"""P15-D: real Skill 04 AUTO path re-resolves climate, precedence and shared pool."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from concilium.application.skills import run_cronograma
from concilium.domain.models.canonical import (
    CanonicalModel,
    DistribuicaoSemanal,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
)

WEEKS = ("2026-W01", "2026-W02", "2026-W03", "2026-W04")


class Predecessor:
    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        self.tipo = "FS"
        self.lag = 0
        self.completion_threshold_pct = 1


class Item:
    def __init__(self, item_id: str, predecessors: tuple[str, ...] = ()) -> None:
        self.item_id = item_id
        self.cpu_id = f"CPU-{item_id}"
        self.quantitativo = 1.0
        self._predecessors = tuple(Predecessor(value) for value in predecessors)

    def predecessores_tipados(self):
        return self._predecessors


def _cell(q: float = 1.0, cumulative: float | None = None, capacity: float = 1.0) -> DistribuicaoSemanal:
    actual_cumulative = q if cumulative is None else cumulative
    return DistribuicaoSemanal(
        num_equipes=1,
        qtd_executada=q,
        qtd_acumulada=actual_cumulative,
        pct=actual_cumulative,
        q_max_celula=1.0,
        capacidade_disponivel_semana=capacity,
    )


def _candidate(
    assignments: dict[str, dict[str, int]] | None = None,
    item_ids: tuple[str, ...] = ("A", "B"),
) -> ScheduleCandidateCanonical:
    assignments = assignments or {item: {"crane": 1} for item in item_ids}
    return ScheduleCandidateCanonical(
        heuristic="test",
        scheduled_activities=[
            ScheduledActivityCanonical(
                activity_id=item,
                start_week=0,
                end_week=0,
                duration_weeks=1,
                assigned_resources=assignments[item],
            )
            for item in item_ids
        ],
        makespan=1,
        quality_score=1.0,
    )


def _runtime_inputs(
    *,
    resource_capacities: dict[str, int] | None = None,
    items: tuple[Item, ...] | None = None,
):
    resources = {"crane": 1} if resource_capacities is None else resource_capacities
    canonical = SimpleNamespace(
        eap=list(items or (Item("A"), Item("B"))),
        atividades=[],
        recurso_pool=[
            SimpleNamespace(
                proveniencia="CONFIGURADO",
                tipo_id=resource,
                quantidade_total=quantity,
            )
            for resource, quantity in sorted(resources.items())
        ],
        projeto=SimpleNamespace(data_inicio=date(2026, 1, 5)),
    )
    regime = SimpleNamespace(horas_dia=1.0, dias_semana=1.0, eta_jornada=1.0)
    return canonical, regime


def _patch_skill04_materializer(monkeypatch) -> None:
    from sys import modules

    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    p15 = modules[helper.__module__]

    def distribution_for(scheduled, item):
        start = scheduled.start_week
        if item.item_id == "A":
            if start + 1 >= len(WEEKS):
                return {}, 0.0
            # Climate closes A only at the end of the week after its zero-output week.
            return {
                WEEKS[start]: _cell(q=0.0, cumulative=0.0, capacity=0.0),
                WEEKS[start + 1]: _cell(q=1.0, cumulative=1.0, capacity=1.0),
            }, 1.0
        return {WEEKS[start]: _cell()}, 1.0

    def build_distribution(scheduled, item, cpu, ramp, n_max, *args, **kwargs):
        return distribution_for(scheduled, item)

    def convert(selected, canonical, weeks, *args, **kwargs):
        result = {}
        for scheduled in selected.scheduled_activities:
            item_id = scheduled.activity_id
            item = next(entry for entry in canonical.eap if entry.item_id == item_id)
            distribution, _ = distribution_for(scheduled, item)
            if distribution:
                result[item_id] = distribution
        return result, set()

    monkeypatch.setattr(p15, "_build_activity_distribuicao", build_distribution)
    monkeypatch.setattr(p15, "_convert_schedule_to_distribuicao", convert)
    monkeypatch.setattr(p15, "_resolve_productivity", lambda *_: (1.0, False))
    monkeypatch.setattr(p15, "_compute_activity_n_max", lambda *_: 1)
    monkeypatch.setattr(
        p15, "_origem_capacidade",
        lambda *_args, **_kwargs: "TAXA_POR_FRENTE_ASSUMIDA",
    )


def test_auto_runtime_resolves_climate_delayed_precedence_and_shared_resource_collision(monkeypatch) -> None:
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    _patch_skill04_materializer(monkeypatch)
    items = (Item("A"), Item("B", ("A",)), Item("C", ("A",)))
    canonical, regime = _runtime_inputs(
        resource_capacities={"crane": 1, "excavator": 1},
        items=items,
    )
    candidate = _candidate(
        {"A": {"excavator": 1}, "B": {"crane": 1}, "C": {"crane": 1}},
        ("A", "B", "C"),
    )
    validations = []
    result = helper(
        canonical=canonical,
        inputs={"rcpsp_spec": {"resource_pool": {"crane": 1, "excavator": 1}}},
        mode="AUTO_SCHEDULE",
        schedule_selected=candidate,
        distribution_by_item={},
        fallback_item_ids=set(),
        weeks=list(WEEKS),
        cpu_lookup={
            "CPU-A": {"codigo": "CPU-A", "producao_id_ref": "prod"},
            "CPU-B": {"codigo": "CPU-B", "producao_id_ref": "prod"},
            "CPU-C": {"codigo": "CPU-C", "producao_id_ref": "prod"},
        },
        production_lookup={"prod": {}},
        regime=regime,
        practicability_weekly={week: 1.0 for week in WEEKS},
        practicability_monthly={},
        calendar_factor_weekly={week: 1.0 for week in WEEKS},
        validacoes=validations,
    )

    assert result.status == "PASS", result.reason
    assert result.complete_search is False  # first valid witness; later weeks remain unexamined
    assert result.attempts == 12
    positions = {
        activity.activity_id: activity.start_week
        for activity in result.schedule_selected.scheduled_activities
    }
    # A delivers only in W02, so FS successors cannot start before W03;
    # B and C cannot both consume the one-unit crane pool in the same week.
    assert positions == {"A": 0, "B": 2, "C": 3}
    assert result.distribution_by_item["A"][WEEKS[0]].qtd_executada == 0.0
    assert result.distribution_by_item["A"][WEEKS[1]].qtd_executada == 1.0
    assert result.distribution_by_item["B"][WEEKS[2]].qtd_executada == 1.0
    assert result.distribution_by_item["C"][WEEKS[3]].qtd_executada == 1.0
    assert any(value.codigo == "VAL-RCPSP-RESOLVED" for value in validations)


def test_auto_physical_resolver_returns_unknown_when_pool_is_unproven(monkeypatch) -> None:
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    _patch_skill04_materializer(monkeypatch)
    canonical, regime = _runtime_inputs(resource_capacities={})
    candidate = _candidate()
    result = helper(
        canonical=canonical,
        inputs={"rcpsp_spec": {"activities": [{"item_id": "A"}]}},
        mode="AUTO_SCHEDULE",
        schedule_selected=candidate,
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
        validacoes=[],
    )
    assert result.status == "UNKNOWN"
    assert result.attempts == 0
    assert "no explicit physical resource pool" in result.reason


def test_auto_physical_resolver_rejects_search_budget_above_hard_limit(monkeypatch) -> None:
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    _patch_skill04_materializer(monkeypatch)
    canonical, regime = _runtime_inputs()
    candidate = _candidate()
    result = helper(
        canonical=canonical,
        inputs={
            "rcpsp_spec": {"resource_pool": {"crane": 1}},
            "physical_rcpsp_max_states": 100_001,
        },
        mode="AUTO_SCHEDULE",
        schedule_selected=candidate,
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
        validacoes=[],
    )
    assert result.status == "FAIL"
    assert result.attempts == 0
    assert "between 1 and 100000" in result.reason


def test_auto_physical_resolver_rejects_unsupported_precedence_as_unknown(monkeypatch) -> None:
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    _patch_skill04_materializer(monkeypatch)
    predecessor = Predecessor("A")
    predecessor.tipo = "SF"  # unsupported by the physical witness contract
    items = (Item("A"), Item("B"))
    items[1]._predecessors = (predecessor,)
    canonical, regime = _runtime_inputs(items=items)
    candidate = _candidate(item_ids=("A", "B"))
    result = helper(
        canonical=canonical,
        inputs={"rcpsp_spec": {"resource_pool": {"crane": 1}}},
        mode="AUTO_SCHEDULE",
        schedule_selected=candidate,
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
        validacoes=[],
    )
    assert result.status == "UNKNOWN"
    assert "unsupported physical predecessor relation" in result.reason


@pytest.mark.parametrize(
    ("resolution_status", "expected_code"),
    [
        ("FAIL", "VAL-RCPSP-RESOLVE"),
        ("UNKNOWN", "VAL-RCPSP-RESOLVE-UNKNOWN"),
    ],
)
@pytest.mark.parametrize("certification_intent", ["PREVIEW", "CERTIFIED"])
def test_skill04_blocks_auto_schedule_when_physical_resolution_is_not_pass(
    monkeypatch, resolution_status: str, expected_code: str, certification_intent: str
) -> None:
    module = run_cronograma.__globals__
    stale = object()
    canonical = CanonicalModel.model_construct(
        meta=None,
        projeto=None,
        cronograma=stale,
        resultado=stale,
        resultado_reconciliado=stale,
        s_curve=stale,
        cubo_analitico=stale,
    )
    candidate = _candidate()
    monkeypatch.setitem(module, "_validate_preconditions", lambda *_: True)
    monkeypatch.setitem(module, "_build_cpu_lookup", lambda *_: {})
    monkeypatch.setitem(module, "_build_producao_lookup", lambda *_: {})
    monkeypatch.setitem(module, "_preflight_physical_productivity", lambda *args, **kwargs: (False, False))
    monkeypatch.setitem(
        module,
        "_run_cronograma_build_context",
        lambda *_: (
            SimpleNamespace(horas_dia=1.0, dias_semana=1.0, eta_jornada=1.0),
            list(WEEKS),
            {},
            {},
            {},
            {week: 1.0 for week in WEEKS},
            [],
        ),
    )
    monkeypatch.setitem(module, "_extract_praticabilidade", lambda *_: ({}, {}))
    monkeypatch.setitem(module, "_run_cronograma_validate_num_equipes_formato", lambda *_: True)
    monkeypatch.setitem(
        module,
        "_determine_mode_and_distribuicao",
        lambda *_: ("AUTO_SCHEDULE", {}, [candidate], candidate, False, [], set()),
    )
    monkeypatch.setitem(
        module,
        "resolve_skill04_physical_schedule",
        lambda **_: SimpleNamespace(
            status=resolution_status,
            schedule_selected=candidate,
            distribution_by_item={},
            fallback_item_ids=set(),
            attempts=4,
            reason="bounded physical calendar exhausted",
            violation_details=("V1_SCOPE_UNCLOSED:A:Q=1;sum_q=0",),
            complete_search=True,
        ),
    )
    monkeypatch.setitem(
        module,
        "_build_scheduled_activities",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("a rejected schedule must not be published")
        ),
    )

    outcome = run_cronograma(canonical, {"certification_intent": certification_intent})
    assert outcome.has_errors
    assert outcome.canonical.cronograma is None
    assert outcome.canonical.resultado is None
    assert any(v.codigo == expected_code and v.status == "ERRO" for v in outcome.validacoes)
    if resolution_status == "FAIL":
        assert any(v.codigo == "VAL-RCPSP-RESOLVE-DETAIL" for v in outcome.validacoes)
