"""P15: a post-solver physical pool collision must not publish a schedule."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem
from concilium.domain.models.project.constraint_violation import ConstraintViolation


def _skill04():
    from concilium.application.skills import run_cronograma

    assert run_cronograma
    return sys.modules["_concilium_skillpkg_04_cronograma.skill"]


def test_pool_violation_blocks_materialization_and_invalidates_stale_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _skill04()
    stale = object()
    canonical = CanonicalModel.model_construct(
        meta=None, projeto=None,
        cronograma=stale, resultado=stale,
        custos_atividades=[stale], ponto_equilibrio=[stale],
        intervalos_atividade=[stale],
        constraint_violations=[],
    )

    monkeypatch.setattr(mod, "_validate_preconditions", lambda *_: True)
    monkeypatch.setattr(
        mod, "_run_cronograma_build_context",
        lambda *_: (SimpleNamespace(), ["2026-W01"], {}, {}, {}, {}, []),
    )
    monkeypatch.setattr(mod, "_extract_praticabilidade", lambda *_: ({}, {}))
    monkeypatch.setattr(mod, "_run_cronograma_validate_num_equipes_formato", lambda *_: True)
    monkeypatch.setattr(
        mod, "_determine_mode_and_distribuicao",
        lambda *_: ("MANUAL_ALLOCATION", {"A": {}}, [], None, False, [], set()),
    )
    collision = ConstraintViolation(
        code="VAL-POOL-01", status="ERRO", magnitude=1,
        affected_items=["2026-W01"],
        remediation_hint="Reduce overlapping crane teams",
    )

    def mock_pool(_canonical, _dist, _cpus, validacoes):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POOL-01", status="ERRO",
                mensagem="crane requires two units, available one",
            )
        )
        return [collision]

    monkeypatch.setattr(mod, "_check_pool_violations", mock_pool)
    monkeypatch.setattr(
        mod, "_build_scheduled_activities",
        lambda *_: pytest.fail("invalid physical schedule must never be published"),
    )

    output = mod.run_cronograma(canonical, {})
    assert output.has_errors
    assert output.canonical.cronograma is None
    assert output.canonical.intervalos_atividade == []
    assert output.canonical.resultado is None
    assert output.canonical.custos_atividades == []
    assert output.canonical.ponto_equilibrio == []
    assert len(output.canonical.constraint_violations) == 1
    assert output.canonical.constraint_violations[0].code == "VAL-POOL-01"
    assert any(v.codigo == "VAL-POOL-01" and v.status == "ERRO" for v in output.validacoes)


def test_no_pool_information_is_not_a_false_zero_demand_certificate() -> None:
    # Missing capacity evidence is UNKNOWN at the physical validator layer,
    # not a proof that a project has an infinitely available resource pool.
    from fractions import Fraction

    from concilium.application.scheduling.physical_validator import (
        PhysicalActivity,
        validate_materialized_calendar,
    )

    physical = PhysicalActivity(
        item_id="A", scope=Fraction(1), start_week=0, end_week_exclusive=1,
        deliveries=((0, Fraction(1)),),
        weekly_capacities=((0, Fraction(1)),),
        demands=((0, "crane", Fraction(1)),),
    )
    audit = validate_materialized_calendar(
        (physical,), (), calendar_horizon_weeks=1, pool_capacity=None,
        require_weekly_capacity=True,
    )
    assert audit.status == "UNKNOWN"
