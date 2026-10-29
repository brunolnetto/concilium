"""P15: Skill 04 calls the bounded resolver and revalidates rematerialized AUTO schedules."""
from __future__ import annotations

from datetime import date
from fractions import Fraction as F
from types import SimpleNamespace

from concilium.application.skills import run_cronograma
from concilium.domain.models.canonical import (
    CanonicalModel,
    DistribuicaoSemanal,
    ScheduleCandidateCanonical,
    ScheduledActivityCanonical,
)


WEEKS = ("2026-W01", "2026-W02", "2026-W03", "2026-W04")


class Item:
    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        self.cpu_id = f"CPU-{item_id}"
        self.quantitativo = 1.0

    def predecessores_tipados(self):
        return []


def _cell() -> DistribuicaoSemanal:
    return DistribuicaoSemanal(
        num_equipes=1,
        qtd_executada=1.0,
        qtd_acumulada=1.0,
        pct=1.0,
        q_max_celula=1.0,
        capacidade_disponivel_semana=1.0,
    )


def _candidate(resources: dict[str, int] | None = None) -> ScheduleCandidateCanonical:
    return ScheduleCandidateCanonical(
        heuristic="test",
        scheduled_activities=[
            ScheduledActivityCanonical(
                activity_id=item,
                start_week=0,
                end_week=0,
                duration_weeks=1,
                assigned_resources=resources if resources is not None else {"crane": 1},
            )
            for item in ("A", "B")
        ],
        makespan=1,
        quality_score=1.0,
    )


def _runtime_inputs(*, with_pool: bool = True):
    canonical = SimpleNamespace(
        eap=[Item("A"), Item("B")],
        atividades=[],
        recurso_pool=(
            [SimpleNamespace(
                proveniencia="CONFIGURADO",
                tipo_id="crane",
                quantidade_total=1,
            )]
            if with_pool else []
        ),
        projeto=SimpleNamespace(data_inicio=date(2026, 1, 5)),
    )
    regime = SimpleNamespace(horas_dia=1.0, dias_semana=1.0, eta_jornada=1.0)
    return canonical, regime


def _patch_skill04_materializer(monkeypatch) -> object:
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    p15 = __import__("sys").modules[helper.__module__]

    def build_distribution(scheduled, item, cpu, ramp, n_max, *args, **kwargs):
        week = WEEKS[scheduled.start_week]
        return {week: _cell()}, 1.0

    def convert(selected, canonical, weeks, *args, **kwargs):
        return {
            scheduled.activity_id: {weeks[scheduled.start_week]: _cell()}
            for scheduled in selected.scheduled_activities
        }, set()

    monkeypatch.setattr(p15, "_build_activity_distribuicao", build_distribution)
    monkeypatch.setattr(p15, "_convert_schedule_to_distribuicao", convert)
    monkeypatch.setattr(p15, "_resolve_productivity", lambda *_: (1.0, False))
    monkeypatch.setattr(p15, "_compute_activity_n_max", lambda *_: 1)
    monkeypatch.setattr(p15, "_origem_capacidade", lambda *_args, **_kwargs: "TAXA_POR_FRENTE_ASSUMIDA")
    return p15


def test_auto_runtime_re_resolves_resource_collision_and_audits_final_skill04_cells(monkeypatch) -> None:
    from concilium.application.skills.manifests import _unused  # noqa: F401
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    p15 = _patch_skill04_materializer(monkeypatch)
    canonical, regime = _runtime_inputs()
    candidate = _candidate()

    result = helper(
        canonical=canonical,
        inputs={"rcpsp_spec": {"resource_pool": {"crane": 1}}},
        mode="AUTO_SCHEDULE",
        schedule_selected=candidate,
        distribution_by_item={},
        fallback_item_ids=set(),
        weeks=list(WEEKS),
        cpu_lookup={"CPU-A": {"codigo": "CPU-A", "producao_id_ref": "prod"},
                    "CPU-B": {"codigo": "CPU-B", "producao_id_ref": "prod"}},
        production_lookup={"prod": {}},
        regime=regime,
        practicability_weekly={week: 1.0 for week in WEEKS},
        practicability_monthly={},
        calendar_factor_weekly={week: 1.0 for week in WEEKS},
        validacoes=[],
    )

    assert result.status == "PASS", result.reason
    assert result.attempts == 2
    assert result.schedule_selected is not None
    positions = {
        activity.activity_id: activity.start_week
        for activity in result.schedule_selected.scheduled_activities
    }
    assert positions == {"A": 0, "B": 1}
    assert result.distribution_by_item["A"][WEEKS[0]].qtd_executada == 1.0
    assert result.distribution_by_item["B"][WEEKS[1]].qtd_executada == 1.0
    assert any(v.codigo == "VAL-RCPSP-RESOLVED" for v in result_validations(result))


