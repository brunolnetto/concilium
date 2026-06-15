"""Unit tests for bar_tempo_natureza.build()."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

MODULE = "concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza"
COMMON_MODULE = "concilium.application.runtime.deliverables.visualizations.cube._common"


def _make_payload(rows=None, columns=None, unit_type="currency_brl"):
    return {
        "rows": rows if rows is not None else [{"mes": "2024-01", "direto": 100, "indireto": 50}],
        "columns": columns if columns is not None else [{"id": "mes", "role": "domain"}],
        "unit_type": unit_type,
    }


def _make_fig():
    fig = MagicMock()
    return fig


def _make_fig_to_bytes(return_value=b"PNG_BYTES"):
    def fig_to_bytes(fig):
        return return_value

    return fig_to_bytes


# ---------------------------------------------------------------------------
# (1) build_payload raises → returns None
# ---------------------------------------------------------------------------
def test_build_payload_raises_returns_none():
    canonical = MagicMock()
    cubo = MagicMock()

    with patch(f"{MODULE}.build_payload", side_effect=RuntimeError("cubo error")):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        result = build(canonical, cubo)

    assert result is None


# ---------------------------------------------------------------------------
# (2a) rows is empty list → returns None
# ---------------------------------------------------------------------------
def test_empty_rows_returns_none():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = _make_payload(rows=[])

    with patch(f"{MODULE}.build_payload", return_value=payload):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        result = build(canonical, cubo)

    assert result is None


# ---------------------------------------------------------------------------
# (2b) rows key missing from payload → returns None
# ---------------------------------------------------------------------------
def test_missing_rows_key_returns_none():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = {"columns": [], "unit_type": "currency_brl"}  # no "rows" key

    with patch(f"{MODULE}.build_payload", return_value=payload):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        result = build(canonical, cubo)

    assert result is None


# ---------------------------------------------------------------------------
# (3) fig is None → returns None
# ---------------------------------------------------------------------------
def test_fig_none_returns_none():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = _make_payload()

    mock_plt = MagicMock()
    fig_to_bytes = _make_fig_to_bytes()

    with (
        patch(f"{MODULE}.build_payload", return_value=payload),
        patch(f"{MODULE}.init_mpl", return_value=(mock_plt, fig_to_bytes)),
        patch(f"{MODULE}.render_stacked_bar", return_value=None),
    ):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        result = build(canonical, cubo)

    assert result is None


# ---------------------------------------------------------------------------
# (4) Happy path with unit_type == "currency_brl" → use_millions=True, returns bytes
# ---------------------------------------------------------------------------
def test_happy_path_currency_brl_returns_bytes():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = _make_payload(unit_type="currency_brl")

    mock_plt = MagicMock()
    fig = _make_fig()
    fig_to_bytes = _make_fig_to_bytes(b"PNG_DATA")

    with (
        patch(f"{MODULE}.build_payload", return_value=payload) as mock_bp,
        patch(f"{MODULE}.init_mpl", return_value=(mock_plt, fig_to_bytes)),
        patch(f"{MODULE}.render_stacked_bar", return_value=fig) as mock_rsb,
    ):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        result = build(canonical, cubo)

    assert result == b"PNG_DATA"

    # Verify use_millions=True was passed (4th positional arg after plt, rows, columns, title)
    call_args = mock_rsb.call_args
    # use_millions is the 5th positional argument
    assert call_args.args[4] is True or call_args.kwargs.get("use_millions") is True


# ---------------------------------------------------------------------------
# (4b) Happy path with unit_type != "currency_brl" → use_millions=False, returns bytes
# ---------------------------------------------------------------------------
def test_happy_path_non_currency_returns_bytes():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = _make_payload(unit_type="count")

    mock_plt = MagicMock()
    fig = _make_fig()
    fig_to_bytes = _make_fig_to_bytes(b"PNG_COUNT")

    with (
        patch(f"{MODULE}.build_payload", return_value=payload),
        patch(f"{MODULE}.init_mpl", return_value=(mock_plt, fig_to_bytes)),
        patch(f"{MODULE}.render_stacked_bar", return_value=fig) as mock_rsb,
    ):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        result = build(canonical, cubo)

    assert result == b"PNG_COUNT"

    call_args = mock_rsb.call_args
    use_millions = call_args.args[4] if len(call_args.args) > 4 else call_args.kwargs.get("use_millions")
    assert use_millions is False


# ---------------------------------------------------------------------------
# (5) render_stacked_bar raises → returns None and closes matplotlib figures
# ---------------------------------------------------------------------------
def test_render_stacked_bar_raises_closes_mpl_and_returns_none():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = _make_payload()

    mock_plt = MagicMock()
    fig_to_bytes = _make_fig_to_bytes()

    with (
        patch(f"{MODULE}.build_payload", return_value=payload),
        patch(f"{MODULE}.init_mpl", return_value=(mock_plt, fig_to_bytes)),
        patch(f"{MODULE}.render_stacked_bar", side_effect=ValueError("render failed")),
    ):
        # Patch matplotlib.pyplot.close directly so the except-block cleanup runs fine
        import matplotlib.pyplot as _real_plt

        close_mock = MagicMock()
        original_close = _real_plt.close
        _real_plt.close = close_mock
        try:
            from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

            result = build(canonical, cubo)
        finally:
            _real_plt.close = original_close

    assert result is None
    close_mock.assert_called_once_with("all")


# ---------------------------------------------------------------------------
# (5b) render_stacked_bar raises, matplotlib also raises during close → still None
# ---------------------------------------------------------------------------
def test_render_stacked_bar_raises_mpl_close_also_raises_returns_none():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = _make_payload()

    mock_plt = MagicMock()
    fig_to_bytes = _make_fig_to_bytes()

    with (
        patch(f"{MODULE}.build_payload", return_value=payload),
        patch(f"{MODULE}.init_mpl", return_value=(mock_plt, fig_to_bytes)),
        patch(f"{MODULE}.render_stacked_bar", side_effect=ValueError("render failed")),
    ):
        import matplotlib.pyplot as _real_plt

        original_close = _real_plt.close
        _real_plt.close = MagicMock(side_effect=RuntimeError("close failed"))
        try:
            from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

            result = build(canonical, cubo)
        finally:
            _real_plt.close = original_close

    assert result is None


# ---------------------------------------------------------------------------
# (6) build_payload is called with correct face/granularity args
# ---------------------------------------------------------------------------
def test_build_payload_called_with_correct_args():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = _make_payload()

    mock_plt = MagicMock()
    fig = _make_fig()
    fig_to_bytes = _make_fig_to_bytes(b"OK")

    with (
        patch(f"{MODULE}.build_payload", return_value=payload) as mock_bp,
        patch(f"{MODULE}.init_mpl", return_value=(mock_plt, fig_to_bytes)),
        patch(f"{MODULE}.render_stacked_bar", return_value=fig),
    ):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        build(canonical, cubo)

    mock_bp.assert_called_once_with("tempo_natureza", "mes", 120, canonical, cubo)


# ---------------------------------------------------------------------------
# (7) rows is None (payload returns rows=None) → returns None
# ---------------------------------------------------------------------------
def test_rows_none_returns_none():
    canonical = MagicMock()
    cubo = MagicMock()
    payload = {"rows": None, "columns": [], "unit_type": "currency_brl"}

    with patch(f"{MODULE}.build_payload", return_value=payload):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza import build

        result = build(canonical, cubo)

    assert result is None
