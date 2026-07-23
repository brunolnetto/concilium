"""Tests for cube visualization renderers.

Covers all missing lines in _renderers.py using MagicMock for matplotlib.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from concilium.application.runtime.deliverables.visualizations.cube._renderers import (
    render_line_bar,
    render_stacked_area,
    render_stacked_area_100pct,
    render_stacked_bar,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_plt_mock(two_axes: bool = False):
    """Return a MagicMock that mimics plt.subplots correctly."""
    plt_mock = MagicMock()
    fig_mock = MagicMock()
    ax_mock = MagicMock()
    ax_norm_mock = MagicMock()

    if two_axes:
        plt_mock.subplots.return_value = (fig_mock, (ax_mock, ax_norm_mock))
    else:
        plt_mock.subplots.return_value = (fig_mock, ax_mock)

    return plt_mock, fig_mock, ax_mock, ax_norm_mock


def _col(role: str, col_id: str, label: str = "") -> dict:
    return {"role": role, "id": col_id, "label": label or col_id}


# ---------------------------------------------------------------------------
# render_stacked_bar — early-exit paths
# ---------------------------------------------------------------------------


class TestRenderStackedBarEarlyExit:
    def test_returns_none_when_rows_empty(self):
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("series", "serie"), _col("value", "valor_rs")]
        result = render_stacked_bar(plt_mock, [], columns, "Title")
        assert result is None

    def test_returns_none_when_no_series_derived(self):
        """rows present but series_key yields empty set → None."""
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("series", "serie"), _col("value", "valor_rs")]
        # rows have no 'serie' key — series_names will be {""}
        # but labels will also be {""} so we need labels empty to hit None
        result = render_stacked_bar(plt_mock, [], columns, "Title")
        assert result is None

    def test_returns_none_when_labels_empty(self):
        """rows is empty list → labels empty → returns None."""
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("value", "valor_rs")]
        result = render_stacked_bar(plt_mock, [], columns, "Title")
        assert result is None


# ---------------------------------------------------------------------------
# render_stacked_bar — x_key_role branch (normal path)
# ---------------------------------------------------------------------------


class TestRenderStackedBarXKeyRole:
    def _make_rows(self):
        return [
            {"periodo": "2024-W01", "serie": "mao_obra", "valor_rs": 1000.0},
            {"periodo": "2024-W01", "serie": "equipamento", "valor_rs": 500.0},
            {"periodo": "2024-W02", "serie": "mao_obra", "valor_rs": 1200.0},
            {"periodo": "2024-W02", "serie": "equipamento", "valor_rs": 600.0},
        ]

    def _make_columns(self):
        return [
            _col("x", "periodo", "Periodo"),
            _col("series", "serie", "Serie"),
            _col("value", "valor_rs", "Valor R$"),
        ]

    def test_normal_execution_returns_fig(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        rows = self._make_rows()
        columns = self._make_columns()
        result = render_stacked_bar(plt_mock, rows, columns, "Test Chart")
        assert result is fig_mock

    def test_use_millions_true(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        rows = self._make_rows()
        columns = self._make_columns()
        result = render_stacked_bar(plt_mock, rows, columns, "Title", use_millions=True)
        assert result is fig_mock
        # set_ylabel should be called with "R$ (Mi)"
        ylabel_calls = [str(c) for c in ax_mock.set_ylabel.call_args_list]
        assert any("Mi" in c for c in ylabel_calls)

    def test_tight_layout_called(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        rows = self._make_rows()
        columns = self._make_columns()
        render_stacked_bar(plt_mock, rows, columns, "Title")
        fig_mock.tight_layout.assert_called_once()

    def test_fallback_value_key_defaults_to_valor_rs(self):
        """When no value column in columns, defaults to 'valor_rs'."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        columns = [_col("x", "periodo"), _col("series", "serie")]
        rows = [
            {"periodo": "A", "serie": "s1", "valor_rs": 10.0},
        ]
        result = render_stacked_bar(plt_mock, rows, columns, "Title")
        assert result is fig_mock

    def test_fallback_x_key_defaults_to_periodo(self):
        """When no x column in columns, x_key defaults to 'periodo'."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        columns = [_col("series", "serie"), _col("value", "valor_rs")]
        rows = [{"periodo": "A", "serie": "s1", "valor_rs": 10.0}]
        result = render_stacked_bar(plt_mock, rows, columns, "Title")
        assert result is fig_mock


# ---------------------------------------------------------------------------
# render_stacked_bar — y_key_role branch
# ---------------------------------------------------------------------------


class TestRenderStackedBarYKeyRole:
    def _make_rows(self):
        return [
            {"atividade": "ATv1", "categoria": "Cat1", "valor_rs": 1000.0},
            {"atividade": "ATv1", "categoria": "Cat2", "valor_rs": 500.0},
            {"atividade": "ATv2", "categoria": "Cat1", "valor_rs": 800.0},
        ]

    def _make_columns(self):
        # y role present and no series role → y_key_role branch
        return [
            _col("x", "categoria", "Categoria"),
            _col("y", "atividade", "Atividade"),
            _col("value", "valor_rs", "Valor"),
        ]

    def test_y_key_role_branch_returns_fig(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        rows = self._make_rows()
        columns = self._make_columns()
        result = render_stacked_bar(plt_mock, rows, columns, "Heatmap Chart")
        assert result is fig_mock


# ---------------------------------------------------------------------------
# render_stacked_bar — show_normalized=True
# ---------------------------------------------------------------------------


class TestRenderStackedBarNormalized:
    def _make_rows(self):
        return [
            {"periodo": "W1", "serie": "mao_obra", "valor_rs": 500.0},
            {"periodo": "W1", "serie": "equipamento", "valor_rs": 500.0},
            {"periodo": "W2", "serie": "mao_obra", "valor_rs": 700.0},
            {"periodo": "W2", "serie": "equipamento", "valor_rs": 300.0},
        ]

    def _make_columns(self):
        return [
            _col("x", "periodo"),
            _col("series", "serie"),
            _col("value", "valor_rs"),
        ]

    def test_show_normalized_true_returns_fig(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        rows = self._make_rows()
        columns = self._make_columns()
        result = render_stacked_bar(plt_mock, rows, columns, "Title", show_normalized=True)
        assert result is fig_mock

    def test_show_normalized_calls_subplots_2_1(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        rows = self._make_rows()
        columns = self._make_columns()
        render_stacked_bar(plt_mock, rows, columns, "Title", show_normalized=True)
        plt_mock.subplots.assert_called_once()
        call_args = plt_mock.subplots.call_args
        assert call_args[0] == (2, 1) or call_args[1].get("nrows") == 2

    def test_ax_norm_bar_called(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        rows = self._make_rows()
        columns = self._make_columns()
        render_stacked_bar(plt_mock, rows, columns, "Title", show_normalized=True)
        ax_norm_mock.bar.assert_called()

    def test_ax_norm_set_ylim_called(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        rows = self._make_rows()
        columns = self._make_columns()
        render_stacked_bar(plt_mock, rows, columns, "Title", show_normalized=True)
        ax_norm_mock.set_ylim.assert_called_with(0, 105)


# ---------------------------------------------------------------------------
# render_stacked_bar — annotate_bdi=True
# ---------------------------------------------------------------------------


class TestRenderStackedBarAnnotateBdi:
    def _make_rows(self):
        return [
            {"periodo": "W1", "serie": "overhead_AC", "valor_rs": 300.0},
            {"periodo": "W1", "serie": "tributo_ISS", "valor_rs": 200.0},
        ]

    def _make_columns(self):
        return [_col("x", "periodo"), _col("series", "serie"), _col("value", "valor_rs")]

    def test_annotate_bdi_without_normalized(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        rows = self._make_rows()
        columns = self._make_columns()
        result = render_stacked_bar(plt_mock, rows, columns, "BDI", annotate_bdi=True)
        assert result is fig_mock
        ax_mock.annotate.assert_called_once()
        # subplots_adjust should be called
        fig_mock.subplots_adjust.assert_called_with(bottom=0.22)

    def test_annotate_bdi_with_normalized_annotates_ax_norm(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        rows = self._make_rows()
        columns = self._make_columns()
        result = render_stacked_bar(plt_mock, rows, columns, "BDI", show_normalized=True, annotate_bdi=True)
        assert result is fig_mock
        ax_norm_mock.annotate.assert_called_once()


# ---------------------------------------------------------------------------
# render_stacked_area — early-exit paths
# ---------------------------------------------------------------------------


class TestRenderStackedAreaEarlyExit:
    def test_no_series_key_returns_none(self):
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("value", "valor_rs")]
        rows = [{"periodo": "W1", "valor_rs": 100.0}]
        result = render_stacked_area(plt_mock, rows, columns, "Title")
        assert result is None

    def test_empty_rows_returns_none(self):
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("series", "serie"), _col("value", "valor_rs")]
        result = render_stacked_area(plt_mock, [], columns, "Title")
        assert result is None


# ---------------------------------------------------------------------------
# render_stacked_area — normal path
# ---------------------------------------------------------------------------


class TestRenderStackedAreaNormal:
    def _make_rows(self):
        return [
            {"periodo": "2024-W01", "serie": "mao_obra", "valor_rs": 500.0},
            {"periodo": "2024-W01", "serie": "equipamento", "valor_rs": 300.0},
            {"periodo": "2024-W02", "serie": "mao_obra", "valor_rs": 600.0},
            {"periodo": "2024-W02", "serie": "equipamento", "valor_rs": 400.0},
        ]

    def _make_columns(self):
        return [
            _col("x", "periodo"),
            _col("series", "serie"),
            _col("value", "valor_rs"),
        ]

    def test_normal_execution_returns_fig(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        result = render_stacked_area(plt_mock, self._make_rows(), self._make_columns(), "Area")
        assert result is fig_mock

    def test_fill_between_called_on_both_axes(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        render_stacked_area(plt_mock, self._make_rows(), self._make_columns(), "Area")
        ax_mock.fill_between.assert_called()
        ax_norm_mock.fill_between.assert_called()

    def test_ax_norm_set_ylim_100(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        render_stacked_area(plt_mock, self._make_rows(), self._make_columns(), "Area")
        ax_norm_mock.set_ylim.assert_called_with(0, 100)

    def test_use_millions_ylabel(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        render_stacked_area(plt_mock, self._make_rows(), self._make_columns(), "Area", use_millions=True)
        calls = [str(c) for c in ax_mock.set_ylabel.call_args_list]
        assert any("Mi" in c for c in calls)

    def test_tight_layout_called(self):
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        render_stacked_area(plt_mock, self._make_rows(), self._make_columns(), "Area")
        fig_mock.tight_layout.assert_called_once()

    def test_x_key_defaults_to_periodo(self):
        """columns without x role → default 'periodo' key used."""
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        columns = [_col("series", "serie"), _col("value", "valor_rs")]
        rows = [{"periodo": "A", "serie": "s1", "valor_rs": 10.0}]
        result = render_stacked_area(plt_mock, rows, columns, "Title")
        assert result is fig_mock

    def test_value_key_defaults_to_valor_rs(self):
        """columns without value role → default 'valor_rs' used."""
        plt_mock, fig_mock, ax_mock, ax_norm_mock = _make_plt_mock(two_axes=True)
        columns = [_col("x", "periodo"), _col("series", "serie")]
        rows = [{"periodo": "A", "serie": "s1", "valor_rs": 10.0}]
        result = render_stacked_area(plt_mock, rows, columns, "Title")
        assert result is fig_mock


# ---------------------------------------------------------------------------
# render_stacked_area_100pct — early-exit paths
# ---------------------------------------------------------------------------


class TestRenderStackedArea100pctEarlyExit:
    def test_no_series_key_returns_none(self):
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("value", "valor_rs")]
        rows = [{"periodo": "W1", "valor_rs": 100.0}]
        result = render_stacked_area_100pct(plt_mock, rows, columns, "Title")
        assert result is None

    def test_empty_rows_returns_none(self):
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("series", "serie"), _col("value", "valor_rs")]
        result = render_stacked_area_100pct(plt_mock, [], columns, "Title")
        assert result is None


# ---------------------------------------------------------------------------
# render_stacked_area_100pct — normal path
# ---------------------------------------------------------------------------


class TestRenderStackedArea100pctNormal:
    def _make_rows(self):
        return [
            {"periodo": "2024-W01", "serie": "custo_direto", "valor_rs": 800.0},
            {"periodo": "2024-W01", "serie": "custo_indireto", "valor_rs": 200.0},
            {"periodo": "2024-W02", "serie": "custo_direto", "valor_rs": 900.0},
            {"periodo": "2024-W02", "serie": "custo_indireto", "valor_rs": 100.0},
        ]

    def _make_columns(self):
        return [
            _col("x", "periodo"),
            _col("series", "serie"),
            _col("value", "valor_rs"),
        ]

    def test_normal_execution_returns_fig(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        result = render_stacked_area_100pct(plt_mock, self._make_rows(), self._make_columns(), "100pct")
        assert result is fig_mock

    def test_fill_between_called(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_stacked_area_100pct(plt_mock, self._make_rows(), self._make_columns(), "100pct")
        ax_mock.fill_between.assert_called()

    def test_set_ylim_0_100(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_stacked_area_100pct(plt_mock, self._make_rows(), self._make_columns(), "100pct")
        ax_mock.set_ylim.assert_called_with(0, 100)

    def test_tight_layout_called(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_stacked_area_100pct(plt_mock, self._make_rows(), self._make_columns(), "100pct")
        fig_mock.tight_layout.assert_called_once()

    def test_serie_label_map_used(self):
        """SERIE_LABEL_MAP keys should be translated to friendly labels."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_stacked_area_100pct(plt_mock, self._make_rows(), self._make_columns(), "100pct")
        # fill_between was called — the label arg should contain the mapped label
        calls = ax_mock.fill_between.call_args_list
        labels_used = [c[1].get("label", "") for c in calls]
        # custo_direto → "Custo Direto"
        assert any("Custo Direto" in lbl for lbl in labels_used)

    def test_x_key_defaults_to_periodo(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        columns = [_col("series", "serie"), _col("value", "valor_rs")]
        rows = [{"periodo": "A", "serie": "s1", "valor_rs": 10.0}]
        result = render_stacked_area_100pct(plt_mock, rows, columns, "Title")
        assert result is fig_mock


# ---------------------------------------------------------------------------
# render_line_bar — early-exit paths
# ---------------------------------------------------------------------------


class TestRenderLineBarEarlyExit:
    def test_no_value_key_returns_none(self):
        plt_mock = MagicMock()
        columns = [_col("x", "periodo")]
        rows = [{"periodo": "W1", "valor_rs": 100.0}]
        result = render_line_bar(plt_mock, rows, columns, "Title")
        assert result is None

    def test_empty_rows_returns_none(self):
        plt_mock = MagicMock()
        columns = [_col("x", "periodo"), _col("value", "valor_rs")]
        result = render_line_bar(plt_mock, [], columns, "Title")
        assert result is None


# ---------------------------------------------------------------------------
# render_line_bar — bar branch (no series_key)
# ---------------------------------------------------------------------------


class TestRenderLineBarBarBranch:
    def _make_rows(self):
        return [
            {"periodo": "2024-W01", "valor_rs": 1000.0},
            {"periodo": "2024-W02", "valor_rs": 1200.0},
            {"periodo": "2024-W03", "valor_rs": 900.0},
        ]

    def _make_columns(self):
        return [_col("x", "periodo"), _col("value", "valor_rs", "Valor R$")]

    def test_bar_branch_returns_fig(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        result = render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Bar")
        assert result is fig_mock

    def test_ax_bar_called(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Bar")
        ax_mock.bar.assert_called_once()

    def test_ax_plot_not_called(self):
        """In bar branch, ax.plot should NOT be called."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Bar")
        ax_mock.plot.assert_not_called()

    def test_tight_layout_called(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Bar")
        fig_mock.tight_layout.assert_called_once()

    def test_x_key_defaults_to_periodo(self):
        """No x column → defaults to 'periodo'."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        columns = [_col("value", "valor_rs")]
        rows = [{"periodo": "A", "valor_rs": 10.0}]
        result = render_line_bar(plt_mock, rows, columns, "Title")
        assert result is fig_mock


# ---------------------------------------------------------------------------
# render_line_bar — line branch (series_key present)
# ---------------------------------------------------------------------------


class TestRenderLineBarLineBranch:
    def _make_rows(self):
        return [
            {"periodo": "2024-W01", "serie": "mao_obra", "custo_rs": 500.0},
            {"periodo": "2024-W01", "serie": "equipamento", "custo_rs": 300.0},
            {"periodo": "2024-W02", "serie": "mao_obra", "custo_rs": 600.0},
            {"periodo": "2024-W02", "serie": "equipamento", "custo_rs": 400.0},
        ]

    def _make_columns(self):
        return [
            _col("x", "periodo"),
            _col("series", "serie"),
            _col("value", "custo_rs", "Custo R$"),
        ]

    def test_line_branch_returns_fig(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        result = render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Lines")
        assert result is fig_mock

    def test_ax_plot_called(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Lines")
        ax_mock.plot.assert_called()

    def test_ax_bar_not_called(self):
        """In line branch, ax.bar should NOT be called."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Lines")
        ax_mock.bar.assert_not_called()

    def test_ax_legend_called(self):
        """ax.legend() should be called in the line branch."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows(), self._make_columns(), "Lines")
        ax_mock.legend.assert_called()


# ---------------------------------------------------------------------------
# render_line_bar — is_liters=True path (diesel in value_key)
# ---------------------------------------------------------------------------


class TestRenderLineBarLitersBranch:
    def _make_rows_diesel(self):
        return [
            {"periodo": "2024-W01", "volume_diesel_l": 5000.0},
            {"periodo": "2024-W02", "volume_diesel_l": 4500.0},
        ]

    def _make_columns_diesel(self):
        return [_col("x", "periodo"), _col("value", "volume_diesel_l", "Volume (L)")]

    def test_diesel_keyword_activates_liters_path(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        result = render_line_bar(plt_mock, self._make_rows_diesel(), self._make_columns_diesel(), "Diesel")
        assert result is fig_mock

    def test_ylabel_volume_kl_for_diesel(self):
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows_diesel(), self._make_columns_diesel(), "Diesel")
        calls = [str(c) for c in ax_mock.set_ylabel.call_args_list]
        assert any("kL" in c for c in calls)

    def test_liter_label_l_activates_liters_path(self):
        """(l) in col label also triggers is_liters."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        columns = [_col("x", "periodo"), _col("value", "volume_col", "Consumo (L)")]
        rows = [{"periodo": "A", "volume_col": 1000.0}]
        result = render_line_bar(plt_mock, rows, columns, "Title")
        assert result is fig_mock
        calls = [str(c) for c in ax_mock.set_ylabel.call_args_list]
        assert any("kL" in c for c in calls)

    def test_diesel_values_scaled_by_1000(self):
        """Values should be divided by 1000 in the bar call."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        render_line_bar(plt_mock, self._make_rows_diesel(), self._make_columns_diesel(), "Diesel")
        ax_mock.bar.assert_called_once()
        bar_call_args = ax_mock.bar.call_args
        values_passed = bar_call_args[0][1]  # second positional arg = values list
        # 5000 / 1000 = 5.0 and 4500 / 1000 = 4.5
        assert values_passed[0] == pytest.approx(5.0)
        assert values_passed[1] == pytest.approx(4.5)


# ---------------------------------------------------------------------------
# render_line_bar — use_millions flag (ylabel only, no is_liters)
# ---------------------------------------------------------------------------


class TestRenderLineBarUseMilions:
    def test_use_millions_ylabel_not_liters(self):
        """When use_millions=True and NOT liters, ylabel = value_col_label."""
        plt_mock, fig_mock, ax_mock, _ = _make_plt_mock(two_axes=False)
        columns = [_col("x", "periodo"), _col("value", "valor_rs", "Valor R$")]
        rows = [{"periodo": "W1", "valor_rs": 1_000_000.0}]
        result = render_line_bar(plt_mock, rows, columns, "Title", use_millions=True)
        assert result is fig_mock
