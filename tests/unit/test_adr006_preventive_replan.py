"""Tests for ADR-006: ConstraintValidator (preventive planning validation).

Covers:
  - C2 deadline constraint (VAL-SCHED-WEEKLY-03)
  - C3 resource pool constraint (VAL-SCHED-WEEKLY-05)
  - F1 budget constraint (VAL-INDIRETOS-04)
  - ReplannGenerator producing 3 strategic options for Tier 3
  - Multiple violations combined
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from concilium.application.scheduling.constraint_validator import ConstraintValidator

# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_canonical(
    makespan_weeks: int = 20,
    data_inicio: date = date(2026, 1, 1),
    data_termino: date = date(2026, 12, 31),
    conflitos_pico: list | None = None,
    indiretos_total: float = 0.0,
    no_cronograma: bool = False,
) -> MagicMock:
    """Build a minimal canonical mock for ConstraintValidator tests."""
    canonical = MagicMock()
    canonical.projeto.data_inicio = data_inicio
    canonical.projeto.data_termino = data_termino

    if no_cronograma:
        canonical.cronograma = None
    else:
        canonical.cronograma = MagicMock()
        canonical.cronograma.makespan_weeks = makespan_weeks
        canonical.cronograma.scheduled_activities = [MagicMock()]  # non-empty

    canonical.conflitos_pico = conflitos_pico or []

    if indiretos_total > 0:
        ind = MagicMock()
        ind.custo_total = indiretos_total
        canonical.indiretos = [ind]
    else:
        canonical.indiretos = []

    return canonical


def _make_conflito(
    excedente: float = 2.0,
    tipo_nome: str = "operador",
    quantidade_necessaria: float = 5.0,
    quantidade_disponivel: int = 3,
    atividades_conflitantes: list[str] | None = None,
) -> MagicMock:
    c = MagicMock()
    c.excedente = excedente
    c.tipo_nome = tipo_nome
    c.quantidade_necessaria = quantidade_necessaria
    c.quantidade_disponivel = quantidade_disponivel
    c.atividades_conflitantes = atividades_conflitantes or []
    return c


# ─── C2: deadline ─────────────────────────────────────────────────────────────


class TestDeadlineConstraint:
    def test_feasible_plan_no_c2_violation(self):
        """Makespan within contract → no VAL-SCHED-WEEKLY-03."""
        canonical = _make_canonical(
            makespan_weeks=20,
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),  # 52+ weeks
        )
        violations = ConstraintValidator().validate(canonical)
        assert not any(v.code == "VAL-SCHED-WEEKLY-03" for v in violations)

    def test_makespan_exceeds_contract_generates_erro(self):
        """Makespan > contract weeks → ERRO violation."""
        start = date(2026, 1, 1)
        end = start + timedelta(weeks=10)  # 10-week contract
        canonical = _make_canonical(
            makespan_weeks=15,
            data_inicio=start,
            data_termino=end,
        )
        violations = ConstraintValidator().validate(canonical)
        c2 = [v for v in violations if v.code == "VAL-SCHED-WEEKLY-03"]
        assert len(c2) == 1
        assert c2[0].status == "ERRO"

    def test_deadline_magnitude_equals_excess_weeks(self):
        """C2 magnitude == makespan - contract_weeks."""
        start = date(2026, 1, 1)
        end = start + timedelta(weeks=10)
        canonical = _make_canonical(
            makespan_weeks=14,
            data_inicio=start,
            data_termino=end,
        )
        violations = ConstraintValidator().validate(canonical)
        c2 = [v for v in violations if v.code == "VAL-SCHED-WEEKLY-03"]
        assert c2[0].magnitude == 4.0  # 14 - 10

    def test_no_cronograma_skips_c2_check(self):
        """No cronograma → C2 check silently skipped."""
        canonical = _make_canonical(no_cronograma=True)
        violations = ConstraintValidator().validate(canonical)
        assert not any(v.code == "VAL-SCHED-WEEKLY-03" for v in violations)

    def test_c2_remediation_hint_mentions_options(self):
        """C2 hint mentions the three ADR-006 options."""
        start = date(2026, 1, 1)
        end = start + timedelta(weeks=5)
        canonical = _make_canonical(makespan_weeks=10, data_inicio=start, data_termino=end)
        violations = ConstraintValidator().validate(canonical)
        hint = violations[0].remediation_hint or ""
        assert "prazo" in hint.lower() or "recursos" in hint.lower() or "escopo" in hint.lower()


# ─── C3: resource pool ────────────────────────────────────────────────────────


class TestResourcePoolConstraint:
    def test_no_conflitos_no_c3_violation(self):
        """Empty conflitos_pico → no VAL-SCHED-WEEKLY-05."""
        canonical = _make_canonical(conflitos_pico=[])
        violations = ConstraintValidator().validate(canonical)
        assert not any(v.code == "VAL-SCHED-WEEKLY-05" for v in violations)

    def test_one_conflito_generates_one_c3_violation(self):
        """One conflito_pico → one ERRO with correct magnitude."""
        canonical = _make_canonical(conflitos_pico=[_make_conflito(excedente=2.0)])
        violations = ConstraintValidator().validate(canonical)
        c3 = [v for v in violations if v.code == "VAL-SCHED-WEEKLY-05"]
        assert len(c3) == 1
        assert c3[0].status == "ERRO"
        assert c3[0].magnitude == 2.0

    def test_multiple_conflitos_generate_multiple_violations(self):
        """Three conflitos → three separate violations."""
        conflitos = [_make_conflito(excedente=float(i + 1)) for i in range(3)]
        canonical = _make_canonical(conflitos_pico=conflitos)
        violations = ConstraintValidator().validate(canonical)
        c3 = [v for v in violations if v.code == "VAL-SCHED-WEEKLY-05"]
        assert len(c3) == 3

    def test_c3_affected_items_contain_conflicting_activities(self):
        """C3 affected_items lists the conflicting activities."""
        conflito = _make_conflito(atividades_conflitantes=["EXCAV-01", "COMPAC-02"])
        canonical = _make_canonical(conflitos_pico=[conflito])
        violations = ConstraintValidator().validate(canonical)
        c3 = [v for v in violations if v.code == "VAL-SCHED-WEEKLY-05"]
        assert "EXCAV-01" in c3[0].affected_items
        assert "COMPAC-02" in c3[0].affected_items


# ─── F1: budget ───────────────────────────────────────────────────────────────


class TestBudgetConstraint:
    def test_within_budget_no_f1_violation(self):
        """Indiretos total ≤ budget → no VAL-INDIRETOS-04."""
        canonical = _make_canonical(indiretos_total=500_000.0)
        violations = ConstraintValidator().validate(canonical, budget_indiretos=600_000.0)
        assert not any(v.code == "VAL-INDIRETOS-04" for v in violations)

    def test_budget_exceeded_generates_f1_erro(self):
        """Indiretos total > budget → ERRO with correct magnitude."""
        canonical = _make_canonical(indiretos_total=700_000.0)
        violations = ConstraintValidator().validate(canonical, budget_indiretos=600_000.0)
        f1 = [v for v in violations if v.code == "VAL-INDIRETOS-04"]
        assert len(f1) == 1
        assert f1[0].status == "ERRO"
        assert f1[0].magnitude == pytest.approx(100_000.0)

    def test_budget_check_skipped_when_not_provided(self):
        """No budget_indiretos arg → F1 check not performed."""
        canonical = _make_canonical(indiretos_total=999_999_999.0)
        violations = ConstraintValidator().validate(canonical)
        assert not any(v.code == "VAL-INDIRETOS-04" for v in violations)


# ─── combined + replanning ────────────────────────────────────────────────────


class TestCombinedAndReplanning:
    def test_multiple_constraint_types_all_reported(self):
        """C2 + C3 + F1 violations all returned in one validate() call."""
        start = date(2026, 1, 1)
        end = start + timedelta(weeks=5)
        conflito = _make_conflito(excedente=1.0)
        canonical = _make_canonical(
            makespan_weeks=10,
            data_inicio=start,
            data_termino=end,
            conflitos_pico=[conflito],
            indiretos_total=200_000.0,
        )
        violations = ConstraintValidator().validate(canonical, budget_indiretos=100_000.0)
        codes = {v.code for v in violations}
        assert "VAL-SCHED-WEEKLY-03" in codes
        assert "VAL-SCHED-WEEKLY-05" in codes
        assert "VAL-INDIRETOS-04" in codes

    def test_t3_generator_produces_three_or_more_candidates(self):
        """ReplannGenerator.generate_candidates() for Tier 3 produces ≥ 3 options (ADR-006 D2)."""
        from concilium.application.replanning.generator import ReplannGenerator
        from concilium.application.replanning.models import ReplannTrigger

        canonical = _make_canonical()
        trigger = ReplannTrigger(tier=3, code="T3-DEADLINE", days_late=28)
        candidates = ReplannGenerator().generate_candidates(canonical, trigger)

        assert len(candidates) >= 3
        names = [c.name for c in candidates]
        # Must cover the three ADR-006 options: relax, add, reduce
        assert any("prazo" in n.lower() or "extensão" in n.lower() for n in names), (
            "Expected a deadline extension option"
        )
        assert any("recurso" in n.lower() or "pool" in n.lower() or "equipe" in n.lower() for n in names), (
            "Expected an add-resource option"
        )
        assert any("escopo" in n.lower() or "redução" in n.lower() or "adiar" in n.lower() for n in names), (
            "Expected a scope reduction option"
        )
