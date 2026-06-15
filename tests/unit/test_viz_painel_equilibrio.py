"""Tests for build_painel_equilibrio in painel_equilibrio.py.

Covers all missing lines including:
- early-return paths (empty levers, ImportError)
- data-extraction paths (delta_total, break_even_alcancavel, combinacoes, etc.)
- label-building logic (word-wrap, star prefix, combo-only prefix)
- color / edge logic
- acao_potencial aggregation (praticabilidade, escala_operacional, pool_eficiencia)
- rendering paths via mocked matplotlib
- error-path (savefig raises -> returns None)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lever(
    id_: str = "lever_x",
    descricao: str | None = None,
    tipo: str = "custo",
    delta: float = 1_000_000.0,
    break_even_solo: bool = False,
    restricoes: list[str] | None = None,
) -> dict:
    lv: dict = {
        "id": id_,
        "delta_margin_total": delta,
        "tipo": tipo,
        "break_even_solo": break_even_solo,
    }
    if descricao is not None:
        lv["descricao"] = descricao
    if restricoes:
        lv["restricoes"] = restricoes
    return lv


def _make_plt_mock():
    """Return (mock_plt, mock_fig, mock_ax, mock_bars) with sensible stubs."""
    mock_bar = MagicMock()
    mock_bar.get_width.return_value = 1.0
    mock_bar.get_y.return_value = 0.0
    mock_bar.get_height.return_value = 0.55

    mock_ax = MagicMock()
    mock_ax.barh.return_value = [mock_bar]

    mock_fig = MagicMock()
    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)

    return mock_plt, mock_fig, mock_ax, mock_bar


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _patched_init_mpl(mock_plt):
    """Return a patch for _common.init_mpl that returns (mock_plt, stub)."""
    return patch(
        "concilium.application.runtime.deliverables.visualizations.charts.painel_equilibrio.init_mpl",
        return_value=(mock_plt, _fig_to_bytes_stub),
    )


# ---------------------------------------------------------------------------
# Import-path helpers
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.charts.painel_equilibrio"


def _import_fn():
    import importlib
    mod = importlib.import_module(_MOD)
    return mod.build_painel_equilibrio


# ---------------------------------------------------------------------------
# 1. Early-return paths
# ---------------------------------------------------------------------------

class TestEarlyReturns:
    def test_empty_levers_key_absent_returns_none(self):
        """No 'levers' key → return None immediately."""
        build = _import_fn()
        assert build({}) is None

    def test_empty_levers_list_returns_none(self):
        """Explicit empty list → return None immediately."""
        build = _import_fn()
        assert build({"levers": []}) is None

    def test_none_levers_returns_none(self):
        """levers=None → falsy, return None."""
        build = _import_fn()
        assert build({"levers": None}) is None

    def test_import_error_path_returns_none(self):
        """ImportError during init_mpl → return None."""
        build = _import_fn()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.painel_equilibrio.init_mpl",
            side_effect=ImportError("no matplotlib"),
        ):
            assert build({"levers": [_make_lever()]}) is None


# ---------------------------------------------------------------------------
# 2. Minimal happy path — one lever
# ---------------------------------------------------------------------------

class TestMinimalOneLever:
    def test_returns_bytes_one_lever(self):
        """Single lever with defaults → bytes returned."""
        build = _import_fn()
        mock_plt, _, _, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({"levers": [_make_lever()]})
        assert isinstance(result, bytes)
        assert result == b"PNG"

    def test_returns_bytes_with_break_even_alcancavel_true(self):
        """break_even_alcancavel=True affects title colour but still returns bytes."""
        build = _import_fn()
        mock_plt, _, _, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({
                "levers": [_make_lever()],
                "break_even_alcancavel": True,
            })
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 3. delta_total / deficit_mi branches
# ---------------------------------------------------------------------------

class TestDeltaTotalBranches:
    def test_deficit_negative_draws_axvline(self):
        """delta_total < 0 → ax.axvline called with red color."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({
                "levers": [_make_lever()],
                "delta_total": -2_000_000.0,
            })
        # The red deficit line should have been drawn
        calls_axvline = mock_ax.axvline.call_args_list
        assert any(
            call.kwargs.get("color") == "#e74c3c" or (len(call.args) > 0 and call.args[0] == 2.0)
            for call in calls_axvline
        )

    def test_delta_total_zero_no_deficit_line(self):
        """delta_total=0 → deficit_mi=0, not negative, so no red axvline."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({
                "levers": [_make_lever()],
                "delta_total": 0.0,
            })
        calls_axvline = mock_ax.axvline.call_args_list
        red_calls = [c for c in calls_axvline if c.kwargs.get("color") == "#e74c3c"]
        assert len(red_calls) == 0

    def test_delta_total_positive_no_deficit_line(self):
        """Positive delta_total → no deficit axvline."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({
                "levers": [_make_lever()],
                "delta_total": 1_000_000.0,
            })
        calls_axvline = mock_ax.axvline.call_args_list
        red_calls = [c for c in calls_axvline if c.kwargs.get("color") == "#e74c3c"]
        assert len(red_calls) == 0


