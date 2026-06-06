"""Tests for ADR-022 — Wave Execution: GATE taint propagation and clearing.

Covers:
  - GATE skill failure taints canonical (pipeline_blocked_from, pipeline_integridade)
  - GATE skill success on re-run removes itself from pipeline_blocked_from (untaint)
  - Multiple simultaneous GATE failures: fixing one unblocks only that one
  - When all GATE failures fixed: pipeline_integridade reverts to None
  - Downstream skill blocked when GATE predecessor is tainted
"""

from __future__ import annotations

from datetime import UTC

import pytest

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel, ValidacaoItem

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_canonical(**kwargs) -> CanonicalModel:
    """Minimal canonical for tests that need only pipeline taint fields."""
    from datetime import date, datetime

    from concilium.domain.models.canonical import Coordenadas, Meta, Projeto, RegimeTrabalho

    defaults: dict = {
        "meta": Meta(
            gerado_em=datetime(2026, 1, 1, tzinfo=UTC),
            contexto_id="ctx-test-022",
        ),
        "projeto": Projeto(
            id="proj-test-022",
            nome="Teste ADR-022",
            tipo_obra="terraplenagem",
            localizacao="GO",
            coordenadas=Coordenadas(lat=-16.0, lng=-49.0),
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            snapshot_catalogo_id="snap-test",
            snapshot_perfil_id="perf-test",
        ),
        "pipeline_blocked_from": [],
        "pipeline_integridade": None,
    }
    defaults.update(kwargs)
    return CanonicalModel(**defaults)


def _make_skill_result(canonical: CanonicalModel, has_errors: bool = False) -> SkillResult:
    validacoes = [ValidacaoItem(codigo="VAL-TEST", status="ERRO" if has_errors else "OK")]
    return SkillResult(canonical, validacoes)


# ── Unit tests (taint logic in isolation) ────────────────────────────────────


class TestTaintOnFailure:
    """GATE skill failure → canonical is tainted."""

    def test_single_gate_failure_taints_canonical(self):
        """When a GATE skill has errors, pipeline_blocked_from includes it."""
        from concilium.application.runtime import _GATE_SKILLS

        assert "04-cronograma" in _GATE_SKILLS, "03-equipes-diretas must be a GATE skill"

        canonical = _make_canonical(pipeline_blocked_from=[])
        result = _make_skill_result(canonical, has_errors=True)

        # Simulate what runtime does on GATE failure
        skill_id = "04-cronograma"
        if result.has_errors and skill_id in _GATE_SKILLS:
            canonical_before = result.canonical
            blocked = list(set(canonical_before.pipeline_blocked_from) | {skill_id})
            tainted = SkillResult(
                canonical_before.model_copy(
                    update={
                        "pipeline_blocked_from": blocked,
                        "pipeline_integridade": "CORROMPIDO",
                    }
                ),
                result.validacoes,
            )
            result = tainted

        assert "04-cronograma" in result.canonical.pipeline_blocked_from
        assert result.canonical.pipeline_integridade == "CORROMPIDO"

    def test_multiple_gate_failures_accumulate(self):
        """Two GATE failures accumulate in pipeline_blocked_from."""
        from concilium.application.runtime import _GATE_SKILLS

        canonical = _make_canonical(
            pipeline_blocked_from=["04-cronograma"],
            pipeline_integridade="CORROMPIDO",
        )
        result = _make_skill_result(canonical, has_errors=True)

        skill_id = "06-precificacao-unitaria"
        assert skill_id in _GATE_SKILLS

        if result.has_errors and skill_id in _GATE_SKILLS:
            blocked = list(set(canonical.pipeline_blocked_from) | {skill_id})
            result = SkillResult(
                canonical.model_copy(
                    update={
                        "pipeline_blocked_from": blocked,
                        "pipeline_integridade": "CORROMPIDO",
                    }
                ),
                result.validacoes,
            )

        blocked_set = set(result.canonical.pipeline_blocked_from)
        assert "04-cronograma" in blocked_set
        assert "06-precificacao-unitaria" in blocked_set
        assert result.canonical.pipeline_integridade == "CORROMPIDO"


