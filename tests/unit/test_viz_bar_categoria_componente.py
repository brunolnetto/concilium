"""Tests for bar_categoria_componente.py — Composição de Custo por Categoria.

Covers all seven specified scenarios:
1. build_payload raises an exception → returns None (first try/except path).
2. build_payload returns a payload with no rows (rows=[]) → returns None.
3. build_payload returns a payload with rows=None → returns None.
4. Happy path: payload has rows, unit_type="currency_brl" → use_millions=True,
   render_stacked_bar receives the right args, fig_to_bytes is called and its
   return value (bytes) is returned.
5. Happy path: unit_type is something else → use_millions=False.
6. render_stacked_bar returns None → build returns None.
7. render_stacked_bar raises an exception (or init_mpl raises) → returns None,
   matplotlib cleanup attempted via matplotlib.pyplot.close("all").
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Module paths
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.cube.bar_categoria_componente"
_BUILD_PAYLOAD_PATCH = f"{_MOD}.build_payload"
_INIT_MPL_PATCH = f"{_MOD}.init_mpl"
_RENDER_PATCH = f"{_MOD}.render_stacked_bar"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_module():
    import importlib

    return importlib.import_module(_MOD)


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG_BYTES"


def _make_mock_fig():
    return MagicMock(name="figure")


def _make_payload(rows, columns=None, unit_type=None):
    payload = {"rows": rows, "columns": columns or []}
    if unit_type is not None:
        payload["unit_type"] = unit_type
    return payload


def _minimal_rows():
    return [
        {"categoria": "Custo operacional", "mes": "2024-01", "valor_rs": 1_000_000.0},
    ]


# ---------------------------------------------------------------------------
# Scenario 1: build_payload raises → returns None
# ---------------------------------------------------------------------------


class TestBuildPayloadRaises:
    def test_build_payload_raises_returns_none(self):
        """Scenario 1: build_payload raises RuntimeError → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, side_effect=RuntimeError("cubo not ready")):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_raises_value_error_returns_none(self):
        """Scenario 1: build_payload raises ValueError → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, side_effect=ValueError("bad input")):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_build_payload_raises_exception_returns_none(self):
        """Scenario 1: build_payload raises generic Exception → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, side_effect=Exception("generic")):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# Scenario 2: build_payload returns rows=[] → returns None
# ---------------------------------------------------------------------------


class TestEmptyRows:
    def test_empty_rows_returns_none(self):
        """Scenario 2: payload has rows=[] → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value=_make_payload([])):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_empty_rows_does_not_call_init_mpl(self):
        """Scenario 2: with empty rows, init_mpl is never called."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value=_make_payload([])), patch(_INIT_MPL_PATCH) as mock_init:
            mod.build(MagicMock(), MagicMock())
        mock_init.assert_not_called()


# ---------------------------------------------------------------------------
# Scenario 3: build_payload returns rows=None → returns None
# ---------------------------------------------------------------------------


class TestNoneRows:
    def test_none_rows_returns_none(self):
        """Scenario 3: payload has rows=None → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value=_make_payload(None)):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None

    def test_none_rows_does_not_call_init_mpl(self):
        """Scenario 3: with rows=None, init_mpl is never called."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value=_make_payload(None)), patch(_INIT_MPL_PATCH) as mock_init:
            mod.build(MagicMock(), MagicMock())
        mock_init.assert_not_called()

    def test_missing_rows_key_returns_none(self):
        """Scenario 3 variant: payload has no 'rows' key → build() returns None."""
        mod = _import_module()
        with patch(_BUILD_PAYLOAD_PATCH, return_value={}):
            result = mod.build(MagicMock(), MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# Scenario 4: Happy path with unit_type="currency_brl" → use_millions=True
# ---------------------------------------------------------------------------


class TestHappyPathCurrencyBrl:
    def test_returns_bytes_currency_brl(self):
        """Scenario 4: unit_type=currency_brl → use_millions=True, returns bytes."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")

        payload = _make_payload(_minimal_rows(), columns=["col1"], unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"PNG_BYTES"

    def test_use_millions_true_when_currency_brl(self):
        """Scenario 4: render_stacked_bar is called with use_millions=True."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")
        columns = ["Custo operacional", "BDI"]

        payload = _make_payload(_minimal_rows(), columns=columns, unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            mod.build(MagicMock(), MagicMock())

        mock_render.assert_called_once()
        _, kwargs = mock_render.call_args
        # use_millions is passed as positional arg index 3 or keyword
        call_args = mock_render.call_args
        # render_stacked_bar(plt, rows, columns, title, use_millions, ...)
        positional = call_args.args
        # use_millions is 5th positional arg (index 4)
        if len(positional) >= 5:
            assert positional[4] is True
        else:
            assert call_args.kwargs.get("use_millions") is True

    def test_render_receives_correct_rows_and_columns(self):
        """Scenario 4: render_stacked_bar receives rows and columns from payload."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")
        rows = _minimal_rows()
        columns = ["Custo operacional"]

        payload = _make_payload(rows, columns=columns, unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            mod.build(MagicMock(), MagicMock())

        call_args = mock_render.call_args
        positional = call_args.args
        # render_stacked_bar(plt, rows, columns, title, use_millions, ...)
        assert positional[1] is rows
        assert positional[2] is columns

    def test_fig_to_bytes_called_with_figure(self):
        """Scenario 4: fig_to_bytes is called with the figure returned by render_stacked_bar."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")
        captured_figs = []

        def capturing_fig_to_bytes(fig) -> bytes:
            captured_figs.append(fig)
            return b"CAPTURED"

        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, capturing_fig_to_bytes)),
            patch(_RENDER_PATCH, return_value=mock_fig),
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"CAPTURED"
        assert captured_figs == [mock_fig]