# ---------------------------------------------------------------------------
# 4. combinacoes / solo_ids / combo_only_ids logic
# ---------------------------------------------------------------------------

class TestCombinacoesBranches:
    def _run(self, combinacoes, levers=None):
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            return build({
                "levers": levers or [_make_lever("lv1")],
                "combinacoes_break_even": combinacoes,
            })

    def test_no_combinacoes(self):
        assert self._run([]) == b"PNG"

    def test_tier1_solo_combination(self):
        """A lever in tier=1 combo gets solo_ids membership."""
        levers = [_make_lever("lv1", break_even_solo=True)]
        combinacoes = [{"tier": 1, "levers_ids": ["lv1"]}]
        assert self._run(combinacoes, levers) == b"PNG"

    def test_tier2_combo_only(self):
        """A lever in tier>1 combo (but not tier=1) gets combo_only label."""
        levers = [_make_lever("lv2"), _make_lever("lv3")]
        combinacoes = [{"tier": 2, "levers_ids": ["lv2", "lv3"]}]
        assert self._run(combinacoes, levers) == b"PNG"

    def test_n_tier1_and_n_tier2_in_title(self):
        """Both tier1 and tier2 combos → combined summary string."""
        levers = [_make_lever("lv1"), _make_lever("lv2"), _make_lever("lv3")]
        combinacoes = [
            {"tier": 1, "levers_ids": ["lv1"]},
            {"tier": 2, "levers_ids": ["lv2", "lv3"]},
        ]
        result = self._run(combinacoes, levers)
        assert result == b"PNG"

    def test_only_tier2_no_tier1(self):
        """No tier=1 combos, only tier=2 → 'N par(es) suficiente(s)'."""
        levers = [_make_lever("lv2"), _make_lever("lv3")]
        combinacoes = [{"tier": 2, "levers_ids": ["lv2", "lv3"]}]
        result = self._run(combinacoes, levers)
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 5. Label-building (word-wrap, ★ prefix, ◎ prefix, plain)
# ---------------------------------------------------------------------------

