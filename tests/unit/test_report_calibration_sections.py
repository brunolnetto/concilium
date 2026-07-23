"""Coverage sweep 6 — auth routes, calibration, cube_common, graph_exporter, catalog."""

from __future__ import annotations

# ─── report_calibration_sections.py ─────────────────────────────────────────


class TestReportCalibrationSections:
    def test_f_converts_float(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _f

        assert _f(1.5) == 1.5
        assert _f(None) == 0.0
        assert _f("bad") == 0.0

    def test_money_formats(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _money

        result = _money(1_000_000.0)
        assert "1" in result

    def test_pct_formats(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _pct

        result = _pct(0.15)
        assert "%" in result or "15" in result

    def test_sum_pe_field(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _sum_pe_field

        rows = [{"a": 1.0}, {"a": 2.0}, {"b": 5.0}]
        assert _sum_pe_field(rows, "a") == 3.0
        assert _sum_pe_field(rows, "missing") == 0.0

    def test_render_dict_insights(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _render_dict_insights

        result = _render_dict_insights({"key": "value", "num": 42})
        assert isinstance(result, list)
        assert len(result) > 0

    def test_render_list_insights(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import _render_list_insights

        result = _render_list_insights(["item1", "item2"])
        assert isinstance(result, list)
        assert len(result) == 2

    def test_render_equilibrium_section_empty(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import (
            render_equilibrium_section,
        )

        result = render_equilibrium_section([], {})
        assert isinstance(result, list)

    def test_render_insights_section_dict(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import (
            render_insights_section,
        )

        result = render_insights_section({"key": "val"})
        assert isinstance(result, list)

    def test_render_insights_section_none(self):
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import (
            render_insights_section,
        )

        result = render_insights_section(None)
        assert isinstance(result, list)









# report_calibration_sections.py line 119->121:
# isinstance(insights, list) False → skip to lines += [..., "---", ...]
# ---------------------------------------------------------------------------


class TestRenderInsightsSectionNonListNonDict:
    def test_string_insights_skips_both_branches(self):
        """Line 119->121: insights is a string → not dict, not list → skip both → add footer."""
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import (
            render_insights_section,
        )

        result = render_insights_section("plain string insight")
        # Neither dict nor list → no content added, just footer
        assert "## Recomendações Técnicas" in result
        assert "---" in result

    def test_integer_insights_skips_both_branches(self):
        """Line 119->121: insights is an int → not dict, not list → skip."""
        from concilium.application.runtime.deliverables.reports.report_calibration_sections import (
            render_insights_section,
        )

        result = render_insights_section(42)
        assert "---" in result


# ---------------------------------------------------------------------------

