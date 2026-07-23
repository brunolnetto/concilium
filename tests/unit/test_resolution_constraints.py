"""Coverage batch 27 — runner_utils, stage_discrepancy_summary,
constraints, resolver small gaps."""

from __future__ import annotations

from types import SimpleNamespace

# constraints.py line 110->125:
# cpu has dmt in attributes but cpu_dmt is None → if condition False → skip to 125
# ---------------------------------------------------------------------------


class TestStructuralCompatibilityDmtNone:
    def _make_filter(self):
        from concilium.application.resolution.constraints import ConstraintFilter

        return ConstraintFilter()

    def test_returns_passed_when_cpu_dmt_is_none(self):
        """Line 110->125: intent_dmt is not None, but cpu_dmt is None → if False → passed=True."""
        cf = self._make_filter()
        # cpu: activity_type=cut_fill, dmt in attributes but value is None
        cpu = SimpleNamespace(activity_type="cut_fill", attributes={"dmt": None})
        # intent: dimension_value("dmt") returns 500.0 (not None)
        intent = SimpleNamespace(dimension_value=lambda name: 500.0 if name == "dmt" else None)

        result = cf.check_structural_compatibility(intent, cpu)
        assert result.passed is True

    def test_returns_passed_when_intent_dmt_is_none(self):
        """Line 110->125: intent_dmt is None → if condition False → passed=True."""
        cf = self._make_filter()
        cpu = SimpleNamespace(activity_type="cut_fill", attributes={"dmt": 2000.0})
        # intent: no dmt dimension → dimension_value returns None
        intent = SimpleNamespace(dimension_value=lambda name: None)

        result = cf.check_structural_compatibility(intent, cpu)
        assert result.passed is True

    def test_returns_failed_when_dmt_exceeds_cpu_limit(self):
        """Normal path: both dmt not None, intent_dmt > upper → passed=False."""
        cf = self._make_filter()
        cpu = SimpleNamespace(activity_type="cut_fill", attributes={"dmt": 1000.0})
        intent = SimpleNamespace(dimension_value=lambda name: 9999.0 if name == "dmt" else None)

        result = cf.check_structural_compatibility(intent, cpu)
        assert result.passed is False


# ---------------------------------------------------------------------------

