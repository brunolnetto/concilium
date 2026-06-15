"""Tests for waterfall_causal eficiencia visualization."""
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest


def _plot(campo, **kwargs):
    from concilium.application.runtime.deliverables.visualizations.eficiencia.waterfall_causal import plot_waterfall_causal
    return plot_waterfall_causal(campo, **kwargs)


def _make_campo(decomposicao=None):
    campo = MagicMock()
    campo.decomposicao_causal.return_value = decomposicao or {
        "eta_s_global": 0.9,
        "eta_p_global": 0.85,
        "eta_w_global": 0.95,
        "eta_global": 0.72,
        "eps_cross": -0.03,
        "acoplamento_material": False,
    }
    return campo


class TestPlotWaterfallCausal:
    def test_decomposicao_causal_is_called(self):
        campo = _make_campo()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bars = [MagicMock() for _ in range(5)]
        for bar in mock_bars:
            bar.get_x.return_value = 0.0
            bar.get_width.return_value = 1.0
            bar.get_height.return_value = 0.9
        mock_ax.bar.return_value = mock_bars
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            _plot(campo)
        campo.decomposicao_causal.assert_called()

    def test_returns_figure_with_default_data(self):
        campo = _make_campo()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bars = [MagicMock() for _ in range(5)]
        for bar in mock_bars:
            bar.get_x.return_value = 0.0
            bar.get_width.return_value = 1.0
            bar.get_height.return_value = 0.9
        mock_ax.bar.return_value = mock_bars
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            result = _plot(campo)
        assert result is mock_fig

    def test_calls_decomposicao_causal(self):
        campo = _make_campo()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bars = [MagicMock() for _ in range(5)]
        for bar in mock_bars:
            bar.get_x.return_value = 0.0
            bar.get_width.return_value = 1.0
            bar.get_height.return_value = 0.9
        mock_ax.bar.return_value = mock_bars
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            _plot(campo)
        campo.decomposicao_causal.assert_called_once()

    def test_accepts_custom_title(self):
        campo = _make_campo()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bars = [MagicMock() for _ in range(5)]
        for bar in mock_bars:
            bar.get_x.return_value = 0.0
            bar.get_width.return_value = 1.0
            bar.get_height.return_value = 0.9
        mock_ax.bar.return_value = mock_bars
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            result = _plot(campo, title="Waterfall Teste")
        mock_ax.set_title.assert_called_with("Waterfall Teste")
        assert result is mock_fig

    def test_eps_cross_positive_uses_grey_color(self):
        campo = _make_campo(decomposicao={
            "eta_s_global": 0.9, "eta_p_global": 0.85, "eta_w_global": 0.95,
            "eta_global": 0.72, "eps_cross": 0.02, "acoplamento_material": False,
        })
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bars = [MagicMock() for _ in range(5)]
        for bar in mock_bars:
            bar.get_x.return_value = 0.0
            bar.get_width.return_value = 1.0
            bar.get_height.return_value = 0.9
        mock_ax.bar.return_value = mock_bars
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            result = _plot(campo)
        # Bar called with colors list — eps positive → grey (#9E9E9E)
        call_kwargs = mock_ax.bar.call_args[1]
        colors = call_kwargs.get("color", [])
        assert "#9E9E9E" in colors

    def test_acoplamento_material_adds_annotation(self):
        campo = _make_campo(decomposicao={
            "eta_s_global": 0.9, "eta_p_global": 0.85, "eta_w_global": 0.95,
            "eta_global": 0.72, "eps_cross": -0.1, "acoplamento_material": True,
        })
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bars = [MagicMock() for _ in range(5)]
        for bar in mock_bars:
            bar.get_x.return_value = 0.0
            bar.get_width.return_value = 1.0
            bar.get_height.return_value = 0.9
        mock_ax.bar.return_value = mock_bars
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            _plot(campo)
        mock_ax.annotate.assert_called_once()
        annotation_text = mock_ax.annotate.call_args[0][0]
        assert "Acoplamento" in annotation_text
