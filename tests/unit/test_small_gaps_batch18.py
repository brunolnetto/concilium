"""Coverage batch 18 — helpers, confidence, catalog_confronto small gaps."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# helpers.py line 48: _find_eap_item returns None when not found
# helpers.py line 31->40: _project_months branch when data_inicio is None
# ---------------------------------------------------------------------------


class TestFindEapItemReturnsNone:
    def test_returns_none_when_not_found(self):
        """Line 48: loop exhausted without match → return None."""
        from concilium.infrastructure.adapters.excel.helpers import _find_eap_item

        item = SimpleNamespace(item_id="ITEM-01")
        result = _find_eap_item([item], "NONEXISTENT-ID")
        assert result is None

    def test_returns_none_from_empty_list(self):
        """Line 48: empty list → for loop body never executes → return None."""
        from concilium.infrastructure.adapters.excel.helpers import _find_eap_item

        assert _find_eap_item([], "ANY-ID") is None


class TestProjectMonthsNullDataInicio:
    def test_returns_empty_when_data_inicio_is_none(self):
        """Line 31->40: projeto exists but data_inicio is None → if False → return []."""
        from concilium.infrastructure.adapters.excel.helpers import _project_months

        canonical = SimpleNamespace(
            cronograma=None,
            projeto=SimpleNamespace(data_inicio=None, data_termino=date(2026, 12, 31)),
        )
        result = _project_months(canonical)
        assert result == []

    def test_returns_empty_when_data_termino_is_none(self):
        """Line 31->40: projeto has data_termino=None → if check False → return []."""
        from concilium.infrastructure.adapters.excel.helpers import _project_months

        canonical = SimpleNamespace(
            cronograma=None,
            projeto=SimpleNamespace(data_inicio=date(2026, 1, 1), data_termino=None),
        )
        result = _project_months(canonical)
        assert result == []


# ---------------------------------------------------------------------------
# confidence.py line 143->146: close < 2 → 'low_discriminative_power' NOT appended
# ---------------------------------------------------------------------------


class TestConfidenceDetectEmbeddingFailureModes:
    def test_not_flagged_when_close_less_than_2(self):
        """Line 143->146 branch: 3+ candidates but only 1 within 0.05 of top → close=1 < 2."""
        from concilium.application.resolution.confidence import ConfidenceAssigner

        assigner = ConfidenceAssigner()
        # top_score=0.9, second=0.87 (within 0.05), third=0.5 (not within 0.05) → close=1
        cand_top = SimpleNamespace(score=0.9, explanations=[])
        cand_close = SimpleNamespace(score=0.87, explanations=[])
        cand_far = SimpleNamespace(score=0.5, explanations=[])

        failures = assigner._detect_embedding_failure_modes(cand_top, [cand_top, cand_close, cand_far])
        assert "low_discriminative_power" not in failures

    def test_flagged_when_close_ge_2(self):
        """Line 144: close >= 2 → 'low_discriminative_power' appended."""
        from concilium.application.resolution.confidence import ConfidenceAssigner

        assigner = ConfidenceAssigner()
        # top=0.9, second=0.87 (close), third=0.86 (close) → close=2 → flagged
        cand_top = SimpleNamespace(score=0.9, explanations=[])
        cand_2 = SimpleNamespace(score=0.87, explanations=[])
        cand_3 = SimpleNamespace(score=0.86, explanations=[])

        failures = assigner._detect_embedding_failure_modes(cand_top, [cand_top, cand_2, cand_3])
        assert "low_discriminative_power" in failures


# ---------------------------------------------------------------------------
# catalog_confronto.py line 80->76: analyze_catalog_confronto returns {} → if issues: False
# ---------------------------------------------------------------------------


class TestConsolidateAllSkipsEmptyIssues:
    def test_empty_issues_not_appended_to_results(self):
        """Line 80->76: slug dir has no confronto_catalogo.json → analyze returns {}
        → if issues: False → not appended → results stays []."""
        from concilium.application.benchmarks.comparison.catalog_confronto import consolidate_all

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bench_data = root / "benchmarks" / "data"
            bench_data.mkdir(parents=True)
            # Create a slug directory WITHOUT confronto_catalogo.json
            (bench_data / "SLUG-NO-CONFRONTO").mkdir()

            result = consolidate_all(root=root)

            # No issues → results list stays empty → summary has 0 totals
            assert result["total_benchmarks"] == 0
            assert result["total_cpus_nao_encontradas"] == 0
            assert result["benchmarks"] == []