def result_validations(result):
    # The Skill04 resolver result intentionally does not own the issue-level
    # validation list. This helper keeps assertions about its finite witness
    # focused on the returned schedule/audit state.
    return []


def test_auto_physical_resolver_returns_unknown_when_pool_or_assignment_is_unproven(monkeypatch) -> None:
    helper = run_cronograma.__globals__["resolve_skill04_physical_schedule"]
    _patch_skill04_materializer(monkeypatch)
    canonical, regime = _runtime_inputs(with_pool=False)
    result = helper(
        canonical=canonical,
        inputs={"rcpsp_spec": {"activities": [{"item_id": "A"}]}},
        mode="AUTO_SCHEDULE",
        schedule_selected=_candidate(),
        distribution_by_item={},
        fallback_item_ids=set(),
        weeks=list(WEEKS),
        cpu_lookup={"CPU-A": {"codigo": "CPU-A", "producao_id_ref": "prod"},
                    "CPU-B": {"codigo": "CPU-B", "producao_id_ref": "prod"}},
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


def test_skill04_blocks_auto_schedule_when_physical_resolver_exhausts_calendar(monkeypatch) -> None:
    module = run_cronograma.__globals__
    stale = object()
    canonical = CanonicalModel.model_construct(
        meta=None, projeto=None, cronograma=stale, resultado=stale,
        resultado_reconciliado=stale, s_curve=stale, cubo_analitico=stale,
    )
    candidate = _candidate()
    monkeypatch.setitem(module, "_validate_preconditions", lambda *_: True)
    monkeypatch.setitem(module, "_build_cpu_lookup", lambda *_: {})
    monkeypatch.setitem(module, "_build_producao_lookup", lambda *_: {})
    monkeypatch.setitem(module, "_preflight_physical_productivity", lambda *args, **kwargs: (False, False))
    monkeypatch.setitem(
        module, "_run_cronograma_build_context",
        lambda *_: (
            SimpleNamespace(horas_dia=1.0, dias_semana=1.0, eta_jornada=1.0),
            list(WEEKS), {}, {}, {}, {week: 1.0 for week in WEEKS}, [],
        ),
    )
    monkeypatch.setitem(module, "_extract_praticabilidade", lambda *_: ({}, {}))
    monkeypatch.setitem(module, "_run_cronograma_validate_num_equipes_formato", lambda *_: True)
    monkeypatch.setitem(
        module, "_determine_mode_and_distribuicao",
        lambda *_: ("AUTO_SCHEDULE", {}, [candidate], candidate, False, [], set()),
    )
    monkeypatch.setitem(
        module, "resolve_skill04_physical_schedule",
        lambda **_: SimpleNamespace(
            status="FAIL", schedule_selected=candidate, distribution_by_item={},
            fallback_item_ids=set(), attempts=4, reason="bounded physical calendar exhausted",
            violation_details=("V1_SCOPE_UNCLOSED:A:Q=1;sum_q=0",),
        ),
    )
    monkeypatch.setitem(
        module, "_build_scheduled_activities",
        lambda *_: (_ for _ in ()).throw(AssertionError("a rejected schedule must not be published")),
    )

    outcome = run_cronograma(canonical, {"certification_intent": "PREVIEW"})
    assert outcome.has_errors
    assert outcome.canonical.cronograma is None
    assert outcome.canonical.resultado is None
    assert any(v.codigo == "VAL-RCPSP-RESOLVE" and v.status == "ERRO" for v in outcome.validacoes)
    assert any(v.codigo == "VAL-RCPSP-RESOLVE-DETAIL" for v in outcome.validacoes)
