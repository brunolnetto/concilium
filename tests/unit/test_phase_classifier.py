"""Coverage batch 8 — scoring, resolver, phase_classifier, catalogo, health."""

from __future__ import annotations

# phase_classifier.py lines 169, 193, 198: simple function calls
# ---------------------------------------------------------------------------


class TestPhaseClassifierSimpleFunctions:
    def test_resolve_skill_id_unknown_returns_input(self):
        """Line 169: skill_id not in aliases → return skill_id unchanged."""
        from concilium.application.skills.phase_classifier import resolve_skill_id

        result = resolve_skill_id("99-nonexistent-skill")
        assert result == "99-nonexistent-skill"

    def test_resolve_skill_id_known_alias(self):
        """Line 169: skill_id in aliases → return mapped id."""
        from concilium.application.skills.phase_classifier import SKILL_ID_ALIASES, resolve_skill_id

        if SKILL_ID_ALIASES:
            alias_key = next(iter(SKILL_ID_ALIASES))
            result = resolve_skill_id(alias_key)
            assert result == SKILL_ID_ALIASES[alias_key]

    def test_get_phase_skills_returns_list(self):
        """Line 193: get_phase_skills with valid phase → returns list of skill ids."""
        from concilium.application.skills.phase_classifier import get_phase_skills

        result = get_phase_skills("Planejamento")
        assert isinstance(result, list)

    def test_get_phase_skills_unknown_phase_returns_empty(self):
        """Line 193: get_phase_skills with unknown phase → returns []."""
        from concilium.application.skills.phase_classifier import get_phase_skills

        result = get_phase_skills("NonExistentPhase")
        assert result == []

    def test_get_all_phases_returns_list_of_strings(self):
        """Line 198: get_all_phases() → list of str."""
        from concilium.application.skills.phase_classifier import get_all_phases

        result = get_all_phases()
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(p, str) for p in result)


# ---------------------------------------------------------------------------

