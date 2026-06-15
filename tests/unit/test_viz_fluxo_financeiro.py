"""Tests for build_fluxo_financeiro in fluxo_financeiro.py.

Covers all missing lines including:
- early-return paths (non-dict, missing labels, empty saldo, ImportError)
- happy path with receita and saldo present (returns bytes)
- break-even line path (saldo_acum has negative values followed by positive)
- no receita path (ax_saldo and ax2 hidden)
- be_idx path (receita >= despesa triggers axvline + annotate)
- rendering exception path (returns None)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.charts.fluxo_financeiro"
_INIT_MLP_PATCH = f"{_MOD}.init_mpl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_fn():
    import importlib
    mod = importlib.import_module(_MOD)
    return mod.build_fluxo_financeiro


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _make_ax_mock():
    ax = MagicMock()
    return ax


def _make_three_axes():
    ax1 = _make_ax_mock()
    ax_saldo = _make_ax_mock()
    ax2 = _make_ax_mock()
    return ax1, ax_saldo, ax2


def _make_plt_mock(ax1=None, ax_saldo=None, ax2=None):
    """Return (mock_plt, mock_fig, ax1, ax_saldo, ax2)."""
    if ax1 is None:
        ax1 = _make_ax_mock()
    if ax_saldo is None:
        ax_saldo = _make_ax_mock()
    if ax2 is None:
        ax2 = _make_ax_mock()
    mock_fig = MagicMock()
    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, (ax1, ax_saldo, ax2))
    return mock_plt, mock_fig, ax1, ax_saldo, ax2


def _patched_init_mpl(mock_plt):
    return patch(_INIT_MLP_PATCH, return_value=(mock_plt, _fig_to_bytes_stub))


def _minimal_financeiro(**kwargs):
    """Minimal valid financeiro dict."""
    base = {
        "labels": ["Jan", "Feb", "Mar"],
        "receita": [10_000_000, 20_000_000, 30_000_000],
        "saldo": [1_000_000, 2_000_000, 3_000_000],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# 1. Early-return paths
# ---------------------------------------------------------------------------

class TestEarlyReturns:
    def test_not_a_dict_returns_none(self):
        """financeiro is not a dict → return None immediately."""
        build = _import_fn()
        assert build(None) is None

    def test_empty_dict_returns_none(self):
        """Empty dict (no 'labels') → return None."""
        build = _import_fn()
        assert build({}) is None

    def test_labels_key_absent_returns_none(self):
        """Dict without 'labels' → return None."""
        build = _import_fn()
        assert build({"saldo": [1.0]}) is None

    def test_labels_empty_list_returns_none(self):
        """Dict with labels=[] (falsy) → return None immediately."""
        build = _import_fn()
        assert build({"labels": [], "saldo": [1.0]}) is None

    def test_saldo_empty_returns_none(self):
        """labels present but saldo empty → return None after list comprehension."""
        build = _import_fn()
        assert build({"labels": ["Jan"], "saldo": []}) is None

    def test_import_error_returns_none(self):
        """ImportError from init_mpl → return None."""
        build = _import_fn()
        with patch(_INIT_MLP_PATCH, side_effect=ImportError("no matplotlib")):
            assert build(_minimal_financeiro()) is None

    def test_non_dict_list_returns_none(self):
        """financeiro is a list → return None."""
        build = _import_fn()
        assert build(["Jan", "Feb"]) is None

    def test_non_dict_string_returns_none(self):
        """financeiro is a string → return None."""
        build = _import_fn()
        assert build("labels") is None


# ---------------------------------------------------------------------------
# 2. Happy path with receita and saldo
# ---------------------------------------------------------------------------

class TestHappyPathWithReceita:
    def test_returns_bytes(self):
        """Full valid financeiro → returns bytes."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build(_minimal_financeiro())
        assert isinstance(result, bytes)
        assert result == b"PNG"

    def test_none_values_in_receita_treated_as_zero(self):
        """None values in receita/saldo are replaced with 0.0."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb"],
            "receita": [None, 10_000_000],
            "saldo": [None, 1_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"

    def test_receita_longer_than_saldo_truncates(self):
        """When receita is longer than saldo, n=min(len) is used."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [10_000_000, 20_000_000, 30_000_000, 40_000_000],
            "saldo": [1_000_000, 2_000_000, 3_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"

    def test_saldo_longer_than_receita_truncates(self):
        """When saldo is longer than receita, n=min(len) is used."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [10_000_000, 20_000_000],
            "saldo": [1_000_000, 2_000_000, 3_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 3. Break-even (saldo_acum) path — negative before positive
# ---------------------------------------------------------------------------

class TestBreakEvenSaldoAcum:
    def test_breakeven_line_drawn_when_saldo_turns_positive(self):
        """saldo_acum starts negative then turns positive → axvline called on ax_saldo."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        # receita small, saldo (per-period) negative initially → accumulated saldo negative at first
        # receita=5M, saldo(period)=-3M each => despesa_per = receita - saldo = 8M
        # period1: r_acum=5, d_acum=8 → saldo_acum=-3 (negative)
        # period2: r_acum=10, d_acum=16 → saldo_acum=-6 still negative
        # period3: r_acum=100, d_acum=24 → saldo_acum=76 (positive) — break-even!
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [5_000_000, 5_000_000, 90_000_000],
            "saldo": [-3_000_000, -3_000_000, 70_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"
        # ax_saldo.axvline should have been called for the break-even marker
        assert ax_saldo.axvline.called

    def test_breakeven_legend_called_when_breakeven_found(self):
        """When break-even is found in saldo_acum, ax_saldo.legend is called."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [5_000_000, 5_000_000, 90_000_000],
            "saldo": [-3_000_000, -3_000_000, 70_000_000],
        }
        with _patched_init_mpl(mock_plt):
            build(financeiro)
        ax_saldo.legend.assert_called()

    def test_no_breakeven_when_saldo_acum_always_negative(self):
        """When saldo_acum is always negative, be_zero_idx is None → no axvline on ax_saldo."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        # saldo_acum = sum(period saldo values); all negative → be_zero_idx=None
        # with receita=10M and period saldo=-5M: despesa_per=15M, so saldo_acum < 0 always
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [10_000_000, 10_000_000, 10_000_000],
            "saldo": [-5_000_000, -5_000_000, -5_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"
        # ax_saldo.axvline should NOT have been called (be_zero_idx is None)
        assert not ax_saldo.axvline.called


# ---------------------------------------------------------------------------
# 4. be_idx (receita >= despesa break-even) path
# ---------------------------------------------------------------------------

class TestBeIdx:
    def test_be_idx_axvline_and_annotate_called(self):
        """When receita_acum >= despesa_acum at some point → ax2.axvline + ax2.annotate called."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        # receita much larger at period 3 → be_idx = 2
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [5_000_000, 5_000_000, 100_000_000],
            "saldo": [1_000_000, 1_000_000, 80_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"
        assert ax2.axvline.called
        assert ax2.annotate.called

    def test_be_idx_none_when_despesa_always_exceeds_receita(self):
        """When despesa_acum always > receita_acum → be_idx is None → no axvline on ax2."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        # small receita, large saldo-based despesa → despesa always > receita
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [1_000_000, 1_000_000, 1_000_000],
            "saldo": [-50_000_000, -50_000_000, -50_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"
        assert not ax2.axvline.called


# ---------------------------------------------------------------------------
# 5. No receita path — ax_saldo and ax2 set_visible(False)
# ---------------------------------------------------------------------------

class TestNoReceita:
    def test_no_receita_hides_ax_saldo_and_ax2(self):
        """When receita key is absent (empty list) → ax_saldo and ax2 set_visible(False)."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "saldo": [1_000_000, 2_000_000, 3_000_000],
            # no 'receita' key → defaults to []
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"
        ax_saldo.set_visible.assert_called_once_with(False)
        ax2.set_visible.assert_called_once_with(False)

    def test_empty_receita_list_hides_ax_saldo_and_ax2(self):
        """Explicit empty receita list → ax_saldo and ax2 hidden."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb"],
            "receita": [],
            "saldo": [1_000_000, 2_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"
        ax_saldo.set_visible.assert_called_once_with(False)
        ax2.set_visible.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# 6. Exception inside plotting block → returns None
# ---------------------------------------------------------------------------

class TestExceptionPath:
    def test_subplots_raises_returns_none(self):
        """When plt.subplots raises, the except block catches it and returns None."""
        build = _import_fn()
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("render boom")
        with patch(_INIT_MLP_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)):
            result = build(_minimal_financeiro())
        assert result is None

    def test_fig_to_bytes_raises_returns_none(self):
        """When fig_to_bytes raises, the except block catches it and returns None."""
        def _bad_fig_to_bytes(fig):
            raise OSError("disk full")

        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with patch(_INIT_MLP_PATCH, return_value=(mock_plt, _bad_fig_to_bytes)):
            result = build(_minimal_financeiro())
        assert result is None

    def test_ax_bar_raises_returns_none(self):
        """When ax1.bar raises, the except block catches it and returns None."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        ax1.bar.side_effect = ValueError("invalid data")
        with patch(_INIT_MLP_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)):
            result = build(_minimal_financeiro())
        assert result is None


# ---------------------------------------------------------------------------
# 7. Negative saldo values affect bar colors
# ---------------------------------------------------------------------------

class TestBarColors:
    def test_negative_saldo_values_use_red_color(self):
        """Negative saldo values → bar_colors uses '#c05c18'; still returns bytes."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb", "Mar"],
            "receita": [10_000_000, 10_000_000, 10_000_000],
            "saldo": [-5_000_000, 2_000_000, -1_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"

    def test_mixed_saldo_signs(self):
        """Mixed positive/negative saldo — both color codes used."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        financeiro = {
            "labels": ["Jan", "Feb"],
            "receita": [20_000_000, 20_000_000],
            "saldo": [-5_000_000, 5_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"
        # ax1.bar was called
        assert ax1.bar.called
        call_args = ax1.bar.call_args
        colors = call_args[0][2] if len(call_args[0]) >= 3 else call_args[1].get("color")
        if colors is not None:
            assert "#c05c18" in colors
            assert "#1a3a5c" in colors


# ---------------------------------------------------------------------------
# 8. Labels with only one period
# ---------------------------------------------------------------------------

class TestSinglePeriod:
    def test_single_period_returns_bytes(self):
        """Single period should work without list index errors."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        financeiro = {
            "labels": ["Jan"],
            "receita": [10_000_000],
            "saldo": [5_000_000],
        }
        with _patched_init_mpl(mock_plt):
            result = build(financeiro)
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 9. fig.suptitle and tight_layout are called
# ---------------------------------------------------------------------------

class TestFigSuptitle:
    def test_fig_suptitle_called(self):
        """fig.suptitle is called with 'Analise Financeira'."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build(_minimal_financeiro())
        mock_fig.suptitle.assert_called_once()
        call_args = mock_fig.suptitle.call_args
        assert "Analise Financeira" in call_args[0][0]

    def test_tight_layout_called(self):
        """fig.tight_layout is called."""
        build = _import_fn()
        mock_plt, mock_fig, ax1, ax_saldo, ax2 = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build(_minimal_financeiro())
        mock_fig.tight_layout.assert_called_once()
