"""One parser for rcpsp_spec.precedence: documented forms or a precise error."""

from __future__ import annotations

import pytest

from concilium.application.scheduling.rcpsp_precedence import PrecedenceEdge, parse_rcpsp_precedence


def test_documented_list_forms() -> None:
    assert parse_rcpsp_precedence([["A", "B"], ["B", "C", 0.5]]) == (
        PrecedenceEdge("A", "B", 1.0),
        PrecedenceEdge("B", "C", 0.5),
    )


def test_canonical_mapping_form_matches_activity_dag_edges() -> None:
    raw = [{"de": "A", "para": "B"}, {"de": "B", "para": "C", "tipo": "FS", "lag": 0, "completion_threshold_pct": 0.25}]
    assert parse_rcpsp_precedence(raw) == (PrecedenceEdge("A", "B", 1.0), PrecedenceEdge("B", "C", 0.25))


def test_missing_or_empty_is_no_edges() -> None:
    assert parse_rcpsp_precedence(None) == ()
    assert parse_rcpsp_precedence([]) == ()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"de": "A"}, r"precedence must be a list"),
        ([["A"]], r"precedence\[0\]: .*\[pred, succ\] or \[pred, succ, theta\]"),
        ([["A", "B", 0.5, 9]], r"precedence\[0\]"),
        ([{"de": "A", "para": "B", "tipo": "SS"}], r"precedence\[0\]: only FS.*EapItem.predecessores"),
        ([{"de": "A", "para": "B", "lag": 2}], r"precedence\[0\]: .*lag.*EapItem.predecessores"),
        ([{"pred": "A", "succ": "B"}], r"precedence\[0\]: unsupported keys"),
        ([["A", "B", 1.5]], r"precedence\[0\]: theta must be in \[0, 1\]"),
        ([["A", "B", "x"]], r"precedence\[0\]: theta must be a number"),
        ([["A", "A"]], r"precedence\[0\]: an activity cannot precede itself"),
        ([["", "B"]], r"precedence\[0\]: activity ids must be nonempty"),
        ([["A", "B"], ["A", "B", 0.5]], r"precedence\[1\]: duplicate edge A->B"),
        ([42], r"precedence\[0\]"),
    ],
)
def test_malformed_precedence_raises_a_located_error(raw, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_rcpsp_precedence(raw)


def _skill04_auto_canonical():
    from tests.unit.application.skills.test_skill_02_cronograma_auto_mode import _make_canonical

    return _make_canonical(num_activities=2, deadline_days=60)


def _spec(precedence) -> dict:
    return {
        "activities": [
            {"item_id": "eap-01", "descricao": "A", "duration_weeks": 2, "required_resources": {"maq": 1}},
            {"item_id": "eap-02", "descricao": "B", "duration_weeks": 2, "required_resources": {"maq": 1}},
        ],
        "resource_pool": {"maq": 1},
        "precedence": precedence,
        "deadline_weeks": 8,
    }


def test_skill04_reports_malformed_precedence_as_validation_error() -> None:
    """Previously crashed with `KeyError: 0` for a mapping entry."""
    from concilium.application.skills import run_cronograma

    result = run_cronograma(
        _skill04_auto_canonical(), {"rcpsp_spec": _spec([{"de": "eap-01", "lag": 2, "para": "eap-02"}])}
    )
    errors = [v for v in result.validacoes if v.codigo == "VAL-RCPSP-PRECEDENCE"]
    assert errors and errors[0].status == "ERRO"
    assert "precedence[0]" in errors[0].mensagem and "EapItem.predecessores" in errors[0].mensagem


def test_skill04_accepts_the_canonical_mapping_form() -> None:
    from concilium.application.skills import run_cronograma

    result = run_cronograma(_skill04_auto_canonical(), {"rcpsp_spec": _spec([{"de": "eap-01", "para": "eap-02"}])})
    assert not [v for v in result.validacoes if v.codigo == "VAL-RCPSP-PRECEDENCE"]
    sched = {a.activity_id: a for a in result.canonical.cronograma.scheduled_activities}
    assert sched["eap-02"].start_week >= sched["eap-01"].end_week


def test_skill05_does_not_build_pool_contracts_on_a_malformed_dag() -> None:
    from concilium.application.skills import run_equipes_e_alocacao

    result = run_equipes_e_alocacao(_skill04_auto_canonical(), {"rcpsp_spec": _spec([["eap-01"]])}, {})
    errors = [v for v in result.validacoes if v.codigo == "VAL-RCPSP-PRECEDENCE"]
    assert errors and errors[0].status == "ERRO" and "precedence[0]" in errors[0].mensagem
    assert result.canonical.contratos_recurso == []
