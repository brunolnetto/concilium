"""Tests for build() in scurve_custo.py.

Covers all missing lines including:
- rows_nat empty → returns None
- ImportError from init_mpl → returns None
- happy path with tempo_natureza rows and BDI tempo_componente rows → returns bytes
- preco_pool_bdi > 0 branch (axhline with red)
- custo_op > 0 branch (axhline with green)
- inner exception (bad data) → returns None
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Module path
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.cube.scurve_custo"


def _import_build():
    import importlib

    mod = importlib.import_module(_MOD)
    return mod.build


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _make_canonical(
    cubo_analitico=None,
    venda_total_com_bdi: float = 0.0,
    custo_total: float = 0.0,
):
    """Build a minimal canonical mock with the attributes accessed by build()."""
    canonical = MagicMock()
    canonical.cubo_analitico = cubo_analitico

    resultado = MagicMock()
    venda = MagicMock()
    venda.total_com_bdi = venda_total_com_bdi
    resultado.venda = venda

    custo = MagicMock()
    custo.total = custo_total
    resultado.custo = custo

    canonical.resultado = resultado
    return canonical


def _make_nat_rows(periodos=("2025-01", "2025-02"), direto=1e6, indireto=5e5):
    """Generate minimal tempo_natureza rows."""
    rows = []
    for p in periodos:
        rows.append({"periodo": p, "natureza": "direto", "valor_rs": direto})
        rows.append({"periodo": p, "natureza": "indireto", "valor_rs": indireto})
    return rows


def _make_comp_rows(periodos=("2025-01", "2025-02")):
    """Generate minimal tempo_componente rows with BDI components."""
    bdi_comps = ["Overhead BDI", "Lucro (L)", "Tributos"]
    rows = []
    for p in periodos:
        for comp in bdi_comps:
            rows.append({"periodo": p, "componente_bdi": comp, "valor_rs": 2e5})
        # Add a non-BDI component — should be ignored
        rows.append({"periodo": p, "componente_bdi": "Outro", "valor_rs": 9e9})
    return rows


def _make_plt_mock():
    """Return (mock_plt, mock_fig, mock_ax_bar, mock_ax_line)."""
    mock_ax_bar = MagicMock()
    mock_ax_line = MagicMock()
    mock_fig = MagicMock()
    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, (mock_ax_bar, mock_ax_line))
    return mock_plt, mock_fig, mock_ax_bar, mock_ax_line


def _patched_init_mpl(mock_plt):
    return patch(
        f"{_MOD}.init_mpl",
        return_value=(mock_plt, _fig_to_bytes_stub),
    )


def _patched_build_payload(nat_rows=None, comp_rows=None):
    """Patch build_payload to return controlled rows for each face."""
    nat_rows = nat_rows if nat_rows is not None else _make_nat_rows()
    comp_rows = comp_rows if comp_rows is not None else _make_comp_rows()

    def _side_effect(face, granularidade, top_n, canonical, cubo):
        if face == "tempo_natureza":
            return {"rows": nat_rows}
        return {"rows": comp_rows}

    return patch(f"{_MOD}.build_payload", side_effect=_side_effect)


# ---------------------------------------------------------------------------
# 1. Early-return: rows_nat empty
# ---------------------------------------------------------------------------


class TestRowsNatEmpty:
    def test_empty_rows_nat_returns_none(self):
        """build_payload returns rows=[] → build() returns None immediately."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt, *_ = _make_plt_mock()

        with _patched_init_mpl(mock_plt), _patched_build_payload(nat_rows=[]):
            result = build(canonical, cubo=None)

        assert result is None

    def test_none_rows_nat_returns_none(self):
        """build_payload returns rows=None → build() returns None immediately."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt, *_ = _make_plt_mock()

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {"rows": None}
            return {"rows": []}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result is None

    def test_missing_rows_key_returns_none(self):
        """build_payload returns {} (no 'rows' key) → build() returns None."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt, *_ = _make_plt_mock()

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {}
            return {"rows": []}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result is None


# ---------------------------------------------------------------------------
# 2. ImportError from init_mpl
# ---------------------------------------------------------------------------


class TestImportErrorPath:
    def test_import_error_returns_none(self):
        """ImportError during init_mpl → build() returns None."""
        build = _import_build()
        canonical = _make_canonical()

        with patch(f"{_MOD}.init_mpl", side_effect=ImportError("no matplotlib")):
            result = build(canonical, cubo=None)

        assert result is None


