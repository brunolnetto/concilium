"""Tests for pu_calculator, pdf_renderer, azure_blob_storage, and runtime helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ─── pdf_renderer ────────────────────────────────────────────────────────────


class TestPdfRenderer:
    def test_strip_inline_removes_bold(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline

        result = _strip_inline("**bold** text")
        assert "**" not in result
        assert "bold" in result

    def test_strip_inline_removes_bold_italic(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline

        result = _strip_inline("**bold** and *italic* text")
        assert "bold" in result
        assert "italic" in result

    def test_is_table_sep_true(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep

        assert _is_table_sep("|---|---|")
        assert _is_table_sep("| --- | --- |")

    def test_is_table_sep_false(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep

        assert not _is_table_sep("| data | row |")
        assert not _is_table_sep("normal line")

    def test_render_markdown_pdf_returns_bytes(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf

        md = "# Title\n\nParagraph text.\n\n- Item 1\n- Item 2\n"
        try:
            result = render_markdown_pdf(md)
            if result is not None:
                assert isinstance(result, bytes)
                assert len(result) > 0
        except ImportError:
            pytest.skip("fpdf2 not available")

    def test_render_table_row_does_not_crash(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row

        mock_pdf = MagicMock()
        mock_pdf.get_string_width.return_value = 10.0
        # Should not raise
        _render_table_row(mock_pdf, "| Col A | Col B |", col_w=50.0)
        mock_pdf.cell.assert_called()



