"""Tests for several small modules to boost coverage."""

from __future__ import annotations

# ─── charts/_common ────────────────────────────────────────────────────────


class TestChartsCommon:
    def test_clean_series_label_known(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import clean_series_label

        assert clean_series_label("overhead_AC") == "Adm. Central (AC)"
        assert clean_series_label("overhead_L") == "Lucro (L)"
        assert clean_series_label("tributo_ISS") == "ISS"

    def test_clean_series_label_unknown_replaces_underscore(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import clean_series_label

        result = clean_series_label("my_custom_label")
        assert "_" not in result

    def test_init_mpl_returns_plt_and_fn(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import init_mpl

        plt, fig_to_bytes = init_mpl()
        assert callable(fig_to_bytes)

    def test_fig_to_bytes_returns_bytes(self):
        from concilium.application.runtime.deliverables.visualizations.charts._common import init_mpl

        plt, fig_to_bytes = init_mpl()
        fig, ax = plt.subplots()
        result = fig_to_bytes(fig)
        assert isinstance(result, bytes)
        assert len(result) > 0