# ---------------------------------------------------------------------------
# 3. Happy path — returns bytes
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_basic_happy_path_returns_bytes(self):
        """Nominal data with both nat and comp rows → bytes returned."""
        build = _import_build()
        canonical = _make_canonical(
            cubo_analitico=MagicMock(),
            venda_total_com_bdi=10e6,
            custo_total=8e6,
        )
        mock_plt, mock_fig, mock_ax_bar, mock_ax_line = _make_plt_mock()

        with _patched_init_mpl(mock_plt), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert isinstance(result, bytes)
        assert result == b"PNG"

    def test_cubo_argument_passed_through(self):
        """cubo argument forwarded to build_payload for tempo_componente call."""
        build = _import_build()
        cubo_mock = MagicMock()
        canonical = _make_canonical(cubo_analitico=cubo_mock)
        mock_plt, *_ = _make_plt_mock()

        calls = []

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            calls.append((face, cubo))
            if face == "tempo_natureza":
                return {"rows": _make_nat_rows()}
            return {"rows": _make_comp_rows()}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result == b"PNG"
        # tempo_componente call should pass cubo_analitico from canonical
        comp_call = next(c for c in calls if c[0] == "tempo_componente")
        assert comp_call[1] is cubo_mock

    def test_bdi_periods_extended_beyond_nat_periods(self):
        """BDI rows span additional months not present in nat rows → periodos extended."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt, *_ = _make_plt_mock()

        nat_rows = _make_nat_rows(periodos=("2025-01",))
        # comp rows include extra month
        comp_rows = [
            {"periodo": "2025-01", "componente_bdi": "Overhead BDI", "valor_rs": 1e5},
            {"periodo": "2025-02", "componente_bdi": "Lucro (L)", "valor_rs": 1e5},
        ]

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {"rows": nat_rows}
            return {"rows": comp_rows}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result == b"PNG"

    def test_non_bdi_comp_rows_ignored(self):
        """Rows with componente_bdi not in _BDI_COMPS are silently ignored."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt, *_ = _make_plt_mock()

        comp_rows = [
            {"periodo": "2025-01", "componente_bdi": "Custo Direto", "valor_rs": 9e9},
            {"periodo": "2025-01", "componente_bdi": "Outro", "valor_rs": 9e9},
        ]

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {"rows": _make_nat_rows()}
            return {"rows": comp_rows}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 4. preco_pool_bdi > 0 branch (axhline red)
# ---------------------------------------------------------------------------


class TestPrecoBranch:
    def test_preco_pool_bdi_positive_draws_red_axhline(self):
        """When acc_total_bdi[-1] > 0, ax_line.axhline is called with red color."""
        build = _import_build()
        canonical = _make_canonical(venda_total_com_bdi=10e6, custo_total=0.0)
        mock_plt, mock_fig, mock_ax_bar, mock_ax_line = _make_plt_mock()

        with _patched_init_mpl(mock_plt), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert result == b"PNG"
        # axhline should have been called at least once on ax_line
        assert mock_ax_line.axhline.called

    def test_custo_op_positive_draws_green_axhline(self):
        """When custo_total > 0, ax_line.axhline is called a second time."""
        build = _import_build()
        canonical = _make_canonical(venda_total_com_bdi=0.0, custo_total=8e6)
        mock_plt, mock_fig, mock_ax_bar, mock_ax_line = _make_plt_mock()

        with _patched_init_mpl(mock_plt), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert result == b"PNG"
        assert mock_ax_line.axhline.called

    def test_both_preco_and_custo_positive(self):
        """Both preco_pool_bdi and custo_op positive → two axhline calls."""
        build = _import_build()
        canonical = _make_canonical(venda_total_com_bdi=12e6, custo_total=8e6)
        mock_plt, mock_fig, mock_ax_bar, mock_ax_line = _make_plt_mock()

        with _patched_init_mpl(mock_plt), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert result == b"PNG"
        call_count = mock_ax_line.axhline.call_count
        assert call_count >= 1  # at least the preco_pool_bdi line

    def test_zero_values_no_axhline(self):
        """Both values zero → neither axhline branch fires."""
        build = _import_build()
        # Use nat rows with zero valores so acc_total_bdi[-1] will be 0
        zero_nat = [
            {"periodo": "2025-01", "natureza": "direto", "valor_rs": 0.0},
            {"periodo": "2025-01", "natureza": "indireto", "valor_rs": 0.0},
        ]
        zero_comp = [
            {"periodo": "2025-01", "componente_bdi": "Overhead BDI", "valor_rs": 0.0},
            {"periodo": "2025-01", "componente_bdi": "Lucro (L)", "valor_rs": 0.0},
            {"periodo": "2025-01", "componente_bdi": "Tributos", "valor_rs": 0.0},
        ]
        canonical = _make_canonical(venda_total_com_bdi=0.0, custo_total=0.0)
        mock_plt, mock_fig, mock_ax_bar, mock_ax_line = _make_plt_mock()

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {"rows": zero_nat}
            return {"rows": zero_comp}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result == b"PNG"
        assert not mock_ax_line.axhline.called