# ---------------------------------------------------------------------------
# Scenario 5: Happy path with other unit_type → use_millions=False
# ---------------------------------------------------------------------------


class TestHappyPathOtherUnitType:
    def test_other_unit_type_use_millions_false(self):
        """Scenario 5: unit_type != currency_brl → use_millions=False."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")

        payload = _make_payload(_minimal_rows(), unit_type="percent")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"PNG_BYTES"
        call_args = mock_render.call_args
        positional = call_args.args
        if len(positional) >= 5:
            assert positional[4] is False
        else:
            assert call_args.kwargs.get("use_millions") is False

    def test_no_unit_type_key_use_millions_false(self):
        """Scenario 5: payload has no unit_type key → use_millions=False."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")

        payload = {"rows": _minimal_rows(), "columns": []}

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"PNG_BYTES"
        call_args = mock_render.call_args
        positional = call_args.args
        if len(positional) >= 5:
            assert positional[4] is False
        else:
            assert call_args.kwargs.get("use_millions") is False

    def test_unit_type_none_use_millions_false(self):
        """Scenario 5: unit_type=None → use_millions=False."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")

        payload = {"rows": _minimal_rows(), "columns": [], "unit_type": None}

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, return_value=mock_fig) as mock_render,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result == b"PNG_BYTES"
        call_args = mock_render.call_args
        positional = call_args.args
        if len(positional) >= 5:
            assert positional[4] is False
        else:
            assert call_args.kwargs.get("use_millions") is False


# ---------------------------------------------------------------------------
# Scenario 6: render_stacked_bar returns None → build returns None
# ---------------------------------------------------------------------------


class TestRenderReturnsNone:
    def test_render_none_returns_none(self):
        """Scenario 6: render_stacked_bar returns None → build() returns None."""
        mod = _import_module()
        mock_plt = MagicMock(name="plt")
        fig_to_bytes_calls = []

        def tracking_fig_to_bytes(fig) -> bytes:
            fig_to_bytes_calls.append(fig)
            return b"SHOULD_NOT_BE_CALLED"

        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, tracking_fig_to_bytes)),
            patch(_RENDER_PATCH, return_value=None),
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None
        # fig_to_bytes should NOT be called when fig is None
        assert fig_to_bytes_calls == []


# ---------------------------------------------------------------------------
# Scenario 7: render_stacked_bar / init_mpl raises → returns None, cleanup attempted
# ---------------------------------------------------------------------------


class TestExceptionInPlottingBlock:
    def test_render_raises_returns_none(self):
        """Scenario 7: render_stacked_bar raises → build() returns None."""
        mod = _import_module()
        mock_plt = MagicMock(name="plt")
        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, side_effect=RuntimeError("render boom")),
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None

    def test_init_mpl_raises_returns_none(self):
        """Scenario 7: init_mpl raises → build() returns None."""
        mod = _import_module()
        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, side_effect=ImportError("no matplotlib")),
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None

    def test_render_raises_cleanup_attempted(self):
        """Scenario 7: render raises → matplotlib.pyplot.close('all') is attempted."""
        mod = _import_module()
        mock_plt = MagicMock(name="plt")
        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, side_effect=RuntimeError("render boom")),
            patch("matplotlib.pyplot.close") as mock_close,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None
        mock_close.assert_called_once_with("all")

    def test_fig_to_bytes_raises_returns_none(self):
        """Scenario 7: fig_to_bytes raises → build() returns None."""
        mod = _import_module()
        mock_fig = _make_mock_fig()
        mock_plt = MagicMock(name="plt")

        def bad_fig_to_bytes(fig):
            raise OSError("disk full")

        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, bad_fig_to_bytes)),
            patch(_RENDER_PATCH, return_value=mock_fig),
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None

    def test_render_raises_cleanup_handles_import_error(self):
        """Scenario 7: render raises, and even if matplotlib import fails in cleanup,
        build() still returns None without propagating."""
        mod = _import_module()
        mock_plt = MagicMock(name="plt")
        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, return_value=(mock_plt, _fig_to_bytes_stub)),
            patch(_RENDER_PATCH, side_effect=RuntimeError("render fail")),
            patch("matplotlib.pyplot.close", side_effect=ImportError("no mpl")),
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None

    def test_init_mpl_raises_cleanup_attempted(self):
        """Scenario 7: init_mpl raises → cleanup via matplotlib.pyplot.close('all') is tried."""
        mod = _import_module()
        payload = _make_payload(_minimal_rows(), unit_type="currency_brl")

        with (
            patch(_BUILD_PAYLOAD_PATCH, return_value=payload),
            patch(_INIT_MPL_PATCH, side_effect=RuntimeError("init fail")),
            patch("matplotlib.pyplot.close") as mock_close,
        ):
            result = mod.build(MagicMock(), MagicMock())

        assert result is None
        mock_close.assert_called_once_with("all")