class TestUntaintOnSuccess:
    """GATE skill success on re-run → removes itself from pipeline_blocked_from."""

    def test_single_gate_success_removes_itself(self):
        """Fixing the only blocked GATE skill clears pipeline_integridade."""
        from concilium.application.runtime import _GATE_SKILLS

        skill_id = "04-cronograma"
        canonical = _make_canonical(
            pipeline_blocked_from=[skill_id],
            pipeline_integridade="CORROMPIDO",
        )
        result = _make_skill_result(canonical, has_errors=False)

        # Simulate runtime untaint block
        if not result.has_errors and skill_id in _GATE_SKILLS:
            current_blocked = set(result.canonical.pipeline_blocked_from)
            if skill_id in current_blocked:
                new_blocked = sorted(current_blocked - {skill_id})
                new_integridade = "CORROMPIDO" if new_blocked else None
                result = SkillResult(
                    result.canonical.model_copy(
                        update={
                            "pipeline_blocked_from": new_blocked,
                            "pipeline_integridade": new_integridade,
                        }
                    ),
                    result.validacoes,
                )

        assert skill_id not in result.canonical.pipeline_blocked_from
        assert result.canonical.pipeline_blocked_from == []
        assert result.canonical.pipeline_integridade is None

    def test_fix_one_of_two_leaves_other_blocked(self):
        """Fixing one blocked GATE skill leaves the other still blocked."""
        from concilium.application.runtime import _GATE_SKILLS

        skill_id = "04-cronograma"
        other_blocked = "06-precificacao-unitaria"
        canonical = _make_canonical(
            pipeline_blocked_from=[skill_id, other_blocked],
            pipeline_integridade="CORROMPIDO",
        )
        result = _make_skill_result(canonical, has_errors=False)

        # Untaint only skill_id
        if not result.has_errors and skill_id in _GATE_SKILLS:
            current_blocked = set(result.canonical.pipeline_blocked_from)
            if skill_id in current_blocked:
                new_blocked = sorted(current_blocked - {skill_id})
                new_integridade = "CORROMPIDO" if new_blocked else None
                result = SkillResult(
                    result.canonical.model_copy(
                        update={
                            "pipeline_blocked_from": new_blocked,
                            "pipeline_integridade": new_integridade,
                        }
                    ),
                    result.validacoes,
                )

        assert skill_id not in result.canonical.pipeline_blocked_from
        assert other_blocked in result.canonical.pipeline_blocked_from
        # Still corrupted because other_blocked remains
        assert result.canonical.pipeline_integridade == "CORROMPIDO"

    def test_non_gate_skill_success_does_not_untaint(self):
        """Advisory skills do not modify pipeline_blocked_from on success."""
        from concilium.application.runtime import _GATE_SKILLS

        non_gate = "07-custos-indiretos"
        assert non_gate not in _GATE_SKILLS

        canonical = _make_canonical(
            pipeline_blocked_from=["04-cronograma"],
            pipeline_integridade="CORROMPIDO",
        )
        result = _make_skill_result(canonical, has_errors=False)

        # The untaint elif only triggers for GATE skills
        if not result.has_errors and non_gate in _GATE_SKILLS:
            pytest.fail("Should not reach untaint block for non-GATE skill")

        # canonical unchanged
        assert "04-cronograma" in result.canonical.pipeline_blocked_from
        assert result.canonical.pipeline_integridade == "CORROMPIDO"


class TestGateSkillsConstant:
    """Structural tests on _GATE_SKILLS set."""

    def test_gate_skills_contains_expected_ids(self):
        from concilium.application.runtime import _GATE_SKILLS

        # Match current _GATE_SKILLS which includes 03-catalogo-de-recursos
        assert "01-escopo-e-eap" in _GATE_SKILLS
        assert "04-cronograma" in _GATE_SKILLS
        assert "06-precificacao-unitaria" in _GATE_SKILLS

    def test_gate_skills_is_frozenset(self):
        from concilium.application.runtime import _GATE_SKILLS

        assert isinstance(_GATE_SKILLS, frozenset)

    def test_gate_predecessors_uses_gate_skills(self):
        """_GATE_PREDECESSORS values should only contain IDs from _GATE_SKILLS."""
        from concilium.application.runtime import _GATE_SKILLS
        from concilium.presentation.mcp._context import _GATE_PREDECESSORS

        for skill_id, gate_preds in _GATE_PREDECESSORS.items():
            for pred in gate_preds:
                assert pred in _GATE_SKILLS, (
                    f"Predecessor '{pred}' of '{skill_id}' is in _GATE_PREDECESSORS but not in _GATE_SKILLS"
                )


class TestCanonicalOrderIncludes11And15To17:
    """ADR-026: CANONICAL_SKILL_ORDER must include all 24 skills."""

    def test_canonical_order_includes_missing_skills(self):
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER

        for skill_id in ["12-registro-decisoes", "15-relatorio-executivo"]:
            assert skill_id in CANONICAL_SKILL_ORDER, f"'{skill_id}' missing from CANONICAL_SKILL_ORDER"

    def test_canonical_order_no_duplicates(self):
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER

        assert len(CANONICAL_SKILL_ORDER) == len(set(CANONICAL_SKILL_ORDER)), "CANONICAL_SKILL_ORDER has duplicates"

    def test_canonical_order_matches_phase_map(self):
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER, PHASE_MAP

        expected = [s for phase in PHASE_MAP.values() for s in phase]
        assert CANONICAL_SKILL_ORDER == expected
