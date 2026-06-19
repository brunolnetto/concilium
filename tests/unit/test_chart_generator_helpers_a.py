"""Tests for _chart_generator_helpers_a.py — target ≥ 80% coverage.

Strategy:
- _load_json: fully tested using tmp_path (no mocks needed)
- _setup_matplotlib: mock matplotlib.use + plt.rcParams.update
- _compute_times_totaux / _compute_perm_breakdown: inject _TIMES_DATA, use real numpy
- _chart_waterfall: mock plt end-to-end
- _chart_eap_crit: inject _EAP_DATA/_CRIT_COR, mock plt
- _chart_indiretos: inject _INDIR_DATA/_INDIR_COR_DATA, mock plt
- _chart_times: inject _TIMES_DATA, mock plt
- _chart_plan_space: inject _ps_draw_* helpers, mock plt/np
- _times_build_ax0/ax1/ax2: inject _TIMES_DATA, pass MagicMock ax + mticker stub
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_TIMES_DATA = [
    {
        "nome": "ADM",
        "pessoas": 45,
        "custo_mo": 448861,
        "custo_eq": 268331,
        "verbas": 324300,
        "perm": 12.57,
        "sazonal": False,
    },
    {
        "nome": "TOP",
        "pessoas": 5,
        "custo_mo": 64670,
        "custo_eq": 15147,
        "verbas": 3000,
        "perm": 12.57,
        "sazonal": False,
    },
    {
        "nome": "BIOLOGO",
        "pessoas": 1,
        "custo_mo": 7500,
        "custo_eq": 0,
        "verbas": 0,
        "perm": 5.83,
        "sazonal": True,
    },
]

SAMPLE_EAP_DATA = [
    {"nome": "Desmatamento", "crit": "B", "custo": 2529041, "pe_op": 14192824},
    {"nome": "Esc 3aCat 2-3km", "crit": "A", "custo": 13912325, "pe_op": 16188650},
    {"nome": "Compactação PI", "crit": "C", "custo": 393487, "pe_op": 503052},
]

SAMPLE_CRIT_COR = {
    "A": "#DC2626",
    "B": "#EA580C",
    "C": "#6B7280",
}

SAMPLE_INDIR_DATA = {
    "ADM": 13695825,
    "TOP": 858758,
    "MOB": 4054600,
}

SAMPLE_INDIR_COR_DATA = {
    "ADM": "#1B3A6B",
    "TOP": "#0D9488",
    "MOB": "#6B7280",
}


def _import_module():
    import concilium.application.benchmarks.charts._chart_generator_helpers_a as m

    return m


def _inject_times(m):
    """Inject sample _TIMES_DATA into the helpers_a module namespace."""
    m._TIMES_DATA = SAMPLE_TIMES_DATA


def _inject_eap(m):
    m._EAP_DATA = SAMPLE_EAP_DATA
    m._CRIT_COR = SAMPLE_CRIT_COR


def _inject_indir(m):
    m._INDIR_DATA = SAMPLE_INDIR_DATA
    m._INDIR_COR_DATA = SAMPLE_INDIR_COR_DATA


def _make_plt_mock():
    """Build a realistic-enough plt mock for chart functions."""
    plt = MagicMock()
    fig = MagicMock()
    ax = MagicMock()
    # subplots returns (fig, ax) or (fig, axes)
    plt.subplots.return_value = (fig, ax)
    plt.figure.return_value = fig
    fig.add_gridspec.return_value = MagicMock()
    fig.add_subplot.return_value = ax
    # axes[n] used in _chart_times
    axes = [MagicMock(), MagicMock(), MagicMock()]
    plt.subplots.return_value = (fig, axes)
    return plt, fig, ax, axes


# ---------------------------------------------------------------------------
# 1. _load_json
# ---------------------------------------------------------------------------


class TestLoadJson:
    def _fn(self):
        return _import_module()._load_json

    def test_returns_dict_from_existing_json_file(self, tmp_path):
        data = {"key": "value", "num": 42}
        f = tmp_path / "data.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        result = self._fn()(f)
        assert result == data

    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        result = self._fn()(tmp_path / "nonexistent.json")
        assert result == {}

    def test_nested_structure_preserved(self, tmp_path):
        data = {"a": {"b": [1, 2, 3]}}
        f = tmp_path / "nested.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        result = self._fn()(f)
        assert result["a"]["b"] == [1, 2, 3]

    def test_empty_json_object(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text("{}", encoding="utf-8")
        result = self._fn()(f)
        assert result == {}


# ---------------------------------------------------------------------------
# 2. _setup_matplotlib
# ---------------------------------------------------------------------------


class TestSetupMatplotlib:
    def test_returns_plt_object(self):
        m = _import_module()
        with patch("matplotlib.use"), patch("matplotlib.pyplot.rcParams") as mock_rc:
            mock_rc.update = MagicMock()
            import matplotlib.pyplot as real_plt

            result = m._setup_matplotlib()
            # Should be the real plt module (or something with rcParams)
            assert result is real_plt

    def test_sets_mplbackend_env_if_not_set(self, monkeypatch):
        monkeypatch.delenv("MPLBACKEND", raising=False)
        m = _import_module()
        with patch("matplotlib.use"), patch("matplotlib.pyplot.rcParams") as mock_rc:
            mock_rc.update = MagicMock()
            m._setup_matplotlib()
            import os

            assert os.environ.get("MPLBACKEND") == "Agg"

    def test_calls_matplotlib_use_agg(self):
        m = _import_module()
        with patch("matplotlib.use") as mock_use, patch("matplotlib.pyplot.rcParams") as mock_rc:
            mock_rc.update = MagicMock()
            m._setup_matplotlib()
            mock_use.assert_called_once_with("Agg")

    def test_calls_rcparams_update(self):
        m = _import_module()
        with patch("matplotlib.use"), patch("matplotlib.pyplot.rcParams") as mock_rc:
            mock_rc.update = MagicMock()
            m._setup_matplotlib()
            mock_rc.update.assert_called_once()
            update_kwargs = mock_rc.update.call_args[0][0]
            assert "figure.facecolor" in update_kwargs
            assert "font.family" in update_kwargs


# ---------------------------------------------------------------------------
# 3. _compute_times_totaux
# ---------------------------------------------------------------------------


class TestComputeTimesTotaux:
    def _setup(self):
        m = _import_module()
        _inject_times(m)
        return m

    def test_returns_four_items(self):
        m = self._setup()
        result = m._compute_times_totaux(np)
        assert len(result) == 4

    def test_nomes_match_times_data_names(self):
        m = self._setup()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        assert nomes_t == ["ADM", "TOP", "BIOLOGO"]

    def test_tot_mes_units_are_in_thousands(self):
        m = self._setup()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        # ADM: (448861 + 268331 + 324300) / 1e3 = 1041.492
        adm_val = (
            SAMPLE_TIMES_DATA[0]["custo_mo"] + SAMPLE_TIMES_DATA[0]["custo_eq"] + SAMPLE_TIMES_DATA[0]["verbas"]
        ) / 1e3
        assert abs(tot_mes[0] - adm_val) < 1e-6

    def test_sazonal_teams_get_azul_claro_color(self):
        m = self._setup()
        from concilium.application.benchmarks.charts._chart_colors import _CORES

        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        # BIOLOGO is sazonal → azul_claro
        assert cor_b[2] == _CORES["azul_claro"]

    def test_permanent_teams_get_azul_escuro_color(self):
        m = self._setup()
        from concilium.application.benchmarks.charts._chart_colors import _CORES

        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        # ADM is not sazonal → azul_escuro
        assert cor_b[0] == _CORES["azul_escuro"]

    def test_y_t_is_arange_of_correct_length(self):
        m = self._setup()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        np.testing.assert_array_equal(y_t, np.arange(3))


# ---------------------------------------------------------------------------
# 4. _compute_perm_breakdown
# ---------------------------------------------------------------------------


class TestComputePermBreakdown:
    def _setup(self):
        m = _import_module()
        _inject_times(m)
        return m

    def test_returns_five_items(self):
        m = self._setup()
        result = m._compute_perm_breakdown(np)
        assert len(result) == 5

    def test_only_permanent_teams_included(self):
        m = self._setup()
        nomes_b, mo_p, eq_p, vb_p, y_b2 = m._compute_perm_breakdown(np)
        # BIOLOGO is sazonal → excluded
        assert "BIOLOGO" not in nomes_b
        assert "ADM" in nomes_b
        assert "TOP" in nomes_b

    def test_percentages_sum_to_100(self):
        m = self._setup()
        nomes_b, mo_p, eq_p, vb_p, y_b2 = m._compute_perm_breakdown(np)
        for i in range(len(nomes_b)):
            total_pct = mo_p[i] + eq_p[i] + vb_p[i]
            assert abs(total_pct - 100.0) < 1e-6, f"Pct sum for {nomes_b[i]}: {total_pct}"

    def test_adm_mo_percentage_correct(self):
        m = self._setup()
        nomes_b, mo_p, eq_p, vb_p, y_b2 = m._compute_perm_breakdown(np)
        adm_idx = nomes_b.index("ADM")
        adm = SAMPLE_TIMES_DATA[0]
        tot = adm["custo_mo"] + adm["custo_eq"] + adm["verbas"]
        expected_mo_p = adm["custo_mo"] / tot * 100
        assert abs(mo_p[adm_idx] - expected_mo_p) < 1e-6

    def test_y_b2_is_arange_of_permanent_count(self):
        m = self._setup()
        nomes_b, mo_p, eq_p, vb_p, y_b2 = m._compute_perm_breakdown(np)
        # 2 permanent teams (ADM, TOP)
        np.testing.assert_array_equal(y_b2, np.arange(2))

    def test_team_with_zero_custo_eq_gives_zero_eq_pct(self):
        """LAB has custo_eq=0 → eq_p should be 0."""
        m = _import_module()
        m._TIMES_DATA = [
            {
                "nome": "LAB",
                "pessoas": 2,
                "custo_mo": 15310,
                "custo_eq": 0,
                "verbas": 1847,
                "perm": 12.57,
                "sazonal": False,
            }
        ]
        nomes_b, mo_p, eq_p, vb_p, y_b2 = m._compute_perm_breakdown(np)
        assert eq_p[0] == 0.0


# ---------------------------------------------------------------------------
# 5. _times_build_ax0
# ---------------------------------------------------------------------------


class TestTimesBuildAx0:
    def _setup(self):
        m = _import_module()
        _inject_times(m)
        return m

    def _make_mticker_stub(self):
        mticker = MagicMock()
        mticker.FuncFormatter = MagicMock(side_effect=lambda fn: fn)
        return mticker

    def test_calls_barh_for_each_team(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        assert ax.barh.call_count == len(SAMPLE_TIMES_DATA)

    def test_calls_text_for_each_team(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        assert ax.text.call_count == len(SAMPLE_TIMES_DATA)

    def test_sazonal_team_gets_hatch(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        # Third team (BIOLOGO) should have hatch
        third_call = ax.barh.call_args_list[2]
        assert third_call[1].get("hatch", "") == "////"

    def test_permanent_team_has_no_hatch(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        # First team (ADM, not sazonal) → hatch=""
        first_call = ax.barh.call_args_list[0]
        assert first_call[1].get("hatch", "") == ""

    def test_sets_xscale_log(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        ax.set_xscale.assert_called_once_with("log")

    def test_sets_invert_yaxis(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        ax.invert_yaxis.assert_called_once()

    def test_sazonal_star_in_label(self):
        """Sazonal teams should have ★ in text label."""
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        # third call is BIOLOGO (sazonal=True) → text should contain ★
        third_text_call = ax.text.call_args_list[2]
        label_str = third_text_call[0][2]  # positional arg index 2 is the text
        assert "★" in label_str

    def test_non_sazonal_no_star_in_label(self):
        """Non-sazonal teams should NOT have ★ in text label."""
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        m._times_build_ax0(ax, y_t, tot_mes, cor_b, nomes_t, mticker)
        first_text_call = ax.text.call_args_list[0]
        label_str = first_text_call[0][2]
        assert "★" not in label_str


# ---------------------------------------------------------------------------
# 6. _times_build_ax1
# ---------------------------------------------------------------------------


class TestTimesBuildAx1:
    def _setup(self):
        m = _import_module()
        _inject_times(m)
        return m

    def _make_inputs(self, m):
        nomes_b, mo_p, eq_p, vb_p, y_b2 = m._compute_perm_breakdown(np)
        return y_b2, nomes_b, mo_p, eq_p, vb_p

    def test_calls_barh_three_times(self):
        m = self._setup()
        ax = MagicMock()
        y_b2, nomes_b, mo_p, eq_p, vb_p = self._make_inputs(m)
        m._times_build_ax1(ax, y_b2, nomes_b, mo_p, eq_p, vb_p)
        assert ax.barh.call_count == 3  # MO, EQ, Verbas

    def test_sets_legend(self):
        m = self._setup()
        ax = MagicMock()
        y_b2, nomes_b, mo_p, eq_p, vb_p = self._make_inputs(m)
        m._times_build_ax1(ax, y_b2, nomes_b, mo_p, eq_p, vb_p)
        ax.legend.assert_called_once()

    def test_sets_invert_yaxis(self):
        m = self._setup()
        ax = MagicMock()
        y_b2, nomes_b, mo_p, eq_p, vb_p = self._make_inputs(m)
        m._times_build_ax1(ax, y_b2, nomes_b, mo_p, eq_p, vb_p)
        ax.invert_yaxis.assert_called_once()

    def test_sets_title(self):
        m = self._setup()
        ax = MagicMock()
        y_b2, nomes_b, mo_p, eq_p, vb_p = self._make_inputs(m)
        m._times_build_ax1(ax, y_b2, nomes_b, mo_p, eq_p, vb_p)
        ax.set_title.assert_called_once()
        assert "Breakdown" in ax.set_title.call_args[0][0]

    def test_text_drawn_for_large_percentages(self):
        """Percentages > 5% should get text annotations."""
        m = self._setup()
        ax = MagicMock()
        # Use high percentages to trigger text drawing
        mo_p = [80.0, 80.0]
        eq_p = [15.0, 15.0]
        vb_p = [5.0, 5.0]
        y_b2 = np.arange(2)
        nomes_b = ["A", "B"]
        m._times_build_ax1(ax, y_b2, nomes_b, mo_p, eq_p, vb_p)
        # Each team: mo (>5) + eq (>5) = 2 texts per team × 2 teams = 4 calls
        # vb = 5.0 which is NOT > 5, so no vb text
        assert ax.text.call_count == 4

    def test_no_text_for_small_percentages(self):
        """Percentages ≤ 5% should NOT get text annotations."""
        m = self._setup()
        ax = MagicMock()
        mo_p = [3.0]
        eq_p = [2.0]
        vb_p = [4.0]
        y_b2 = np.arange(1)
        nomes_b = ["Z"]
        m._times_build_ax1(ax, y_b2, nomes_b, mo_p, eq_p, vb_p)
        ax.text.assert_not_called()


# ---------------------------------------------------------------------------
# 7. _times_build_ax2
# ---------------------------------------------------------------------------


class TestTimesBuildAx2:
    def _setup(self):
        m = _import_module()
        _inject_times(m)
        return m

    def _make_mticker_stub(self):
        mticker = MagicMock()
        mticker.FuncFormatter = MagicMock(side_effect=lambda fn: fn)
        return mticker

    def test_calls_scatter_for_each_team(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        m._times_build_ax2(ax, mticker)
        assert ax.scatter.call_count == len(SAMPLE_TIMES_DATA)

    def test_calls_annotate_for_each_team(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        m._times_build_ax2(ax, mticker)
        assert ax.annotate.call_count == len(SAMPLE_TIMES_DATA)

    def test_sets_xscale_log(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        m._times_build_ax2(ax, mticker)
        ax.set_xscale.assert_called_once_with("log")

    def test_sets_title(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        m._times_build_ax2(ax, mticker)
        ax.set_title.assert_called_once()
        assert "Headcount" in ax.set_title.call_args[0][0]

    def test_sazonal_team_gets_triangle_marker(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        m._times_build_ax2(ax, mticker)
        # BIOLOGO (index 2) is sazonal → marker='^'
        biologo_call = ax.scatter.call_args_list[2]
        assert biologo_call[1]["marker"] == "^"

    def test_permanent_team_gets_circle_marker(self):
        m = self._setup()
        ax = MagicMock()
        mticker = self._make_mticker_stub()
        m._times_build_ax2(ax, mticker)
        # ADM (index 0) is not sazonal → marker='o'
        adm_call = ax.scatter.call_args_list[0]
        assert adm_call[1]["marker"] == "o"


# ---------------------------------------------------------------------------
# 8. _chart_waterfall
# ---------------------------------------------------------------------------


class TestChartWaterfall:
    def test_returns_path_to_png(self, tmp_path):
        m = _import_module()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        result = m._chart_waterfall(plt, tmp_path, "AGIS")
        assert result == tmp_path / "03_waterfall_financeiro.png"

    def test_savefig_called(self, tmp_path):
        m = _import_module()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_waterfall(plt, tmp_path, "AGIS")
        fig.savefig.assert_called_once()
        args = fig.savefig.call_args[0]
        assert args[0] == tmp_path / "03_waterfall_financeiro.png"

    def test_closes_figure(self, tmp_path):
        m = _import_module()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_waterfall(plt, tmp_path, "AGIS")
        plt.close.assert_called_once_with(fig)

    def test_suptitle_includes_slug(self, tmp_path):
        m = _import_module()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_waterfall(plt, tmp_path, "myslug")
        fig.suptitle.assert_called_once()
        title_text = fig.suptitle.call_args[0][0]
        assert "MYSLUG" in title_text

    def test_tight_layout_called(self, tmp_path):
        m = _import_module()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_waterfall(plt, tmp_path, "AGIS")
        plt.tight_layout.assert_called_once()

    def test_bars_drawn_for_all_wf_items(self, tmp_path):
        m = _import_module()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_waterfall(plt, tmp_path, "AGIS")
        # WF has 11 items → 11 bar calls
        assert ax.bar.call_count == 11

    def test_text_annotations_drawn(self, tmp_path):
        m = _import_module()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_waterfall(plt, tmp_path, "AGIS")
        # 11 items → 11 text calls + 1 for margin annotation
        assert ax.text.call_count >= 11


# ---------------------------------------------------------------------------
# 9. _chart_eap_crit
# ---------------------------------------------------------------------------


class TestChartEapCrit:
    def _setup(self):
        m = _import_module()
        _inject_eap(m)
        return m

    def test_returns_path_to_png(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        result = m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        assert result == tmp_path / "04_eap_criticidade.png"

    def test_savefig_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        fig.savefig.assert_called_once()

    def test_closes_figure(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        plt.close.assert_called_once_with(fig)

    def test_barh_called_once(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        ax.barh.assert_called_once()

    def test_suptitle_includes_slug(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "TESTSLUG", np)
        title_text = fig.suptitle.call_args[0][0]
        assert "TESTSLUG" in title_text

    def test_invert_yaxis_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        ax.invert_yaxis.assert_called_once()

    def test_legend_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        ax.legend.assert_called_once()

    def test_text_drawn_per_item(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        # One text call per EAP item
        assert ax.text.call_count == len(SAMPLE_EAP_DATA)

    def test_annotate_called_when_pe_gt_custo(self, tmp_path):
        """When pe_op > custo, annotate with arrow."""
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax = MagicMock()
        plt.subplots.return_value = (fig, ax)

        m._chart_eap_crit(plt, tmp_path, "AGIS", np)
        # Desmatamento: pe_op=14192824 > custo=2529041 → annotate
        # Esc 3aCat: pe_op=16188650 > custo=13912325 → annotate
        # PI: pe_op=503052 > custo=393487 → annotate
        assert ax.annotate.call_count == 3


# ---------------------------------------------------------------------------
# 10. _chart_indiretos
# ---------------------------------------------------------------------------


class TestChartIndiretos:
    def _setup(self):
        m = _import_module()
        _inject_indir(m)
        return m

    def test_returns_path_to_png(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax_pie = MagicMock()
        ax_bar = MagicMock()
        # pie returns (wedges, texts, ats) where ats is iterable
        ax_pie.pie.return_value = (MagicMock(), MagicMock(), [MagicMock()])
        plt.subplots.return_value = (fig, (ax_pie, ax_bar))
        ax_bar.barh.return_value = [MagicMock()]

        result = m._chart_indiretos(plt, tmp_path, "AGIS", np)
        assert result == tmp_path / "05_indiretos_composicao.png"

    def test_savefig_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax_pie = MagicMock()
        ax_bar = MagicMock()
        ax_pie.pie.return_value = (MagicMock(), MagicMock(), [MagicMock()])
        plt.subplots.return_value = (fig, (ax_pie, ax_bar))
        ax_bar.barh.return_value = [MagicMock()]

        m._chart_indiretos(plt, tmp_path, "AGIS", np)
        fig.savefig.assert_called_once()

    def test_closes_figure(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax_pie = MagicMock()
        ax_bar = MagicMock()
        ax_pie.pie.return_value = (MagicMock(), MagicMock(), [MagicMock()])
        plt.subplots.return_value = (fig, (ax_pie, ax_bar))
        ax_bar.barh.return_value = [MagicMock()]

        m._chart_indiretos(plt, tmp_path, "AGIS", np)
        plt.close.assert_called_once_with(fig)

    def test_pie_called_once(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax_pie = MagicMock()
        ax_bar = MagicMock()
        ax_pie.pie.return_value = (MagicMock(), MagicMock(), [MagicMock()])
        plt.subplots.return_value = (fig, (ax_pie, ax_bar))
        ax_bar.barh.return_value = [MagicMock()]

        m._chart_indiretos(plt, tmp_path, "AGIS", np)
        ax_pie.pie.assert_called_once()

    def test_suptitle_includes_total(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax_pie = MagicMock()
        ax_bar = MagicMock()
        ax_pie.pie.return_value = (MagicMock(), MagicMock(), [MagicMock()])
        plt.subplots.return_value = (fig, (ax_pie, ax_bar))
        ax_bar.barh.return_value = [MagicMock()]

        m._chart_indiretos(plt, tmp_path, "AGIS", np)
        title_text = fig.suptitle.call_args[0][0]
        expected_total = sum(SAMPLE_INDIR_DATA.values()) / 1e6
        assert f"{expected_total:.1f}M" in title_text

    def test_barh_called_once(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax_pie = MagicMock()
        ax_bar = MagicMock()
        ax_pie.pie.return_value = (MagicMock(), MagicMock(), [MagicMock()])
        plt.subplots.return_value = (fig, (ax_pie, ax_bar))
        ax_bar.barh.return_value = [MagicMock()]

        m._chart_indiretos(plt, tmp_path, "AGIS", np)
        ax_bar.barh.assert_called_once()

    def test_text_drawn_per_indir_item(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        ax_pie = MagicMock()
        ax_bar = MagicMock()
        ax_pie.pie.return_value = (MagicMock(), MagicMock(), [MagicMock()])
        plt.subplots.return_value = (fig, (ax_pie, ax_bar))
        # barh returns a list of bar objects equal to number of items
        bars = [MagicMock() for _ in SAMPLE_INDIR_DATA]
        ax_bar.barh.return_value = bars

        m._chart_indiretos(plt, tmp_path, "AGIS", np)
        # text on ax_pie (center) + text per bar on ax_bar
        assert ax_bar.text.call_count == len(SAMPLE_INDIR_DATA)


# ---------------------------------------------------------------------------
# 11. _chart_times
# ---------------------------------------------------------------------------


class TestChartTimes:
    def _setup(self):
        m = _import_module()
        _inject_times(m)
        return m

    def test_returns_path_to_png(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (fig, axes)

        result = m._chart_times(plt, tmp_path, "AGIS", np)
        assert result == tmp_path / "06_times_indiretos.png"

    def test_savefig_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (fig, axes)

        m._chart_times(plt, tmp_path, "AGIS", np)
        fig.savefig.assert_called_once()

    def test_closes_figure(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (fig, axes)

        m._chart_times(plt, tmp_path, "AGIS", np)
        plt.close.assert_called_once_with(fig)

    def test_suptitle_includes_slug(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (fig, axes)

        m._chart_times(plt, tmp_path, "MYSLUG", np)
        title_text = fig.suptitle.call_args[0][0]
        assert "MYSLUG" in title_text

    def test_tight_layout_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        axes = [MagicMock(), MagicMock(), MagicMock()]
        plt.subplots.return_value = (fig, axes)

        m._chart_times(plt, tmp_path, "AGIS", np)
        plt.tight_layout.assert_called_once()


# ---------------------------------------------------------------------------
# 12. _chart_plan_space
# ---------------------------------------------------------------------------


class TestChartPlanSpace:
    def _setup(self):
        m = _import_module()
        # Inject mock drawing functions
        m._ps_draw_pool_bars = MagicMock()
        m._ps_draw_deadline_makespan = MagicMock()
        m._ps_draw_delta_cd = MagicMock()
        m._ps_draw_viabilidade = MagicMock()
        m._ps_draw_insight = MagicMock()
        return m

    def _make_cenarios(self):
        return [
            {"slug": "A0_BASE_AUTO", "ESC3": 10, "ATERRO": 5},
            {"slug": "A1_ESC3_8", "ESC3": 8, "ATERRO": 5},
        ]

    def test_returns_path_to_png(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        gs = MagicMock()
        fig.add_gridspec.return_value = gs
        fig.add_subplot.return_value = MagicMock()
        plt.figure.return_value = fig
        cenarios = self._make_cenarios()
        np_mock = MagicMock()
        np_mock.arange.return_value = np.arange(len(cenarios))

        result = m._chart_plan_space(plt, tmp_path, "AGIS", cenarios, np_mock)
        assert result == tmp_path / "02_plan_space.png"

    def test_savefig_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        gs = MagicMock()
        fig.add_gridspec.return_value = gs
        fig.add_subplot.return_value = MagicMock()
        plt.figure.return_value = fig
        cenarios = self._make_cenarios()
        np_mock = MagicMock()
        np_mock.arange.return_value = np.arange(len(cenarios))

        m._chart_plan_space(plt, tmp_path, "AGIS", cenarios, np_mock)
        fig.savefig.assert_called_once()

    def test_closes_figure(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        gs = MagicMock()
        fig.add_gridspec.return_value = gs
        fig.add_subplot.return_value = MagicMock()
        plt.figure.return_value = fig
        cenarios = self._make_cenarios()
        np_mock = MagicMock()
        np_mock.arange.return_value = np.arange(len(cenarios))

        m._chart_plan_space(plt, tmp_path, "AGIS", cenarios, np_mock)
        plt.close.assert_called_once_with(fig)

    def test_suptitle_includes_slug(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        gs = MagicMock()
        fig.add_gridspec.return_value = gs
        fig.add_subplot.return_value = MagicMock()
        plt.figure.return_value = fig
        cenarios = self._make_cenarios()
        np_mock = MagicMock()
        np_mock.arange.return_value = np.arange(len(cenarios))

        m._chart_plan_space(plt, tmp_path, "MYSLUG", cenarios, np_mock)
        title_text = fig.suptitle.call_args[0][0]
        assert "MYSLUG" in title_text

    def test_all_ps_draw_functions_called(self, tmp_path):
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        gs = MagicMock()
        fig.add_gridspec.return_value = gs
        fig.add_subplot.return_value = MagicMock()
        plt.figure.return_value = fig
        cenarios = self._make_cenarios()
        np_mock = MagicMock()
        np_mock.arange.return_value = np.arange(len(cenarios))

        m._chart_plan_space(plt, tmp_path, "AGIS", cenarios, np_mock)
        m._ps_draw_pool_bars.assert_called()
        m._ps_draw_deadline_makespan.assert_called_once()
        m._ps_draw_delta_cd.assert_called_once()
        m._ps_draw_viabilidade.assert_called_once()
        m._ps_draw_insight.assert_called_once()

    def test_ps_draw_pool_bars_called_twice(self, tmp_path):
        """Pool bars called for ESC3 and ATERRO separately."""
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        gs = MagicMock()
        fig.add_gridspec.return_value = gs
        fig.add_subplot.return_value = MagicMock()
        plt.figure.return_value = fig
        cenarios = self._make_cenarios()
        np_mock = MagicMock()
        np_mock.arange.return_value = np.arange(len(cenarios))

        m._chart_plan_space(plt, tmp_path, "AGIS", cenarios, np_mock)
        assert m._ps_draw_pool_bars.call_count == 2

    def test_label_generation_splits_slug_correctly(self, tmp_path):
        """Labels should split cenario slugs on _ correctly."""
        m = self._setup()
        plt = MagicMock()
        fig = MagicMock()
        gs = MagicMock()
        fig.add_gridspec.return_value = gs
        fig.add_subplot.return_value = MagicMock()
        plt.figure.return_value = fig
        # Single cenario with known slug
        cenarios = [{"slug": "A0_BASE_AUTO"}]
        np_mock = MagicMock()
        np_mock.arange.return_value = np.arange(1)

        m._chart_plan_space(plt, tmp_path, "AGIS", cenarios, np_mock)
        # ps_draw_pool_bars is called with labels as positional arg
        pool_call = m._ps_draw_pool_bars.call_args_list[0]
        labels = pool_call[0][6]  # 7th positional arg
        assert labels == ["A0\nBASE_AUTO"]


# ---------------------------------------------------------------------------
# 13. Edge-case / integration tests
# ---------------------------------------------------------------------------


class TestComputeTimesTotauxSingleSazonal:
    """Edge case: all teams are sazonal."""

    def test_all_sazonal_get_azul_claro(self):
        m = _import_module()
        m._TIMES_DATA = [
            {"nome": "X", "pessoas": 1, "custo_mo": 5000, "custo_eq": 0, "verbas": 0, "perm": 3.0, "sazonal": True},
        ]
        from concilium.application.benchmarks.charts._chart_colors import _CORES

        nomes_t, tot_mes, cor_b, y_t = m._compute_times_totaux(np)
        assert cor_b[0] == _CORES["azul_claro"]


class TestComputePermBreakdownAllSazonal:
    """Edge case: all teams sazonal → empty perm breakdown."""

    def test_all_sazonal_returns_empty_arrays(self):
        m = _import_module()
        m._TIMES_DATA = [
            {"nome": "X", "pessoas": 1, "custo_mo": 5000, "custo_eq": 0, "verbas": 0, "perm": 3.0, "sazonal": True},
        ]
        nomes_b, mo_p, eq_p, vb_p, y_b2 = m._compute_perm_breakdown(np)
        assert nomes_b == []
        assert mo_p == []
        assert eq_p == []
        assert vb_p == []
        np.testing.assert_array_equal(y_b2, np.arange(0))


class TestLoadJsonUtf8:
    def test_utf8_content_decoded_correctly(self, tmp_path):
        m = _import_module()
        data = {"nome": "Escavaçãó", "valor": 123}
        f = tmp_path / "utf8.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result = m._load_json(f)
        assert result["nome"] == "Escavaçãó"