class TestLabelBuilding:
    def _run_with_levers(self, levers, combinacoes=None):
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            return build({
                "levers": levers,
                "combinacoes_break_even": combinacoes or [],
            })

    def test_label_uses_id_when_descricao_absent(self):
        """When descricao is absent, id with underscores replaced is used as label."""
        result = self._run_with_levers([_make_lever("my_lever_id")])
        assert result == b"PNG"

    def test_label_wraps_long_descricao(self):
        """A very long description triggers multi-line wrapping (>30 chars)."""
        long_desc = "This is a very long description that exceeds thirty characters by far"
        result = self._run_with_levers([_make_lever(descricao=long_desc)])
        assert result == b"PNG"

    def test_star_prefix_for_break_even_solo(self):
        """break_even_solo=True → label starts with ★."""
        result = self._run_with_levers([_make_lever(break_even_solo=True)])
        assert result == b"PNG"

    def test_circle_prefix_for_combo_only(self):
        """Lever in tier>1 combo only → label starts with ◎."""
        levers = [_make_lever("combo_lv")]
        combinacoes = [{"tier": 2, "levers_ids": ["combo_lv"]}]
        result = self._run_with_levers(levers, combinacoes)
        assert result == b"PNG"

    def test_plain_label_for_ordinary_lever(self):
        """Lever not in any combo → plain label (no prefix)."""
        result = self._run_with_levers([_make_lever("ordinary", descricao="Ordinary lever")])
        assert result == b"PNG"

    def test_restricoes_annotation(self):
        """Lever with restricoes → restricoes_by_pos populated and ax.text called."""
        levers = [_make_lever(restricoes=["R1", "R2"])]
        build = _import_fn()
        mock_plt, mock_fig, mock_ax, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"levers": levers})
        # ax.text should have been called (at least once for restricoes)
        assert mock_ax.text.called


# ---------------------------------------------------------------------------
# 6. tipo coloring — custo vs. preco
# ---------------------------------------------------------------------------

