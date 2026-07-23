"""Tests for several small modules to boost coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─── png_bundle ─────────────────────────────────────────────────────────────


class TestBuildVisualizationPngFiles:
    def test_empty_relatorio_returns_empty(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            result = build_visualization_png_files({})
        assert result == {}

    def test_graficos_section_forwarded(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        relatorio = {"GRAFICOS": {"gantt": {}}}
        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={"gantt.png": b"x"},
            ) as mock_charts,
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            result = build_visualization_png_files(relatorio)
        mock_charts.assert_called_once_with({"gantt": {}})
        assert "gantt.png" in result

    def test_cube_pngs_merged(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        canonical = MagicMock()
        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={"cube.png": b"y"},
            ),
        ):
            result = build_visualization_png_files({}, canonical=canonical)
        assert "cube.png" in result

    def test_non_dict_relatorio_skips_graficos(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ) as mock_charts,
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            build_visualization_png_files("not a dict")
        # graficos is {} when relatorio is not a dict → build_chart_png_files NOT called (empty graficos skipped)
        mock_charts.assert_not_called()

    def test_graficos_not_dict_skips_charts(self):
        from concilium.application.runtime.deliverables.visualizations.png_bundle import build_visualization_png_files

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_chart_png_files",
                return_value={},
            ) as mock_charts,
            patch(
                "concilium.application.runtime.deliverables.visualizations.png_bundle.build_analytic_cube_png_files",
                return_value={},
            ),
        ):
            build_visualization_png_files({"GRAFICOS": "invalid"})
        # "invalid" is not a dict → charts skipped
        mock_charts.assert_not_called()



