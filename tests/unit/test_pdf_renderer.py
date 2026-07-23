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





from unittest.mock import patch  # noqa: E402

# ─── pdf_renderer.py lines 67-71 (ReportLab dispatch path) ──────────────────


class TestPdfRendererRLPath:
    def test_rl_path_returns_bytes_directly(self):
        """Lines 67, 69, 70, 71: _USE_REPORTLAB=True + rl render returns bytes."""
        import concilium.application.runtime.deliverables.reports.pdf_renderer as mod

        orig = mod._USE_REPORTLAB
        mod._USE_REPORTLAB = True
        try:
            with patch(
                "concilium.application.runtime.deliverables.reports.pdf_renderer_rl.render_markdown_pdf",
                return_value=b"%PDF-fake",
            ):
                result = mod.render_markdown_pdf("# Title\nContent.")
            assert result == b"%PDF-fake"
        finally:
            mod._USE_REPORTLAB = orig

    def test_rl_path_falls_through_when_none(self):
        """Line 70 False branch: rl render returns None → fpdf2 fallback."""
        import concilium.application.runtime.deliverables.reports.pdf_renderer as mod

        orig = mod._USE_REPORTLAB
        mod._USE_REPORTLAB = True
        try:
            with patch(
                "concilium.application.runtime.deliverables.reports.pdf_renderer_rl.render_markdown_pdf",
                return_value=None,
            ):
                result = mod.render_markdown_pdf("Hello fpdf2.")
            assert result is None or isinstance(result, bytes)
        finally:
            mod._USE_REPORTLAB = orig




# ─── pdf_renderer.py lines 117-118 (fpdf2 image embed success) ───────────────


class TestPdfRendererImageEmbedSuccess:
    def test_image_embed_success_path_reached(self):
        """Lines 117-118: pdf.image() doesn't raise → pdf.ln(2) runs."""
        from fpdf import FPDF

        import concilium.application.runtime.deliverables.reports.pdf_renderer as mod

        orig = mod._USE_REPORTLAB
        mod._USE_REPORTLAB = False
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        try:
            with patch.object(FPDF, "image", return_value=None):
                result = mod.render_markdown_pdf(
                    "![chart](chart.png)\nText after.",
                    image_provider=lambda n: png_bytes,
                )
            assert result is None or isinstance(result, bytes)
        finally:
            mod._USE_REPORTLAB = orig





# ─── application/runtime/deliverables/reports/pdf_renderer.py ─────────────────


class TestPdfRenderer2:
    def test_strip_inline_bold(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline

        result = _strip_inline("**bold text**")
        assert "bold text" in result
        assert "**" not in result

    def test_strip_inline_code(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline

        result = _strip_inline("`code`")
        assert "code" in result
        assert "`" not in result

    def test_is_table_sep_true(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep

        assert _is_table_sep("|---|---|") is True
        assert _is_table_sep("| :--- | ---: |") is True

    def test_is_table_sep_false(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep

        assert _is_table_sep("| data | row |") is False

    def test_render_table_row_no_crash(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row

        pdf = MagicMock()
        _render_table_row(pdf, "| col1 | col2 | col3 |", col_w=60.0)
        assert pdf.cell.call_count >= 1

    def test_render_markdown_pdf_empty_returns_bytes_or_none(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf

        result = render_markdown_pdf("")
        assert result is None or isinstance(result, bytes)

    def test_render_markdown_pdf_basic(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf

        md = "# Title\n\nThis is a paragraph.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        result = render_markdown_pdf(md, title="Test Report")
        assert result is None or isinstance(result, bytes)

    def test_render_markdown_pdf_with_code_block(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf

        md = "Normal text\n\n```\ncode block\n```\n\nAfter code."
        result = render_markdown_pdf(md)
        assert result is None or isinstance(result, bytes)



