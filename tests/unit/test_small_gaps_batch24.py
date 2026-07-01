"""Coverage batch 24 — scoring, jobs/state, catalog_confronto,
report_calibration_sections, chart_markdown_support small gaps."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# scoring.py line 52->51: duplicate attribute → if a not in seen: False → continue
# ---------------------------------------------------------------------------


class TestAmCollectUniqueAttrsDuplicate:
    def test_duplicate_attr_is_deduped(self):
        """Line 52->51: 'a' appears twice → second occurrence seen → if False → skip."""
        from concilium.application.resolution.scoring import _am_collect_unique_attrs

        result = _am_collect_unique_attrs(["a", "b", "a"], [])
        assert result == ["a", "b"]  # 'a' deduplicated

    def test_overlap_between_required_and_optional(self):
        """Line 52->51: 'x' in required and optional → second occurrence skipped."""
        from concilium.application.resolution.scoring import _am_collect_unique_attrs

        result = _am_collect_unique_attrs(["x", "y"], ["x", "z"])
        assert result == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# scoring.py lines 163->167 and 164->167: context_fit branch misses
# ---------------------------------------------------------------------------


class TestContextFitBranchMisses:
    def _make_scorer(self):
        from concilium.application.resolution.scoring import FeatureExtractor

        return FeatureExtractor()

    def test_unknown_method_skips_all_branches(self):
        """Line 163->167: method not 'manual' or 'mechanized' → elif False → return 0.5."""
        scorer = self._make_scorer()
        intent = SimpleNamespace(context={"method": "mixed"}, method="mixed")
        cpu = SimpleNamespace(activity_type="grading")

        result = scorer.context_fit(intent, cpu)
        assert result == 0.5  # score unchanged

    def test_mechanized_with_unknown_activity_type(self):
        """Line 164->167: method=='mechanized', activity_type not in tuple → if False → return 0.5."""
        scorer = self._make_scorer()
        intent = SimpleNamespace(context={"method": "mechanized"}, method="mechanized")
        cpu = SimpleNamespace(activity_type="paving")  # not in ("cut_fill", "embankment_compaction")

        result = scorer.context_fit(intent, cpu)
        assert result == 0.5  # score unchanged

    def test_mechanized_with_cut_fill_returns_high_score(self):
        """Normal path: method=='mechanized', activity_type=='cut_fill' → score=0.8."""
        scorer = self._make_scorer()
        intent = SimpleNamespace(context={"method": "mechanized"}, method="mechanized")
        cpu = SimpleNamespace(activity_type="cut_fill")

        result = scorer.context_fit(intent, cpu)
        assert result == 0.8


# ---------------------------------------------------------------------------
# jobs/state.py line 158->161: status_atual is not any known enum → fall through
# ---------------------------------------------------------------------------


class TestCriarStateMachineUnknownStatus:
    def test_unknown_status_returns_sm_unchanged(self):
        """Line 158->161: status='UNKNOWN' → no elif matches → return sm at line 161."""
        from concilium.application.jobs.state import criar_state_machine

        sm = criar_state_machine({"job_id": "AABBCCDD", "status": "UNKNOWN"})
        assert sm is not None

    def test_default_status_aguardando_fila(self):
        """No status key → defaults to AGUARDANDO_FILA → all elif False → return sm."""
        from concilium.application.jobs.state import criar_state_machine

        sm = criar_state_machine({"job_id": "AABBCCDD"})
        assert sm is not None


# ---------------------------------------------------------------------------
# catalog_confronto.py line 65->64: item.engine_zerado is False → back to for loop
# catalog_confronto.py line 78: bench_data has a non-dir file → continue
# ---------------------------------------------------------------------------


class TestAnalyzeCatalogConfrontoEdgeCases:
    def test_item_with_engine_zerado_false_not_added(self):
        """Line 65->64: engine_zerado=False → if False → back to loop → planejamento_zerados stays []."""
        from concilium.application.benchmarks.comparison.catalog_confronto import (
            analyze_catalog_confronto,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slug = "BENCH-CONF"
            data_dir = root / "benchmarks" / "data" / slug
            data_dir.mkdir(parents=True)
            confronto = {
                "planejamento_confronto": {
                    "confronto": [
                        {"item_id": "EAP-01", "engine_zerado": False},  # False → skip
                        {"item_id": "EAP-02", "engine_zerado": None},  # None → falsy → skip
                    ]
                }
            }
            (data_dir / "confronto_catalogo.json").write_text(json.dumps(confronto), encoding="utf-8")

            result = analyze_catalog_confronto(slug, root=root)

        assert result.get("planejamento_zerados") == []

    def test_consolidate_all_skips_non_dir_entries(self):
        """Line 78: bench_data contains a regular file → not d.is_dir() → continue."""
        from concilium.application.benchmarks.comparison.catalog_confronto import (
            consolidate_all,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bench_data = root / "benchmarks" / "data"
            bench_data.mkdir(parents=True)
            # Add a regular file (not a dir) inside bench_data
            (bench_data / "README.txt").write_text("not a benchmark", encoding="utf-8")

            result = consolidate_all(root=root)

        # File was skipped, no benchmarks processed
        assert result["total_benchmarks"] == 0


# ---------------------------------------------------------------------------
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
# chart_markdown_support.py line 146->148:
# _xychart_bar_line returns None (empty labels) → if chart: False → go to exposicao check
# ---------------------------------------------------------------------------


class TestRenderFinancialMarkdownEmptyLabels:
    def test_chart_is_none_when_labels_empty(self):
        """Line 146->148: labels=[] → _xychart_bar_line returns None → if chart: False."""
        from concilium.application.runtime.deliverables.visualizations.chart_markdown_support import (
            _render_financial_markdown,
        )

        graficos = {
            "financeiro": {
                "labels": [],  # empty → xychart returns None
                "saldo": [100.0],  # non-empty → saldo and receita is True
                "receita": [200.0],
            }
        }
        result = _render_financial_markdown(graficos)
        # chart was None → the "### Fluxo de Caixa" block was not added
        assert not any("Fluxo de Caixa" in line for line in result)
