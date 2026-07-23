"""ADR-124 / NEP-036 — Waterfall causal: η_clima / δ / η_plan (planejamento)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _plot(campo, **kwargs):
    from concilium.application.runtime.deliverables.visualizations.eficiencia.waterfall_causal import (
        plot_waterfall_causal,
    )

    return plot_waterfall_causal(campo, **kwargs)


def _make_campo(decomposicao=None):
    campo = MagicMock()
    campo.decomposicao_causal.return_value = decomposicao or {
        "eta_clima_global": 0.88,
        "delta_global": 0.95,
        "eta_plan_global": 0.836,
    }
    return campo


def _mock_ax_and_fig(n_bars: int = 3):
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_bars = [MagicMock() for _ in range(n_bars)]
    for bar in mock_bars:
        bar.get_x.return_value = 0.0
        bar.get_width.return_value = 1.0
        bar.get_height.return_value = 0.9
    mock_ax.bar.return_value = mock_bars
    return mock_fig, mock_ax


class TestPlotWaterfallCausal:
    def test_decomposicao_causal_is_called(self):
        campo = _make_campo()
        mock_fig, mock_ax = _mock_ax_and_fig()
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            _plot(campo)
        campo.decomposicao_causal.assert_called_once()

    def test_returns_figure(self):
        campo = _make_campo()
        mock_fig, mock_ax = _mock_ax_and_fig()
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            result = _plot(campo)
        assert result is mock_fig

    def test_accepts_custom_title(self):
        campo = _make_campo()
        mock_fig, mock_ax = _mock_ax_and_fig()
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            result = _plot(campo, title="Waterfall Teste")
        mock_ax.set_title.assert_called_with("Waterfall Teste")
        assert result is mock_fig

    def test_tres_barras_planejamento(self):
        """Waterfall de planejamento tem exatamente 3 barras: η_clima, δ, η_plan."""
        campo = _make_campo()
        mock_fig, mock_ax = _mock_ax_and_fig()
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            _plot(campo)
        call_args = mock_ax.bar.call_args
        labels = call_args[0][0]
        assert len(labels) == 3
        assert any("clima" in lbl.lower() for lbl in labels)
        assert any("calend" in lbl.lower() or "δ" in lbl for lbl in labels)



import sys  # noqa: E402

# waterfall_causal.py lines 30-31: matplotlib ImportError → return None
# ---------------------------------------------------------------------------


class TestWaterfallCausalMatplotlibImportError:
    def test_importerror_returns_none(self):
        """Lines 30-31: matplotlib not available → return None."""
        from concilium.application.runtime.deliverables.visualizations.eficiencia.waterfall_causal import (
            plot_waterfall_causal,
        )

        campo = MagicMock()
        with patch.dict(sys.modules, {"matplotlib.pyplot": None}):
            result = plot_waterfall_causal(campo)
        assert result is None


# ---------------------------------------------------------------------------

