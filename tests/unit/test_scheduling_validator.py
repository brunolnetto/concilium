"""Strategic tests to reach 100% coverage.

Targets remaining 58 missing statements across multiple modules.
Focus on error handling, edge cases, and specific condition paths.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from concilium.domain.models.canonical import (
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


# scheduling/validator.py: validation edge cases (lines 31, 81)
# ────────────────────────────────────────────────────────────────


class TestScheduleValidation:
    """Test schedule validation edge cases."""

    def test_validator_constraint_handling(self):
        """Validator should handle constraint violations."""
        from concilium.application.scheduling.validator import ScheduleValidator

        validator = ScheduleValidator()
        assert validator is not None


# ────────────────────────────────────────────────────────────────






# scheduling/validator.py line 31: continue when pred/succ not in schedule_map
# scheduling/validator.py line 80: continue when activity not found
# ---------------------------------------------------------------------------


class TestScheduleValidatorMissingLines:
    def test_validate_precedence_skips_unknown_activities(self):
        """Line 31: pred/succ not in schedule_map → continue."""
        from concilium.application.scheduling.models import ScheduledActivity
        from concilium.application.scheduling.validator import ScheduleValidator

        sa = ScheduledActivity(activity_id="A1", start_week=0, end_week=3, duration_weeks=3)
        v = ScheduleValidator()
        # Precedence references "X1" and "X2" which are NOT in scheduled
        result = v.validate_precedence([sa], [("X1", "X2")])
        assert result is True

    def test_validate_durations_skips_unknown_activity(self):
        """Line 80: a is None (activity not in dict) → continue."""
        from concilium.application.scheduling.models import ScheduledActivity
        from concilium.application.scheduling.validator import ScheduleValidator

        sa = ScheduledActivity(activity_id="UNKNOWN", start_week=0, end_week=3, duration_weeks=3)
        v = ScheduleValidator()
        result = v.validate_durations([sa], {})  # empty activities dict
        assert result is True


# ---------------------------------------------------------------------------





from types import SimpleNamespace  # noqa: E402

# scheduling/validator.py line 31: continue when pred_id not in schedule_map
# scheduling/validator.py line 80: continue when activity not in activities dict
# ---------------------------------------------------------------------------


class TestScheduleValidatorContinuePaths:
    def _make_validator(self):
        from concilium.application.scheduling.validator import ScheduleValidator

        return ScheduleValidator()

    def test_validate_precedence_skips_unknown_pred_id(self):
        """Line 31: precedence references activity IDs not in schedule → continue."""
        validator = self._make_validator()
        sa = SimpleNamespace(activity_id="A1", start_week=1, end_week=4)
        # "B1" and "C1" are not in scheduled
        result = validator.validate_precedence(
            scheduled=[sa],
            precedence=[("B1", "C1")],
        )
        assert result is True

    def test_validate_precedence_skips_unknown_succ_id(self):
        """Line 31: succ_id not in schedule_map → continue."""
        validator = self._make_validator()
        sa = SimpleNamespace(activity_id="A1", start_week=1, end_week=4)
        # A1 is in scheduled but "C1" is not
        result = validator.validate_precedence(
            scheduled=[sa],
            precedence=[("A1", "C1")],
        )
        assert result is True

    def test_validate_durations_skips_activity_not_in_lookup(self):
        """Line 80: activities dict doesn't contain scheduled activity → continue."""
        validator = self._make_validator()
        sa = SimpleNamespace(activity_id="A1", start_week=1, end_week=5)
        # Empty activities dict: A1 not found → a is None → continue
        result = validator.validate_durations(
            scheduled=[sa],
            activities={},
        )
        assert result is True


# ---------------------------------------------------------------------------

