"""Tests for temporal categorized cube visualizations (direct and indirect)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBuildDiretoTemporalCategoria:
    _MODULE = "concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria"
    _INIT_MPL = _MODULE + ".init_mpl"
    _PAYLOAD = _MODULE + ".build_payload"
    _RENDER = _MODULE + ".render_stacked_bar"

    def test_returns_none_when_payload_raises(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria import build

        with patch(self._PAYLOAD, side_effect=Exception("boom")):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_rows_empty(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria import build

        with patch(self._PAYLOAD, return_value={"rows": [], "columns": []}):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_matplotlib_unavailable(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria import build

        payload = {"rows": [{"periodo": "2026-08", "categoria_direto": "MAO_OBRA", "valor_rs": 1000.0}], "columns": []}
        with patch(self._PAYLOAD, return_value=payload), patch(self._INIT_MPL, side_effect=ImportError):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_render_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria import build

        payload = {"rows": [{"periodo": "2026-08", "categoria_direto": "MAO_OBRA", "valor_rs": 1000.0}], "columns": []}
        mock_plt = MagicMock()
        with (
            patch(self._PAYLOAD, return_value=payload),
            patch(self._INIT_MPL, return_value=(mock_plt, lambda fig: b"PNG_BYTES")),
            patch(self._RENDER, return_value=None),
        ):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_render_raises(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria import build

        payload = {"rows": [{"periodo": "2026-08", "categoria_direto": "MAO_OBRA", "valor_rs": 1000.0}], "columns": []}
        mock_plt = MagicMock()
        with (
            patch(self._PAYLOAD, return_value=payload),
            patch(self._INIT_MPL, return_value=(mock_plt, lambda fig: b"PNG_BYTES")),
            patch(self._RENDER, side_effect=RuntimeError("render failed")),
        ):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_bytes_for_valid_payload(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria import build

        payload = {
            "rows": [
                {"periodo": "2026-08", "categoria_direto": "MAO_OBRA", "valor_rs": 1000.0},
                {"periodo": "2026-08", "categoria_direto": "EQUIP", "valor_rs": 2000.0},
            ],
            "columns": [
                {"id": "periodo", "role": "x"},
                {"id": "categoria_direto", "role": "series"},
                {"id": "valor_rs", "role": "value"},
            ],
            "unit_type": "currency_brl",
        }
        mock_plt = MagicMock()
        mock_fig = MagicMock()

        with (
            patch(self._PAYLOAD, return_value=payload),
            patch(self._INIT_MPL, return_value=(mock_plt, lambda fig: b"PNG_BYTES")),
            patch(self._RENDER, return_value=mock_fig),
        ):
            assert build(MagicMock(), MagicMock()) == b"PNG_BYTES"


class TestBuildIndiretoTemporalCategoria:
    _MODULE = "concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria"
    _INIT_MPL = _MODULE + ".init_mpl"
    _PAYLOAD = _MODULE + ".build_payload"
    _RENDER = _MODULE + ".render_stacked_bar"

    def test_returns_none_when_payload_raises(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria import build

        with patch(self._PAYLOAD, side_effect=Exception("boom")):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_rows_empty(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria import build

        with patch(self._PAYLOAD, return_value={"rows": [], "columns": []}):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_matplotlib_unavailable(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria import build

        payload = {"rows": [{"periodo": "2026-08", "categoria_indireto": "ADM", "valor_rs": 1000.0}], "columns": []}
        with patch(self._PAYLOAD, return_value=payload), patch(self._INIT_MPL, side_effect=ImportError):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_render_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria import build

        payload = {"rows": [{"periodo": "2026-08", "categoria_indireto": "ADM", "valor_rs": 1000.0}], "columns": []}
        mock_plt = MagicMock()
        with (
            patch(self._PAYLOAD, return_value=payload),
            patch(self._INIT_MPL, return_value=(mock_plt, lambda fig: b"PNG_BYTES")),
            patch(self._RENDER, return_value=None),
        ):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_none_when_render_raises(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria import build

        payload = {"rows": [{"periodo": "2026-08", "categoria_indireto": "ADM", "valor_rs": 1000.0}], "columns": []}
        mock_plt = MagicMock()
        with (
            patch(self._PAYLOAD, return_value=payload),
            patch(self._INIT_MPL, return_value=(mock_plt, lambda fig: b"PNG_BYTES")),
            patch(self._RENDER, side_effect=RuntimeError("render failed")),
        ):
            assert build(MagicMock(), MagicMock()) is None

    def test_returns_bytes_for_valid_payload(self):
        from concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria import build

        payload = {
            "rows": [
                {"periodo": "2026-08", "categoria_indireto": "ADM", "valor_rs": 1000.0},
                {"periodo": "2026-08", "categoria_indireto": "MOB", "valor_rs": 500.0},
            ],
            "columns": [
                {"id": "periodo", "role": "x"},
                {"id": "categoria_indireto", "role": "series"},
                {"id": "valor_rs", "role": "value"},
            ],
            "unit_type": "currency_brl",
        }
        mock_plt = MagicMock()
        mock_fig = MagicMock()

        with (
            patch(self._PAYLOAD, return_value=payload),
            patch(self._INIT_MPL, return_value=(mock_plt, lambda fig: b"PNG_BYTES")),
            patch(self._RENDER, return_value=mock_fig),
        ):
            assert build(MagicMock(), MagicMock()) == b"PNG_BYTES"