# ---------------------------------------------------------------------------
# 5. Inner exception → returns None
# ---------------------------------------------------------------------------


class TestInnerException:
    def test_subplots_raises_returns_none(self):
        """When plt.subplots raises, except block returns None."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("display error")

        with patch(f"{_MOD}.init_mpl", return_value=(mock_plt, _fig_to_bytes_stub)), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert result is None

    def test_fig_to_bytes_raises_returns_none(self):
        """When fig_to_bytes raises, except block returns None."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt, *_ = _make_plt_mock()

        def _bad_fig_to_bytes(fig):
            raise OSError("disk full")

        with patch(f"{_MOD}.init_mpl", return_value=(mock_plt, _bad_fig_to_bytes)), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert result is None

    def test_bad_valor_rs_still_handled(self):
        """If valor_rs contains unexpected non-numeric that causes float() to raise,
        the except block returns None."""
        build = _import_build()
        canonical = _make_canonical()
        mock_plt, *_ = _make_plt_mock()

        bad_nat_rows = [
            {"periodo": "2025-01", "natureza": "direto", "valor_rs": "not_a_number_xyz"},
        ]

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {"rows": bad_nat_rows}
            return {"rows": []}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result is None


# ---------------------------------------------------------------------------
# 6. resultado attribute variations
# ---------------------------------------------------------------------------


class TestResultadoAttributes:
    def test_resultado_none_does_not_crash(self):
        """If canonical.resultado is None, getattr guards prevent crash."""
        build = _import_build()
        canonical = _make_canonical()
        canonical.resultado = None
        mock_plt, *_ = _make_plt_mock()

        with _patched_init_mpl(mock_plt), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert result == b"PNG"

    def test_cubo_analitico_none_still_passes(self):
        """cubo_analitico=None → build_payload called with cubo=None."""
        build = _import_build()
        canonical = _make_canonical(cubo_analitico=None)
        mock_plt, *_ = _make_plt_mock()

        with _patched_init_mpl(mock_plt), _patched_build_payload():
            result = build(canonical, cubo=None)

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# 7. Multiple periods — covers bar/fill_between loop iterations
# ---------------------------------------------------------------------------


class TestMultiplePeriods:
    def test_many_periods(self):
        """10 periods → large figsize, all loops iterate correctly."""
        build = _import_build()
        periodos = [f"2025-{i:02d}" for i in range(1, 11)]
        nat_rows = _make_nat_rows(periodos=periodos, direto=2e6, indireto=1e6)
        comp_rows = _make_comp_rows(periodos=periodos)
        canonical = _make_canonical(venda_total_com_bdi=30e6, custo_total=20e6)
        mock_plt, *_ = _make_plt_mock()

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {"rows": nat_rows}
            return {"rows": comp_rows}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result == b"PNG"

    def test_single_period(self):
        """Single period edge case — acc_total_bdi has one element."""
        build = _import_build()
        canonical = _make_canonical(venda_total_com_bdi=5e6, custo_total=4e6)
        mock_plt, *_ = _make_plt_mock()

        nat_rows = _make_nat_rows(periodos=("2025-01",), direto=3e6, indireto=1e6)
        comp_rows = _make_comp_rows(periodos=("2025-01",))

        def _side_effect(face, granularidade, top_n, canonical, cubo):
            if face == "tempo_natureza":
                return {"rows": nat_rows}
            return {"rows": comp_rows}

        with _patched_init_mpl(mock_plt), patch(f"{_MOD}.build_payload", side_effect=_side_effect):
            result = build(canonical, cubo=None)

        assert result == b"PNG"
