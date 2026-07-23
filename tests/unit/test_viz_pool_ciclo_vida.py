"""Tests for several remaining uncovered modules."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─── pool_ciclo_vida visualization ───────────────────────────────────────────


class TestVizPoolCicloVida:
    _RESOLVE_POOL = "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection"
    _INIT_MPL_CICLO = "concilium.application.runtime.deliverables.visualizations.cube.pool_ciclo_vida.init_mpl"

    def test_build_returns_none_when_no_rows(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_ciclo_vida import build

        canonical = MagicMock()
        with patch(self._RESOLVE_POOL, return_value={"rows": []}):
            assert build(canonical) is None

    def test_build_returns_none_on_exception(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_ciclo_vida import build

        canonical = MagicMock()
        with patch(self._RESOLVE_POOL, side_effect=Exception("fail")):
            assert build(canonical) is None

    def test_build_returns_none_when_matplotlib_missing(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_ciclo_vida import build

        canonical = MagicMock()
        rows = [{"instancia_id": "EQ-1", "estado": "prod", "semana_iso": "2026-W01", "valor_rs": 1000}]
        with (
            patch(self._RESOLVE_POOL, return_value={"rows": rows}),
            patch(self._INIT_MPL_CICLO, side_effect=ImportError),
        ):
            assert build(canonical) is None

    def test_build_happy_path(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_ciclo_vida import build

        canonical = MagicMock()
        rows = [
            {"instancia_id": "EQ-1", "estado": "prod", "semana_iso": "2026-W01", "valor_rs": 1000},
            {"instancia_id": "EQ-1", "estado": "idle", "semana_iso": "2026-W02", "valor_rs": 500},
        ]
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        def fake_to_bytes(fig):
            return b"CICLO_PNG"

        with (
            patch(self._RESOLVE_POOL, return_value={"rows": rows}),
            patch(self._INIT_MPL_CICLO, return_value=(mock_plt, fake_to_bytes)),
        ):
            result = build(canonical)
        assert result == b"CICLO_PNG"






# pool_ciclo_vida.py line 49: _draw_row with idle_w > 0
# ---------------------------------------------------------------------------


class TestPoolCicloVidaDrawRowWithIdle:
    def test_idle_w_gt_zero_draws_idle_bar(self):
        """Line 49: idle_w > 0 → ax.barh called for idle."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_ciclo_vida import _draw_row

        ax = MagicMock()
        row = {"prod_w": 5, "idle_w": 2, "off_w": 1, "custo_total": 500_000}
        _draw_row(ax, 0, row)
        assert ax.barh.call_count == 2


# ---------------------------------------------------------------------------

