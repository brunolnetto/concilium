"""Tests for linha_recursos_tempo.py — covers missing lines 10-23,26-32,40,42-46,49-56,59-62,71-74,77-82,84-88,90-95."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

MODULE = "concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo"
COMMON = "concilium.application.runtime.deliverables.visualizations.cube._common"


def _make_axes_list(n):
    """Return a list of n MagicMock axes."""
    return [MagicMock() for _ in range(n)]


def _make_mock_plt(n_panels=3):
    mock_plt = MagicMock()
    mock_fig = MagicMock()
    axes = _make_axes_list(n_panels)
    mock_plt.subplots.return_value = (mock_fig, axes)
    return mock_plt, mock_fig, axes


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _rows_factory(n=3, with_mo=False):
    """Build a list of fake cube rows."""
    rows = []
    for i in range(n):
        rows.append(
            {
                "periodo": f"2024-W{i + 1:02d}",
                "equipamentos_unidades_ativas": float(i + 1),
                "n_equipamentos_unicos": float(i),
                "n_equipes_totais": float(i + 2),
            }
        )
    return rows


def _graficos_dict_factory(has_mo=True, with_by_funcao=False):
    if not has_mo:
        return {}
    gd: dict = {
        "mao_obra": {
            "labels": ["2024-W01", "2024-W02", "2024-W03"],
            "values": [5.0, 10.0, 7.0],
        }
    }
    if with_by_funcao:
        gd["mao_obra"]["by_funcao"] = {
            "Operador": [3.0, 6.0, 4.0],
            "Ajudante": [2.0, 4.0, 3.0],
        }
    else:
        gd["mao_obra"]["by_funcao"] = {}
    return gd


# ---------------------------------------------------------------------------
# Test: build_payload raises → returns None (lines 10-13)
# ---------------------------------------------------------------------------


class TestBuildPayloadError:
    def test_build_payload_exception_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        with patch(f"{COMMON}.build_payload", side_effect=RuntimeError("fail")):
            result = build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# Test: empty rows → returns None (lines 14-16)
# ---------------------------------------------------------------------------


class TestEmptyRows:
    def test_empty_rows_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        with patch(f"{COMMON}.build_payload", return_value={"rows": []}):
            result = build(MagicMock(), MagicMock())
        assert result is None

    def test_missing_rows_key_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        with patch(f"{COMMON}.build_payload", return_value={}):
            result = build(MagicMock(), MagicMock())
        assert result is None

    def test_null_rows_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        with patch(f"{COMMON}.build_payload", return_value={"rows": None}):
            result = build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# Test: init_mpl ImportError → returns None (lines 17-20)
# ---------------------------------------------------------------------------


class TestInitMplImportError:
    def test_import_error_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(2)
        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", side_effect=ImportError("no mpl")),
        ):
            result = build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# Test: no MO data (graficos_dict=None) → 2-panel chart (lines 26-46)
# ---------------------------------------------------------------------------


class TestNoMoData:
    def test_build_no_mo_returns_bytes(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=None)

        assert result == b"PNG"

    def test_build_no_mo_graficos_dict_empty(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict={})

        assert result == b"PNG"

    def test_build_no_mo_graficos_dict_no_mao_obra(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict={"other": {}})

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# Test: with MO data and by_funcao → 3-panel chart (lines 42-46, 59-74)
# ---------------------------------------------------------------------------


class TestWithMoData:
    def test_build_with_mo_returns_bytes(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        graficos_dict = _graficos_dict_factory(has_mo=True, with_by_funcao=False)
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=3)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=graficos_dict)

        assert result == b"PNG"

    def test_build_with_mo_and_by_funcao_returns_bytes(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        graficos_dict = _graficos_dict_factory(has_mo=True, with_by_funcao=True)
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=3)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=graficos_dict)

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# Test: mo_data is not a dict (covers isinstance guards, lines 27-31)
# ---------------------------------------------------------------------------


class TestMoDataNotDict:
    def test_mo_data_string_treated_as_no_mo(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        graficos_dict = {"mao_obra": "invalid_string"}
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=graficos_dict)

        assert result == b"PNG"

    def test_mo_data_none_treated_as_no_mo(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        graficos_dict = {"mao_obra": None}
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=graficos_dict)

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# Test: weekly labels → apply_monthly_ticks path (lines 84-87)
# ---------------------------------------------------------------------------


class TestWeeklyLabels:
    def test_weekly_labels_applies_monthly_ticks(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)
        apply_monthly_ticks_mock = MagicMock()

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks", apply_monthly_ticks_mock),
            patch(f"{COMMON}.is_weekly_labels", return_value=True),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=None)

        assert result == b"PNG"
        apply_monthly_ticks_mock.assert_called_once()

    def test_non_weekly_labels_sets_xticks(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=None)

        assert result == b"PNG"
        # ax_team is axes[1] for 2-panel; check set_xticks was called
        axes[1].set_xticks.assert_called()
        axes[1].set_xticklabels.assert_called()


# ---------------------------------------------------------------------------
# Test: exception inside try block → returns None (lines 93-95)
# ---------------------------------------------------------------------------


class TestInnerExceptionHandling:
    def test_exception_in_plotting_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("plotting error")

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=None)

        assert result is None
        mock_plt.close.assert_called()


# ---------------------------------------------------------------------------
# Test: row fields default to 0.0 when absent or None (lines 49-50, 77)
# ---------------------------------------------------------------------------


class TestRowFieldDefaults:
    def test_missing_fields_default_to_zero(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = [{"periodo": "2024-W01"}, {"periodo": "2024-W02"}]
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=None)

        assert result == b"PNG"

    def test_none_field_values_default_to_zero(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = [
            {
                "periodo": "2024-W01",
                "equipamentos_unidades_ativas": None,
                "n_equipamentos_unicos": None,
                "n_equipes_totais": None,
            }
        ]
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=2)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=None)

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# Test: mo_labels and mo_values alignment (line 29-30)
# ---------------------------------------------------------------------------


class TestMoMapAlignment:
    def test_mo_map_period_alignment(self):
        """Periods in rows but not in mo_labels get 0.0; present periods get value."""
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = [
            {
                "periodo": "2024-W01",
                "equipamentos_unidades_ativas": 1.0,
                "n_equipamentos_unicos": 0.0,
                "n_equipes_totais": 1.0,
            },
            {
                "periodo": "2024-W02",
                "equipamentos_unidades_ativas": 2.0,
                "n_equipamentos_unicos": 1.0,
                "n_equipes_totais": 2.0,
            },
            {
                "periodo": "2024-W03",
                "equipamentos_unidades_ativas": 3.0,
                "n_equipamentos_unicos": 2.0,
                "n_equipes_totais": 3.0,
            },
        ]
        # Only W01 and W03 have MO — W02 should default to 0
        graficos_dict = {
            "mao_obra": {
                "labels": ["2024-W01", "2024-W03"],
                "values": [5.0, 8.0],
                "by_funcao": {},
            }
        }
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=3)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=graficos_dict)

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# Test: by_funcao with series shorter than periods (line 34 index guard)
# ---------------------------------------------------------------------------


class TestByFuncaoShortSeries:
    def test_by_funcao_series_shorter_than_periods(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(5)
        graficos_dict = {
            "mao_obra": {
                "labels": [r["periodo"] for r in rows],
                "values": [3.0] * 5,
                "by_funcao": {
                    "Operador": [2.0, 1.0],  # shorter than 5
                },
            }
        }
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=3)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=graficos_dict)

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# Test: funcoes_unicas all-zero → skip plot call (lines 61 branch not taken)
# ---------------------------------------------------------------------------


class TestFuncoesUnicasAllZero:
    def test_by_funcao_all_zero_skips_funcoes_plot(self):
        from concilium.application.runtime.deliverables.visualizations.cube.linha_recursos_tempo import build

        rows = _rows_factory(3)
        graficos_dict = {
            "mao_obra": {
                "labels": [r["periodo"] for r in rows],
                "values": [5.0, 5.0, 5.0],
                "by_funcao": {
                    "Operador": [0.0, 0.0, 0.0],
                },
            }
        }
        mock_plt, mock_fig, axes = _make_mock_plt(n_panels=3)

        with (
            patch(f"{COMMON}.build_payload", return_value={"rows": rows}),
            patch(f"{COMMON}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(f"{COMMON}.apply_monthly_ticks"),
            patch(f"{COMMON}.is_weekly_labels", return_value=False),
        ):
            result = build(MagicMock(), MagicMock(), graficos_dict=graficos_dict)

        assert result == b"PNG"
        # axes[1] is ax_mo — its plot should NOT have been called for funcoes_unicas
        ax_mo = axes[1]
        # bar is called, but plot should not be called (funcoes_unicas all zero)
        ax_mo.bar.assert_called_once()
        # plot SHOULD NOT have been called since funcoes are all zero
        for call_args in ax_mo.plot.call_args_list:
            # If plot was called at all it should not include "Funcoes Unicas" label
            kwargs = call_args[1] if len(call_args) > 1 else {}
            assert kwargs.get("label") != "Funcoes Unicas"
