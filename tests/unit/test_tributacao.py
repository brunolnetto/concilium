"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

from unittest.mock import patch

# tributacao.py line 82: fallback return when no INSS bracket matches
# ---------------------------------------------------------------------------


class TestCalculateInssLastBracketFallback:
    def test_fallback_when_no_bracket_matches(self):
        """Line 82: for loop exhausted → fallback return."""
        from concilium.domain.services.financial import tributacao

        fake_brackets = [(1_000.0, 0.07, 0.0)]
        with patch.object(tributacao, "INSS_BRACKETS_2026", fake_brackets):
            result = tributacao.calculate_inss_employee(50_000.0)
        assert result == round(8_475.55 * 0.07 - 0.0, 2)


# ---------------------------------------------------------------------------

