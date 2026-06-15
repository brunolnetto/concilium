"""Tests for pool_custo_estado visualization."""
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest

_RESOLVE = "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection"
_INIT_MPL = "concilium.application.runtime.deliverables.visualizations.cube.pool_custo_estado.init_mpl"


def _build(*args, **kwargs):
    from concilium.application.runtime.deliverables.visualizations.cube.pool_custo_estado import build
    return build(*args, **kwargs)


class TestBuildEarlyReturns:
    def test_returns_none_when_resolve_raises(self):
        canonical = MagicMock()
        with patch(_RESOLVE, side_effect=Exception("fail")):
            assert _build(canonical) is None

    def test_returns_none_when_rows_empty(self):
        canonical = MagicMock()
        with patch(_RESOLVE, return_value={"rows": []}):
            assert _build(canonical) is None

    def test_returns_none_when_matplotlib_unavailable(self):
        canonical = MagicMock()
        rows = [{"estado": "Produtivo", "componente": "mo", "valor_rs": 100}]
        with patch(_RESOLVE, return_value={"rows": rows}), \
             patch(_INIT_MPL, side_effect=ImportError):
            assert _build(canonical) is None

    def test_returns_none_when_no_valid_estados(self):
        canonical = MagicMock()
        # All valores are 0 → estados sum to 0 → filtered out
        rows = [{"estado": "Produtivo", "componente": "mo", "valor_rs": 0}]
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with patch(_RESOLVE, return_value={"rows": rows}), \
             patch(_INIT_MPL, return_value=(mock_plt, MagicMock())):
            assert _build(canonical) is None


class TestBuildHappyPath:
    def test_returns_bytes_with_valid_data(self):
        canonical = MagicMock()
        rows = [
            {"estado": "Produtivo", "componente": "mo", "valor_rs": 50_000},
            {"estado": "Produtivo", "componente": "eq", "valor_rs": 30_000},
            {"estado": "Ocioso", "componente": "mo", "valor_rs": 20_000},
        ]
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.cm.tab10 = MagicMock()

        def fake_fig_to_bytes(fig):
            return b"PNG_BYTES"

        with patch(_RESOLVE, return_value={"rows": rows}), \
             patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)
        assert result == b"PNG_BYTES"

    def test_handles_exception_in_plot_body(self):
        canonical = MagicMock()
        rows = [{"estado": "Produtivo", "componente": "mo", "valor_rs": 50_000}]
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("plotting error")
        with patch(_RESOLVE, return_value={"rows": rows}), \
             patch(_INIT_MPL, return_value=(mock_plt, MagicMock())):
            assert _build(canonical) is None
