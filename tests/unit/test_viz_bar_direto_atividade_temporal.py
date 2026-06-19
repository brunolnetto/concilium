"""Tests for bar_direto_atividade_temporal visualization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _build(canonical, cubo):
    from concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal import build

    return build(canonical, cubo)


class TestBucketFromWeekIso:
    def test_converts_iso_week_to_month_bucket(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal import (
            _bucket_from_week_iso,
        )

        result = _bucket_from_week_iso("2026-W01")
        assert result.startswith("2025") or result.startswith("2026")
        assert len(result) == 7  # YYYY-MM

    def test_converts_mid_year_week(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal import (
            _bucket_from_week_iso,
        )

        result = _bucket_from_week_iso("2026-W26")
        assert "-" in result


class TestBuildEarlyReturns:
    def test_returns_none_when_matplotlib_unavailable(self):
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal.init_mpl",
            side_effect=ImportError,
        ):
            assert _build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_no_periodos(self):
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal.init_mpl",
                return_value=(mock_plt, MagicMock()),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal._iter_scaled_cubo_cells",
                return_value=[],
            ),
        ):
            assert _build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_no_top_atividades(self):
        # cells have no custo_direto component
        mock_cell = MagicMock()
        mock_cell.componente_bdi = "other"
        mock_cell.atividade_id = "act-1"
        mock_cell.semana_iso = "2026-W01"
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (MagicMock(), MagicMock())
        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal.init_mpl",
                return_value=(mock_plt, MagicMock()),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal._iter_scaled_cubo_cells",
                return_value=[(mock_cell, 100.0)],
            ),
        ):
            assert _build(MagicMock(), MagicMock()) is None


class TestBuildHappyPath:
    def _make_cell(self, componente, atividade_id, semana_iso, valor):
        cell = MagicMock()
        cell.componente_bdi = componente
        cell.atividade_id = atividade_id
        cell.semana_iso = semana_iso
        return cell, valor

    def test_returns_bytes_with_valid_custo_direto_cells(self):
        cells = [
            self._make_cell("custo_direto", "act-1", "2026-W10", 1_000_000),
            self._make_cell("custo_direto", "act-2", "2026-W10", 500_000),
            self._make_cell("custo_direto", "act-1", "2026-W11", 800_000),
        ]
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        def fake_fig_to_bytes(fig):
            return b"BAR_TEMPORAL_BYTES"

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal.init_mpl",
                return_value=(mock_plt, fake_fig_to_bytes),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal._iter_scaled_cubo_cells",
                return_value=cells,
            ),
        ):
            result = _build(MagicMock(), MagicMock())
        assert result == b"BAR_TEMPORAL_BYTES"

    def test_handles_exception_in_plot(self):
        cells = [self._make_cell("custo_direto", "act-1", "2026-W10", 100_000)]
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("plot error")
        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal.init_mpl",
                return_value=(mock_plt, MagicMock()),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_direto_atividade_temporal._iter_scaled_cubo_cells",
                return_value=cells,
            ),
        ):
            assert _build(MagicMock(), MagicMock()) is None