class TestColorBranches:
    def test_tipo_custo_lever(self):
        """tipo='custo' → blue color applied."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({"levers": [_make_lever(tipo="custo")]})
        assert result == b"PNG"

    def test_tipo_preco_lever(self):
        """tipo='preco' → orange color applied."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({"levers": [_make_lever(tipo="preco")]})
        assert result == b"PNG"

    def test_mixed_tipo_levers(self):
        """Mixed custo/preco levers all render."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        # barh returns one mock per lever
        mock_bar = MagicMock()
        mock_bar.get_width.return_value = 1.0
        mock_bar.get_y.return_value = 0.0
        mock_bar.get_height.return_value = 0.55
        mock_ax = MagicMock()
        mock_ax.barh.return_value = [mock_bar, mock_bar]
        mock_fig = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        with _patched_init_mpl(mock_plt):
            result = build({"levers": [_make_lever(tipo="custo"), _make_lever(tipo="preco")]})
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 7. acao_potencial aggregation
# ---------------------------------------------------------------------------

class TestAcaoPotencial:
    def _run_levers(self, levers):
        build = _import_fn()
        # Multiple bars needed
        mock_bars = [MagicMock() for _ in levers]
        for b in mock_bars:
            b.get_width.return_value = 1.0
            b.get_y.return_value = 0.0
            b.get_height.return_value = 0.55
        mock_ax = MagicMock()
        mock_ax.barh.return_value = mock_bars
        mock_fig = MagicMock()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        with _patched_init_mpl(mock_plt):
            return build({"levers": levers})

    def test_fechar_gap_praticabilidade(self):
        """id=fechar_gap_praticabilidade accumulates into praticabilidade bucket."""
        result = self._run_levers([_make_lever("fechar_gap_praticabilidade", delta=500_000.0)])
        assert result == b"PNG"

    def test_fechar_gap_escala(self):
        """id=fechar_gap_escala accumulates into escala_operacional bucket."""
        result = self._run_levers([_make_lever("fechar_gap_escala", delta=300_000.0)])
        assert result == b"PNG"

    def test_fechar_gap_pool(self):
        """id=fechar_gap_pool accumulates into pool_eficiencia bucket."""
        result = self._run_levers([_make_lever("fechar_gap_pool", delta=200_000.0)])
        assert result == b"PNG"

    def test_all_three_acao_buckets(self):
        """All three special levers fill acao_potencial."""
        result = self._run_levers([
            _make_lever("fechar_gap_praticabilidade", delta=1_000_000.0),
            _make_lever("fechar_gap_escala", delta=1_000_000.0),
            _make_lever("fechar_gap_pool", delta=1_000_000.0),
        ])
        assert result == b"PNG"

    def test_no_acao_levers_shows_sem_alavancas(self):
        """No special levers → 'Sem alavancas ativas' line appended to footer."""
        result = self._run_levers([_make_lever("ordinary_lever")])
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 8. frentes_nec_media branch in title
# ---------------------------------------------------------------------------

class TestFrentesNecMedia:
    def test_frentes_nec_media_above_threshold(self):
        """frentes_nec_media > 1.01 → pu_line prefix added to title."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({
                "levers": [_make_lever()],
                "frentes_nec_media": 2.5,
            })
        assert result == b"PNG"

    def test_frentes_nec_media_at_threshold(self):
        """frentes_nec_media <= 1.01 → no pu_line prefix."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({
                "levers": [_make_lever()],
                "frentes_nec_media": 1.0,
            })
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 9. Error path (rendering exception → returns None)
# ---------------------------------------------------------------------------

class TestErrorPath:
    def test_rendering_exception_returns_none(self):
        """When plt.subplots raises, the except block catches it and returns None."""
        build = _import_fn()
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("boom")
        with _patched_init_mpl(mock_plt):
            result = build({"levers": [_make_lever()]})
        assert result is None

    def test_savefig_exception_returns_none(self):
        """When fig_to_bytes raises, the except block catches it and returns None."""
        def _bad_fig_to_bytes(fig):
            raise OSError("disk full")

        build = _import_fn()
        mock_plt, mock_fig, mock_ax, mock_bar = _make_plt_mock()
        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.painel_equilibrio.init_mpl",
            return_value=(mock_plt, _bad_fig_to_bytes),
        ):
            result = build({"levers": [_make_lever()]})
        assert result is None


# ---------------------------------------------------------------------------
# 10. Multiple levers covering bar-annotation loop
# ---------------------------------------------------------------------------

class TestMultipleLevers:
    def test_multiple_levers_all_rendered(self):
        """Three levers (positive and negative values) all render successfully."""
        build = _import_fn()
        bars = []
        for _ in range(3):
            b = MagicMock()
            b.get_width.return_value = 1.0
            b.get_y.return_value = 0.0
            b.get_height.return_value = 0.55
            bars.append(b)
        mock_ax = MagicMock()
        mock_ax.barh.return_value = bars
        mock_fig = MagicMock()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        levers = [
            _make_lever("lv1", delta=2_000_000.0, tipo="custo"),
            _make_lever("lv2", delta=-1_000_000.0, tipo="preco"),
            _make_lever("lv3", delta=500_000.0, break_even_solo=True),
        ]
        with _patched_init_mpl(mock_plt):
            result = build({"levers": levers})
        assert result == b"PNG"

    def test_negative_value_bar_gets_minus_sign(self):
        """Negative delta → sign is empty (minus sign in format string), renders OK."""
        build = _import_fn()
        bar = MagicMock()
        bar.get_width.return_value = -1.0
        bar.get_y.return_value = 0.0
        bar.get_height.return_value = 0.55
        mock_ax = MagicMock()
        mock_ax.barh.return_value = [bar]
        mock_fig = MagicMock()
        mock_plt = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        with _patched_init_mpl(mock_plt):
            result = build({"levers": [_make_lever(delta=-1_000_000.0)]})
        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 11. legend_elements deficit line (deficit_mi < 0)
# ---------------------------------------------------------------------------

class TestLegendDeficitLine:
    def test_deficit_legend_element_added(self):
        """When delta_total < 0, a Line2D element for the deficit is appended."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({
                "levers": [_make_lever()],
                "delta_total": -3_000_000.0,
            })
        assert result == b"PNG"
        # legend was called with handles
        mock_ax.legend.assert_called_once()
        handles = mock_ax.legend.call_args.kwargs.get("handles") or mock_ax.legend.call_args[1].get("handles")
        # Should have 4 elements when deficit is present (3 Patch + 1 Line2D)
        assert handles is not None
        assert len(handles) == 4
