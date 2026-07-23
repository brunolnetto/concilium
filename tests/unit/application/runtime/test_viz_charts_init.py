"""Tests for several small modules to boost coverage."""

from __future__ import annotations

from unittest.mock import patch

# ─── charts/__init__ (build_all) ───────────────────────────────────────────


class TestChartsInit:
    def test_build_all_empty_graficos(self):
        from concilium.application.runtime.deliverables.visualizations.charts import build_all

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_equipamentos",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_mao_obra",
                return_value=None,
            ),
            patch("concilium.application.runtime.deliverables.visualizations.charts.build_gantt", return_value=None),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_fluxo_financeiro",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_painel_equilibrio",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_dependencia_eap",
                return_value=None,
            ),
        ):
            result = build_all({})
        assert result == {}

    def test_build_all_returns_non_none_pngs(self):
        from concilium.application.runtime.deliverables.visualizations.charts import build_all

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_equipamentos",
                return_value=b"png1",
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_mao_obra",
                return_value=None,
            ),
            patch("concilium.application.runtime.deliverables.visualizations.charts.build_gantt", return_value=b"png2"),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_fluxo_financeiro",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_painel_equilibrio",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_dependencia_eap",
                return_value=None,
            ),
        ):
            result = build_all({"cronograma": {}})
        assert "hist_equipamentos.png" in result
        assert "gantt_cronograma.png" in result
        assert "hist_mao_obra.png" not in result

    def test_build_all_swallows_exceptions(self):
        from concilium.application.runtime.deliverables.visualizations.charts import build_all

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_equipamentos",
                side_effect=Exception("fail"),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_hist_mao_obra",
                return_value=None,
            ),
            patch("concilium.application.runtime.deliverables.visualizations.charts.build_gantt", return_value=None),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_fluxo_financeiro",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_painel_equilibrio",
                return_value=None,
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.build_dependencia_eap",
                return_value=None,
            ),
        ):
            result = build_all({})  # should not raise
        assert "hist_equipamentos.png" not in result



