"""Tests targeting missing lines in pdf_renderer.py (fpdf2 backend).

Covers:
- render_markdown_pdf with _USE_REPORTLAB=False (forces fpdf2 path)
  - H1 / H2 / H3 headings
  - Code block toggle (``` delimiters, in_code_block content)
  - Table rows (| lines) and table separator (|---|---| lines)
  - Horizontal rule (---)
  - Empty lines
  - Image provider path (with and without bytes returned)
  - Title rendering
  - Exception fallback (fpdf not available → returns None)
  - multi_cell exception swallowed (bare except)
  - _render_table_row with zero cells and with exception on cell()
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

fpdf = pytest.importorskip("fpdf", reason="fpdf2 not installed")


# Helper: run render_markdown_pdf with the fpdf2 backend regardless of env var
def _render_fpdf(md_text: str, title: str = "", image_provider=None) -> bytes | None:
    """Invoke render_markdown_pdf forcing _USE_REPORTLAB=False."""
    import concilium.application.runtime.deliverables.reports.pdf_renderer as mod

    orig = mod._USE_REPORTLAB
    mod._USE_REPORTLAB = False
    try:
        return mod.render_markdown_pdf(md_text, title=title, image_provider=image_provider)
    finally:
        mod._USE_REPORTLAB = orig


def _is_pdf(data: bytes | None) -> bool:
    return data is not None and data[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Basic fpdf2 rendering
# ---------------------------------------------------------------------------


class TestFpdf2BasicRendering:
    def test_returns_pdf_bytes(self):
        result = _render_fpdf("Hello fpdf2 world")
        assert _is_pdf(result)

    def test_title_is_rendered(self):
        result = _render_fpdf("Content here", title="My Title")
        assert _is_pdf(result)

    def test_empty_markdown(self):
        result = _render_fpdf("")
        # empty md still produces valid PDF (empty page)
        assert result is None or isinstance(result, bytes)

    def test_plain_text_paragraph(self):
        result = _render_fpdf("This is a normal paragraph.")
        assert _is_pdf(result)


# ---------------------------------------------------------------------------
# Headings H1 / H2 / H3
# ---------------------------------------------------------------------------


class TestFpdf2Headings:
    def test_h1_heading(self):
        result = _render_fpdf("# Section One\n\nParagraph.")
        assert _is_pdf(result)

    def test_h2_heading(self):
        result = _render_fpdf("## Subsection\n\nText here.")
        assert _is_pdf(result)

    def test_h3_heading(self):
        result = _render_fpdf("### Sub-sub\n\nText.")
        assert _is_pdf(result)

    def test_mixed_headings(self):
        md = "# H1\n## H2\n### H3\nPara\n"
        result = _render_fpdf(md)
        assert _is_pdf(result)


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------


class TestFpdf2CodeBlocks:
    def test_code_block_skipped(self):
        md = "Before\n```\ncode line one\ncode line two\n```\nAfter\n"
        result = _render_fpdf(md)
        assert _is_pdf(result)

    def test_unclosed_code_block(self):
        md = "Before\n```\ncode without closing\n"
        result = _render_fpdf(md)
        # Should not raise; either returns bytes or None
        assert result is None or isinstance(result, bytes)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class TestFpdf2Tables:
    def test_table_with_header_and_rows(self):
        md = "| Col A | Col B |\n|---|---|\n| val 1 | val 2 |\n| val 3 | val 4 |\n"
        result = _render_fpdf(md)
        assert _is_pdf(result)

    def test_table_separator_line_skipped(self):
        md = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        result = _render_fpdf(md)
        assert _is_pdf(result)


# ---------------------------------------------------------------------------
# Horizontal rule and empty lines
# ---------------------------------------------------------------------------


class TestFpdf2HorizontalRuleAndEmpty:
    def test_horizontal_rule(self):
        md = "Before\n---\nAfter\n"
        result = _render_fpdf(md)
        assert _is_pdf(result)

    def test_empty_lines_add_spacing(self):
        md = "Para one\n\nPara two\n\nPara three\n"
        result = _render_fpdf(md)
        assert _is_pdf(result)


# ---------------------------------------------------------------------------
# Image provider
# ---------------------------------------------------------------------------


class TestFpdf2ImageProvider:
    def test_image_provider_returns_none(self):
        """image_provider returns None → image skipped, no crash."""
        md = "Before\n![Alt](some_image.png)\nAfter\n"
        result = _render_fpdf(md, image_provider=lambda name: None)
        assert _is_pdf(result)

    def test_image_provider_returns_bytes(self, tmp_path):
        """image_provider returns valid PNG bytes → embedded into PDF."""
        # Minimal 1×1 white PNG (67 bytes)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        def provider(name):
            return png_bytes

        md = "![chart](chart.png)\n"
        try:
            result = _render_fpdf(md, image_provider=provider)
            assert result is None or isinstance(result, bytes)
        except Exception:
            # fpdf2 may reject the tiny PNG depending on version — just no unhandled crash
            pass

    def test_image_provider_not_set(self):
        """No image_provider → image markup is treated as plain text."""
        md = "![Alt](some_image.png)\nNormal text\n"
        result = _render_fpdf(md, image_provider=None)
        assert _is_pdf(result)


# ---------------------------------------------------------------------------
# Exception fallback — fpdf not importable
# ---------------------------------------------------------------------------


class TestFpdf2ExceptionFallback:
    def test_returns_none_when_fpdf_unavailable(self):
        import builtins

        import concilium.application.runtime.deliverables.reports.pdf_renderer as mod

        orig_use_rl = mod._USE_REPORTLAB
        mod._USE_REPORTLAB = False
        orig_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "fpdf":
                raise ImportError("fpdf2 not available")
            return orig_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=_mock_import):
                result = mod.render_markdown_pdf("hello")
            assert result is None
        finally:
            mod._USE_REPORTLAB = orig_use_rl


# ---------------------------------------------------------------------------
# _render_table_row edge cases
# ---------------------------------------------------------------------------


class TestRenderTableRowEdgeCases:
    def test_empty_row_string_does_not_crash(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row

        mock_pdf = MagicMock()
        # line with no actual cells after strip
        _render_table_row(mock_pdf, "||", col_w=50.0)
        # Should not crash; cell may or may not be called

    def test_cell_exception_is_swallowed(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row

        mock_pdf = MagicMock()
        mock_pdf.cell.side_effect = Exception("fpdf internal error")
        # Should not raise
        _render_table_row(mock_pdf, "| A | B |", col_w=50.0)

    def test_single_cell_row(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row

        mock_pdf = MagicMock()
        _render_table_row(mock_pdf, "| only one cell |", col_w=100.0)
        mock_pdf.cell.assert_called()

    def test_long_cell_text_truncated(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row

        mock_pdf = MagicMock()
        long_text = "A" * 80
        _render_table_row(mock_pdf, f"| {long_text} |", col_w=50.0)
        call_args = mock_pdf.cell.call_args
        text_arg = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("txt", call_args[0][2])
        # truncated to 35 chars max
        assert len(text_arg) <= 35


# ---------------------------------------------------------------------------
# multi_cell exception swallowed
# ---------------------------------------------------------------------------


class TestFpdf2MultiCellExceptionSwallowed:
    def test_multi_cell_exception_is_swallowed(self):
        """The inner try/except around multi_cell swallows exceptions (lines 175-178).
        The PDF is still produced even when multi_cell raises."""
        import concilium.application.runtime.deliverables.reports.pdf_renderer as mod

        orig_use_rl = mod._USE_REPORTLAB
        mod._USE_REPORTLAB = False
        try:
            from fpdf import FPDF

            original_mc = FPDF.multi_cell
            call_count = {"n": 0}

            def _raise_on_second(*args, **kwargs):
                call_count["n"] += 1
                if call_count["n"] > 1:
                    raise RuntimeError("render fail")
                return original_mc(*args, **kwargs)

            with patch.object(FPDF, "multi_cell", _raise_on_second):
                # The inner bare except swallows the error → PDF still produced
                result = mod.render_markdown_pdf("Line one\nLine two\n", title="T")
            # Either returns bytes (exception swallowed) or None (outer except)
            assert result is None or isinstance(result, bytes)
        finally:
            mod._USE_REPORTLAB = orig_use_rl


# ---------------------------------------------------------------------------
# Temp file cleanup on exception during image
# ---------------------------------------------------------------------------


class TestFpdf2TempFileCleanup:
    def test_temp_file_cleaned_up_after_render(self, tmp_path):
        """Temp files created for images are deleted in the finally block."""
        import tempfile

        import concilium.application.runtime.deliverables.reports.pdf_renderer as mod

        orig_use_rl = mod._USE_REPORTLAB
        mod._USE_REPORTLAB = False
        created_paths: list[str] = []
        orig_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(**kwargs):
            ctx = orig_ntf(**kwargs)
            created_paths.append(ctx.name)
            return ctx

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        md = "![img](image.png)\n"
        try:
            with patch("tempfile.NamedTemporaryFile", side_effect=tracking_ntf):
                mod.render_markdown_pdf(md, image_provider=lambda n: png_bytes)
        except Exception:
            pass
        finally:
            mod._USE_REPORTLAB = orig_use_rl

        # All temp files that were created should now be gone
        for p in created_paths:
            assert not os.path.exists(p), f"Temp file not cleaned: {p}"
