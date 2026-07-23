"""Coverage batch 19 — replanning/validator, completeness small gaps."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

# replanning/validator.py line 28->31: any(ERRO) True → do NOT append VAL-REPLAN-OK
# ---------------------------------------------------------------------------


class TestReplannValidatorErroPath:
    def test_val_replan_ok_not_appended_when_erro_present(self):
        """Line 28->31: validacoes has an ERRO item → if not any(...) is False → VAL-REPLAN-OK not added."""
        from concilium.application.replanning.models import ReplannCandidate
        from concilium.application.replanning.validator import ReplannValidator
        from concilium.domain.models.canonical import ValidacaoItem

        candidate = ReplannCandidate(
            name="Cand-Test",
            description="test candidate",
            schedule_delta_weeks=0.0,
        )
        canonical = SimpleNamespace(replanning_history=[])

        erro_item = ValidacaoItem(
            codigo="VAL-REPLAN-02",
            status="ERRO",
            mensagem="Forced error for coverage.",
        )

        # Patch _val_replan_02 to return an ERRO so the branch is covered
        with patch.object(ReplannValidator, "_val_replan_02", return_value=[erro_item]):
            validator = ReplannValidator()
            validacoes = validator.validate(candidate, canonical)

        codes = {v.codigo for v in validacoes}
        # ERRO present → VAL-REPLAN-OK should NOT be in the result
        assert "VAL-REPLAN-OK" not in codes
        assert "VAL-REPLAN-02" in codes

    def test_val_replan_ok_appended_when_no_erro(self):
        """Line 29: no ERRO items → VAL-REPLAN-OK is appended (normal path)."""
        from concilium.application.replanning.models import ReplannCandidate
        from concilium.application.replanning.validator import ReplannValidator

        candidate = ReplannCandidate(
            name="Cand-Normal",
            description="normal candidate",
            schedule_delta_weeks=0.0,
        )
        canonical = SimpleNamespace(replanning_history=[])

        validator = ReplannValidator()
        validacoes = validator.validate(candidate, canonical)

        codes = {v.codigo for v in validacoes}
        assert "VAL-REPLAN-OK" in codes


# ---------------------------------------------------------------------------

