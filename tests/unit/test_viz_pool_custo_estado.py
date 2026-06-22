"""Tests for pool_custo_estado visualization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, side_effect=ImportError):
            assert _build(canonical) is None

    def test_returns_none_when_no_valid_estados(self):
        canonical = MagicMock()
        # All valores are 0 → estados sum to 0 → filtered out
        rows = [{"estado": "Produtivo", "componente": "mo", "valor_rs": 0}]
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, return_value=(mock_plt, MagicMock())):
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

        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)
        assert result == b"PNG_BYTES"

    def test_handles_exception_in_plot_body(self):
        canonical = MagicMock()
        rows = [{"estado": "Produtivo", "componente": "mo", "valor_rs": 50_000}]
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("plotting error")
        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, return_value=(mock_plt, MagicMock())):
            assert _build(canonical) is None

    def test_narrativa_is_rendered_when_present(self):
        """Covers the narrativa branch (line 98-107 of pool_custo_estado.py)."""
        canonical = MagicMock()
        rows = [
            {"estado": "Produtivo", "componente": "mo", "valor_rs": 50_000},
            {"estado": "Produtivo", "componente": "comb", "valor_rs": 10_000},
            {"estado": "Produtivo", "componente": "mat", "valor_rs": 5_000},
        ]
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        proj = {"rows": rows, "narrativa": ["Estado produtivo concentra todos os custos."]}

        def fake_fig_to_bytes(fig):
            return b"PNG_BYTES"

        with patch(_RESOLVE, return_value=proj), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)
        assert result == b"PNG_BYTES"
        mock_fig.text.assert_called()

    def test_zero_combustivel_and_material_annotation(self):
        """Covers the zero-comb/zero-mat annotation branches (lines 110-124)."""
        canonical = MagicMock()
        rows = [
            {"estado": "Produtivo", "componente": "mo", "valor_rs": 50_000},
            {"estado": "Produtivo", "componente": "eq", "valor_rs": 30_000},
            # comb and mat are absent → total_comb=0 and total_mat=0
        ]
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        def fake_fig_to_bytes(fig):
            return b"PNG_BYTES"

        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)
        assert result == b"PNG_BYTES"
        # fig.text should be called at least once for the zero-annotation note
        mock_fig.text.assert_called()

    def test_zero_only_combustivel_annotation(self):
        """Covers partial zero-annotation: only comb is zero, mat is non-zero."""
        canonical = MagicMock()
        rows = [
            {"estado": "Produtivo", "componente": "mo", "valor_rs": 50_000},
            {"estado": "Produtivo", "componente": "mat", "valor_rs": 10_000},
            # comb absent → total_comb=0, total_mat > 0
        ]
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        def fake_fig_to_bytes(fig):
            return b"PNG_BYTES"

        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)
        assert result == b"PNG_BYTES"
