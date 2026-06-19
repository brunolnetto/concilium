"""Tests for area_tempo_componente.py — Composição do Preço por Período (stacked area).

Covers:
- build_payload raises → returns None
- empty rows → returns None
- happy path with unit_type == "currency_brl" → use_millions=True, returns bytes
- happy path with different unit_type → use_millions=False
- render_stacked_area returns None → build returns None
- render_stacked_area raises → matplotlib cleanup attempted, returns None
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.cube.area_tempo_componente"
_BUILD_PAYLOAD_PATCH = f"{_MOD}.build_payload"
_INIT_MPL_PATCH = f"{_MOD}.init_mpl"
_RENDER_PATCH = f"{_MOD}.render_stacked_area"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_module():
    import importlib

    return importlib.import_module(_MOD)


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _make_init_mpl_mock():
    """Return a patch for init_mpl that yields a dummy plt stub and fig_to_bytes."""
    mock_plt = MagicMock()
    return patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub))


def _minimal_payload(unit_type: str = "currency_brl") -> dict:
    return {
        "rows": [
            {"mes": "2024-01", "componente": "Custo operacional", "valor_rs": 1_000_000.0},
        ],
        "columns": ["Custo operacional"],
        "unit_type": unit_type,
    }


# ---------------------------------------------------------------------------
# 1. build() early-return paths
# ---------------------------------------------------------------------------


class TestBuildEarlyReturns:
    def test_build_payload_raises_returns_none(self):
        """build_payload raises → build() must return None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, side_effect=RuntimeError("no cubo")):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_empty_rows_returns_none(self):
        """build_payload returns empty rows → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": [], "columns": [], "unit_type": "currency_brl"}):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_none_rows_returns_none(self):
        """build_payload returns rows=None → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={"rows": None, "columns": [], "unit_type": "currency_brl"}):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_missing_rows_key_returns_none(self):
        """build_payload returns dict without 'rows' key → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={}):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# 2. build() happy path — unit_type currency_brl → use_millions=True
# ---------------------------------------------------------------------------


class TestBuildHappyPathCurrencyBrl:
    def test_returns_bytes(self):
        """unit_type == 'currency_brl' → render_stacked_area called with use_millions=True."""
        mod = _import_module()
        mock_fig = MagicMock()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"PNG"
        # Verify use_millions=True was passed
        _args, _kwargs = mock_render.call_args
        # use_millions is the 5th positional arg (index 4) or a kwarg
        use_millions = _kwargs.get("use_millions", _args[4] if len(_args) > 4 else None)
        assert use_millions is True

    def test_render_stacked_area_called_with_correct_title(self):
        """render_stacked_area receives the expected title string."""
        mod = _import_module()
        mock_fig = MagicMock()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            mod.build(MagicMock(), MagicMock())

        _args, _kwargs = mock_render.call_args
        # title is 4th positional arg (index 3)
        title = _args[3] if len(_args) > 3 else _kwargs.get("title")
        assert title is not None
        assert isinstance(title, str)


# ---------------------------------------------------------------------------
# 3. build() happy path — non-currency unit_type → use_millions=False
# ---------------------------------------------------------------------------


class TestBuildHappyPathOtherUnit:
    def test_use_millions_false_for_non_currency_unit(self):
        """unit_type != 'currency_brl' → render_stacked_area called with use_millions=False."""
        mod = _import_module()
        mock_fig = MagicMock()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("unit_count")),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"PNG"
        _args, _kwargs = mock_render.call_args
        use_millions = _kwargs.get("use_millions", _args[4] if len(_args) > 4 else None)
        assert use_millions is False

    def test_missing_unit_type_key_defaults_to_false(self):
        """Payload without 'unit_type' key → use_millions=False."""
        mod = _import_module()
        mock_fig = MagicMock()
        payload = {"rows": [{"mes": "2024-01", "componente": "X", "valor_rs": 100.0}], "columns": ["X"]}
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"PNG"
        _args, _kwargs = mock_render.call_args
        use_millions = _kwargs.get("use_millions", _args[4] if len(_args) > 4 else None)
        assert use_millions is False


# ---------------------------------------------------------------------------
# 4. render_stacked_area returns None → build returns None
# ---------------------------------------------------------------------------


class TestRenderReturnsNone:
    def test_render_none_returns_none(self):
        """render_stacked_area returning None → build() returns None."""
        mod = _import_module()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, return_value=None),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# 5. render_stacked_area raises → cleanup attempted, returns None
# ---------------------------------------------------------------------------


class TestRenderRaises:
    def test_render_raises_returns_none(self):
        """render_stacked_area raises → except block runs, returns None."""
        mod = _import_module()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, side_effect=RuntimeError("render exploded")),
            patch("matplotlib.pyplot.close") as mock_close,
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_render_raises_matplotlib_close_called(self):
        """When render raises, matplotlib.pyplot.close('all') is attempted."""
        mod = _import_module()
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as real_plt

        closed = []

        original_close = real_plt.close

        def tracking_close(arg=None):
            closed.append(arg)

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, side_effect=OSError("disk full")),
            patch("matplotlib.pyplot.close", side_effect=tracking_close),
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None
        assert "all" in closed

    def test_render_raises_matplotlib_close_also_raises(self):
        """Even if matplotlib.pyplot.close raises, build() still returns None."""
        mod = _import_module()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            _make_init_mpl_mock(),
            patch(_RENDER_PATCH, side_effect=RuntimeError("render fail")),
            patch("matplotlib.pyplot.close", side_effect=ImportError("no mpl")),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# 6. init_mpl raises → exception path returns None
# ---------------------------------------------------------------------------


class TestInitMplRaises:
    def test_init_mpl_raises_returns_none(self):
        """init_mpl raising ImportError → build() returns None via except block."""
        mod = _import_module()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            patch(_INIT_MPL_PATCH, side_effect=ImportError("no matplotlib")),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# 7. fig_to_bytes raises → exception path returns None
# ---------------------------------------------------------------------------


class TestFigToBytesRaises:
    def test_fig_to_bytes_raises_returns_none(self):
        """fig_to_bytes raising → build() returns None via except block."""

        def bad_fig_to_bytes(fig):
            raise OSError("disk full")

        mod = _import_module()
        mock_plt = MagicMock()
        mock_fig = MagicMock()
        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=_minimal_payload("currency_brl")),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, bad_fig_to_bytes)),
            patch(_RENDER_PATCH, return_value=mock_fig),
        ):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None
