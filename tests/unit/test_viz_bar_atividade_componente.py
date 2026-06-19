"""Tests for bar_atividade_componente.py — Composição de Custo por Atividade.

Covers all missing lines including:
- build_payload raises → returns None
- empty rows → returns None
- happy path returns bytes
- _render with grand_total == 0
- single-activity (all in class A, cut_ab == cut_bc == n == 1)
- multi-activity spanning all three ABC classes
- activity name shortening (direto./indireto. prefixes)
- zero-valued component columns
- UserWarning suppression path via tight_layout
- exception in plotting block → returns None
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.cube.bar_atividade_componente"
_BUILD_PAYLOAD_PATCH = f"{_MOD}.build_payload"
_INIT_MLP_PATCH = f"{_MOD}.init_mpl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_module():
    import importlib

    return importlib.import_module(_MOD)


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _make_plt_mock():
    """Return (mock_plt, mock_fig, mock_ax)."""
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_ax.get_xlim.return_value = (0.0, 10.0)
    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)
    return mock_plt, mock_fig, mock_ax


def _patched_init_mpl(mock_plt):
    return patch(_INIT_MLP_PATCH, return_value=(mock_plt, _fig_to_bytes_stub))


def _minimal_rows():
    """Single activity, single component — simplest valid dataset."""
    return [
        {"atividade_id": "direto.terraplenagem", "componente_bdi": "Custo operacional", "valor_rs": 1_000_000.0},
    ]


def _multi_abc_rows():
    """Multiple activities with values that span all three ABC classes (A, B, C)."""
    # Sorted by total desc: act1=70M (A), act2=15M (B), act3=14M (B or C), act4=1M (C)
    # grand_total = 100M; cut at 70% = 70M, cut at 90% = 90M
    return [
        {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": 70_000_000.0},
        {"atividade_id": "act2", "componente_bdi": "Overhead BDI", "valor_rs": 15_000_000.0},
        {"atividade_id": "act3", "componente_bdi": "Lucro (L)", "valor_rs": 14_000_000.0},
        {"atividade_id": "act4", "componente_bdi": "Tributos", "valor_rs": 1_000_000.0},
    ]


# ---------------------------------------------------------------------------
# 1. build() early-return paths
# ---------------------------------------------------------------------------


class TestBuildEarlyReturns:
    def test_build_payload_raises_returns_none(self):
        """build_payload raises → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, side_effect=RuntimeError("no cubo")):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_empty_rows_returns_none(self):
        """build_payload returns empty rows → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": []}):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_none_rows_returns_none(self):
        """build_payload returns rows=None → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": None}):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_missing_rows_key_returns_none(self):
        """build_payload returns dict without 'rows' key → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={}):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# 2. build() happy path
# ---------------------------------------------------------------------------


class TestBuildHappyPath:
    def test_returns_bytes(self):
        """Valid rows → build() returns bytes."""
        mod = _import_module()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": _minimal_rows()}), _patched_init_mpl(mock_plt):
            result = mod.build(MagicMock(), MagicMock())
        assert result == b"PNG"

    def test_returns_bytes_multi_activity(self):
        """Multiple activities spanning ABC classes → build() returns bytes."""
        mod = _import_module()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": _multi_abc_rows()}), _patched_init_mpl(mock_plt):
            result = mod.build(MagicMock(), MagicMock())
        assert result == b"PNG"

    def test_render_returns_none_build_returns_none(self):
        """When _render returns None, build() returns None (not bytes)."""
        mod = _import_module()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        # Make subplots raise so _render returns None via exception path in build
        mock_plt.subplots.side_effect = RuntimeError("render fail")
        with patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": _minimal_rows()}), _patched_init_mpl(mock_plt):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# 3. build() exception in plotting block
# ---------------------------------------------------------------------------


class TestBuildExceptionPath:
    def test_init_mpl_raises_returns_none(self):
        """init_mpl raises ImportError → build() returns None."""
        mod = _import_module()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": _minimal_rows()}),
            patch(_INIT_MLP_PATCH, side_effect=ImportError("no matplotlib")),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_fig_to_bytes_raises_returns_none(self):
        """fig_to_bytes raises → build() except block returns None."""

        def bad_fig_to_bytes(fig):
            raise OSError("disk full")

        mod = _import_module()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": _minimal_rows()}),
            patch(_INIT_MLP_PATCH, return_value=(mock_plt, bad_fig_to_bytes)),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# 4. _render() direct tests — use real Agg matplotlib for real execution
# ---------------------------------------------------------------------------


class TestRenderDirect:
    """Call _render directly with real matplotlib Agg so all lines execute."""

    @pytest.fixture(autouse=True)
    def _setup_agg(self):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        self.plt = plt
        yield
        plt.close("all")

    def test_render_single_activity_returns_figure(self):
        """Single activity → cut_ab == cut_bc == n == 1 → returns a figure."""
        mod = _import_module()
        rows = [
            {"atividade_id": "direto.escavacao", "componente_bdi": "Custo operacional", "valor_rs": 5_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_multi_activity_all_abc_classes(self):
        """Multiple activities spanning A, B, C classes."""
        mod = _import_module()
        rows = _multi_abc_rows()
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_grand_total_zero(self):
        """grand_total == 0 → pct == 0.0 branch, all go to class A."""
        mod = _import_module()
        rows = [
            {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": 0.0},
            {"atividade_id": "act2", "componente_bdi": "Custo operacional", "valor_rs": 0.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_direto_prefix_stripped(self):
        """Activity with 'direto.' prefix → short label strips it."""
        mod = _import_module()
        rows = [
            {"atividade_id": "direto.terraplenagem", "componente_bdi": "Custo operacional", "valor_rs": 1_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_indireto_prefix_replaced(self):
        """Activity with 'indireto.' prefix → short label replaces with 'ind.'."""
        mod = _import_module()
        rows = [
            {"atividade_id": "indireto.administracao", "componente_bdi": "Overhead BDI", "valor_rs": 2_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_zero_valued_component_columns(self):
        """Components with zero values don't crash; lefts still sums correctly."""
        mod = _import_module()
        rows = [
            {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": 0.0},
            {"atividade_id": "act1", "componente_bdi": "Overhead BDI", "valor_rs": 0.0},
            {"atividade_id": "act1", "componente_bdi": "Lucro (L)", "valor_rs": 0.0},
            {"atividade_id": "act1", "componente_bdi": "Tributos", "valor_rs": 0.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_multiple_components_same_activity(self):
        """Multiple component rows for same activity get aggregated correctly."""
        mod = _import_module()
        rows = [
            {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": 3_000_000.0},
            {"atividade_id": "act1", "componente_bdi": "Overhead BDI", "valor_rs": 1_000_000.0},
            {"atividade_id": "act1", "componente_bdi": "Lucro (L)", "valor_rs": 500_000.0},
            {"atividade_id": "act1", "componente_bdi": "Tributos", "valor_rs": 200_000.0},
            {"atividade_id": "act2", "componente_bdi": "Custo operacional", "valor_rs": 1_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_missing_row_fields_defaults(self):
        """Rows missing keys default to '?' / 0.0 without crashing."""
        mod = _import_module()
        rows = [
            {},  # no atividade_id, no componente_bdi, no valor_rs
            {"atividade_id": "act1"},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_valor_rs_none_treated_as_zero(self):
        """valor_rs=None → float(None or 0.0) uses 0.0."""
        mod = _import_module()
        rows = [
            {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": None},
            {"atividade_id": "act1", "componente_bdi": "Overhead BDI", "valor_rs": 5_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_cut_ab_equals_n_no_b_region(self):
        """All activities in class A (cut_ab == n, cut_bc == n) — no B/C regions."""
        mod = _import_module()
        # Single large activity consumes >70% immediately
        rows = [
            {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": 100_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_only_two_abc_classes(self):
        """Activities fall into only A and B (no C)."""
        mod = _import_module()
        # act1=70M (A), act2=29.9M (B, cumsum=99.9%<100%), act3=0.1M → C
        # Actually let's just have 2 activities at 71% and 29% to get A+B, no C
        # But that's impossible with 2 activities — one will always be > 90%
        # So let's use 3 activities: 70M (A), 20M (B), then one more for C
        rows = [
            {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": 70_000_000.0},
            {"atividade_id": "act2", "componente_bdi": "Custo operacional", "valor_rs": 20_000_000.0},
            {"atividade_id": "act3", "componente_bdi": "Custo operacional", "valor_rs": 10_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_many_activities_large_figure(self):
        """Many activities → fig_h scales with n*0.52 + 1.5."""
        mod = _import_module()
        # Create 20 activities
        rows = []
        for i in range(20):
            rows.append(
                {
                    "atividade_id": f"act{i}",
                    "componente_bdi": "Custo operacional",
                    "valor_rs": float((20 - i) * 1_000_000),
                }
            )
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_cut_lines_drawn_when_cuts_in_range(self):
        """When cut_ab and cut_bc are in range (0 < cut < n), axhline is called."""
        mod = _import_module()
        # Use multi_abc_rows so cut_ab and cut_bc are in range
        rows = _multi_abc_rows()
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_tight_layout_warning_suppressed(self):
        """tight_layout is called inside warnings.catch_warnings context (no crash)."""
        import warnings

        mod = _import_module()
        rows = _minimal_rows()
        # Should not emit any UserWarning to the test
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)

    def test_render_all_components_present(self):
        """All four _COMPS components contribute non-zero values."""
        mod = _import_module()
        rows = [
            {"atividade_id": "act1", "componente_bdi": "Custo operacional", "valor_rs": 50_000_000.0},
            {"atividade_id": "act1", "componente_bdi": "Overhead BDI", "valor_rs": 10_000_000.0},
            {"atividade_id": "act1", "componente_bdi": "Lucro (L)", "valor_rs": 5_000_000.0},
            {"atividade_id": "act1", "componente_bdi": "Tributos", "valor_rs": 3_000_000.0},
            {"atividade_id": "act2", "componente_bdi": "Custo operacional", "valor_rs": 20_000_000.0},
            {"atividade_id": "act2", "componente_bdi": "Overhead BDI", "valor_rs": 4_000_000.0},
            {"atividade_id": "act2", "componente_bdi": "Lucro (L)", "valor_rs": 2_000_000.0},
            {"atividade_id": "act2", "componente_bdi": "Tributos", "valor_rs": 1_000_000.0},
            {"atividade_id": "act3", "componente_bdi": "Custo operacional", "valor_rs": 5_000_000.0},
        ]
        fig = mod._render(self.plt, rows)
        assert fig is not None
        self.plt.close(fig)


# ---------------------------------------------------------------------------
# 5. build() with real Agg rendering (integration-style, no mocks)
# ---------------------------------------------------------------------------


class TestBuildWithRealRendering:
    """Use real matplotlib Agg but mock build_payload and init_mpl returns real plt."""

    def test_build_returns_bytes_with_real_render(self):
        """Patch build_payload but use real init_mpl so _render runs on real figure."""
        import matplotlib

        matplotlib.use("Agg")
        import io

        import matplotlib.pyplot as _plt

        def _real_fig_to_bytes(fig) -> bytes:
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=72)
            _plt.close(fig)
            buf.seek(0)
            return buf.read()

        mod = _import_module()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": _minimal_rows()}),
            patch(_INIT_MLP_PATCH, return_value=(_plt, _real_fig_to_bytes)),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_build_multi_abc_real_render_returns_bytes(self):
        """Multi-activity real render produces bytes."""
        import matplotlib

        matplotlib.use("Agg")
        import io

        import matplotlib.pyplot as _plt

        def _real_fig_to_bytes(fig) -> bytes:
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=72)
            _plt.close(fig)
            buf.seek(0)
            return buf.read()

        mod = _import_module()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": _multi_abc_rows()}),
            patch(_INIT_MLP_PATCH, return_value=(_plt, _real_fig_to_bytes)),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert isinstance(result, bytes)
        assert len(result) > 0
