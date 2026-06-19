"""Tests for pool_economia visualization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

_RESOLVE = "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection"
_INIT_MPL = "concilium.application.runtime.deliverables.visualizations.cube.pool_economia.init_mpl"


def _build(*args, **kwargs):
    from concilium.application.runtime.deliverables.visualizations.cube.pool_economia import build

    return build(*args, **kwargs)


def _make_axes():
    """Return (mock_fig, (ax_bars, ax_eco)) matching plt.subplots unpacking on line 52."""
    mock_fig = MagicMock()
    ax_bars = MagicMock()
    ax_eco = MagicMock()
    return mock_fig, (ax_bars, ax_eco)


def _make_rows_positive():
    """3 rows all with positive economia."""
    return [
        {"atividade_id": "ACT-001", "custo_autonomo": 500_000.0, "custo_instancial": 400_000.0, "economia": 100_000.0},
        {"atividade_id": "ACT-002", "custo_autonomo": 300_000.0, "custo_instancial": 250_000.0, "economia": 50_000.0},
        {"atividade_id": "ACT-003", "custo_autonomo": 200_000.0, "custo_instancial": 180_000.0, "economia": 20_000.0},
    ]


def _make_rows_mixed():
    """5 rows with mixed positive and negative economia to cover color branching."""
    return [
        {"atividade_id": "ACT-001", "custo_autonomo": 500_000.0, "custo_instancial": 400_000.0, "economia": 100_000.0},
        {"atividade_id": "ACT-002", "custo_autonomo": 300_000.0, "custo_instancial": 350_000.0, "economia": -50_000.0},
        {"atividade_id": "ACT-003", "custo_autonomo": 200_000.0, "custo_instancial": 180_000.0, "economia": 20_000.0},
        {"atividade_id": "ACT-004", "custo_autonomo": 150_000.0, "custo_instancial": 200_000.0, "economia": -50_000.0},
        {"atividade_id": "ACT-005", "custo_autonomo": 100_000.0, "custo_instancial": 90_000.0, "economia": 10_000.0},
    ]


class TestBuildEarlyReturns:
    def test_returns_none_when_resolve_raises(self):
        canonical = MagicMock()
        with patch(_RESOLVE, side_effect=Exception("fail")):
            assert _build(canonical) is None

    def test_returns_none_when_rows_empty(self):
        canonical = MagicMock()
        with patch(_RESOLVE, return_value={"rows": []}):
            assert _build(canonical) is None

    def test_returns_none_when_rows_none(self):
        canonical = MagicMock()
        with patch(_RESOLVE, return_value={}):
            assert _build(canonical) is None

    def test_returns_none_when_all_custo_autonomo_zero(self):
        """Filtering by custo_autonomo > 0 empties the list — must return None."""
        canonical = MagicMock()
        rows = [
            {"atividade_id": "ACT-001", "custo_autonomo": 0.0, "custo_instancial": 100.0, "economia": 0.0},
            {"atividade_id": "ACT-002", "custo_autonomo": None, "custo_instancial": 100.0, "economia": 0.0},
        ]
        with patch(_RESOLVE, return_value={"rows": rows}):
            assert _build(canonical) is None

    def test_returns_none_when_matplotlib_unavailable(self):
        canonical = MagicMock()
        rows = _make_rows_positive()
        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, side_effect=ImportError("no matplotlib")):
            assert _build(canonical) is None

    def test_returns_none_when_exception_inside_plot_body(self):
        canonical = MagicMock()
        rows = _make_rows_positive()
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("plotting exploded")
        with patch(_RESOLVE, return_value={"rows": rows}), patch(_INIT_MPL, return_value=(mock_plt, MagicMock())):
            assert _build(canonical) is None


class TestBuildHappyPath:
    def test_returns_bytes_with_positive_economia(self):
        """All economia values positive — covers _COLOR_POS path."""
        canonical = MagicMock()
        rows = _make_rows_positive()
        proj = {
            "rows": rows,
            "operator_meta": {
                "custo_autonomo_total": 1_000_000.0,
                "custo_instancial_total": 830_000.0,
                "economia_total": 170_000.0,
            },
        }

        mock_fig, axes_tuple = _make_axes()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, axes_tuple)

        def fake_fig_to_bytes(fig):
            return b"PNG_BYTES"

        with patch(_RESOLVE, return_value=proj), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)

        assert result == b"PNG_BYTES"

    def test_returns_bytes_with_mixed_economia_signs(self):
        """Mix of positive and negative economia — covers _COLOR_POS and _COLOR_NEG paths."""
        canonical = MagicMock()
        rows = _make_rows_mixed()
        proj = {
            "rows": rows,
            "operator_meta": {
                "custo_autonomo_total": 1_250_000.0,
                "custo_instancial_total": 1_220_000.0,
                "economia_total": 30_000.0,
            },
        }

        mock_fig, axes_tuple = _make_axes()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, axes_tuple)

        def fake_fig_to_bytes(fig):
            return b"PNG_BYTES_MIXED"

        with patch(_RESOLVE, return_value=proj), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)

        assert result == b"PNG_BYTES_MIXED"

    def test_operator_meta_missing_keys_does_not_raise(self):
        """operator_meta absent — defaults to 0.0 for totals."""
        canonical = MagicMock()
        rows = _make_rows_positive()
        proj = {"rows": rows}  # no operator_meta key

        mock_fig, axes_tuple = _make_axes()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, axes_tuple)

        def fake_fig_to_bytes(fig):
            return b"PNG_NO_META"

        with patch(_RESOLVE, return_value=proj), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical)

        assert result == b"PNG_NO_META"

    def test_cubo_kwarg_is_forwarded(self):
        """Passing cubo= does not crash; canonical and cubo are both accepted."""
        canonical = MagicMock()
        cubo = MagicMock()
        rows = _make_rows_positive()
        proj = {"rows": rows}

        mock_fig, axes_tuple = _make_axes()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, axes_tuple)

        def fake_fig_to_bytes(fig):
            return b"PNG_CUBO"

        with patch(_RESOLVE, return_value=proj), patch(_INIT_MPL, return_value=(mock_plt, fake_fig_to_bytes)):
            result = _build(canonical, cubo=cubo)

        assert result == b"PNG_CUBO"
