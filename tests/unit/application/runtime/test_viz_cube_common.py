"""Coverage sweep 6 — auth routes, calibration, cube_common, graph_exporter, catalog."""

from __future__ import annotations

# ─── cube/_common.py ──────────────────────────────────────────────────────────


class TestVizCubeCommon:
    def test_get_column_id_found(self):
        from concilium.application.runtime.deliverables.visualizations.cube._common import get_column_id

        cols = [{"id": "c1", "role": "label"}, {"id": "c2", "role": "value"}]
        assert get_column_id(cols, "label") == "c1"

    def test_get_column_id_not_found(self):
        from concilium.application.runtime.deliverables.visualizations.cube._common import get_column_id

        assert get_column_id([], "missing") is None

    def test_col_label_found(self):
        from concilium.application.runtime.deliverables.visualizations.cube._common import col_label

        cols = [{"id": "c1", "label": "My Label"}]
        assert col_label(cols, "c1") == "My Label"

    def test_col_label_fallback(self):
        from concilium.application.runtime.deliverables.visualizations.cube._common import col_label

        assert col_label([], None) == ""

    def test_is_weekly_labels_true(self):
        from concilium.application.runtime.deliverables.visualizations.cube._common import is_weekly_labels

        assert is_weekly_labels(["2026-W01", "2026-W02"])

    def test_is_weekly_labels_false(self):
        from concilium.application.runtime.deliverables.visualizations.cube._common import is_weekly_labels

        assert not is_weekly_labels(["Jan", "Feb"])

    def test_init_mpl_returns_plt(self):
        from concilium.application.runtime.deliverables.visualizations.cube._common import init_mpl

        plt, to_bytes = init_mpl()
        assert callable(to_bytes)








# _common.py line 70: col_label returns col_id when not found in columns
# ---------------------------------------------------------------------------


class TestColLabelFallback:
    def test_returns_col_id_when_not_found_in_columns(self):
        """Line 70: col_id not in any column → return col_id or ''."""
        from concilium.application.runtime.deliverables.visualizations.cube._common import col_label

        columns = [{"id": "tempo_natureza", "label": "Tempo × Natureza"}]
        result = col_label(columns, "NONEXISTENT_COL_ID")
        assert result == "NONEXISTENT_COL_ID"

    def test_returns_empty_when_col_id_is_none(self):
        """Coverage: col_id=None → if not col_id: return ''."""
        from concilium.application.runtime.deliverables.visualizations.cube._common import col_label

        assert col_label([], None) == ""


# ---------------------------------------------------------------------------

