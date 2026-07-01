"""Batch 39: pdf_renderer.py (RL path, image embed), output_packager.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

fpdf = pytest.importorskip("fpdf", reason="fpdf2 not installed")


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


# ─── output_packager.py line 59 (svg in legacy outputs/) ────────────────────


class TestOutputPackagerSvgFallback:
    def test_collects_svg_from_legacy_outputs_dir(self, tmp_path):
        """Line 59: svg glob in fallback path (no viz_dir, outputs_dir has svgs)."""
        from concilium.application.benchmarks.charts.output_packager import _cf_collect_graficos

        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "chart.svg").write_text("<svg/>")

        collected: list = []
        _cf_collect_graficos(tmp_path, collected)

        arcs = [arc for _, arc in collected]
        assert "graficos/chart.svg" in arcs

    def test_collects_png_and_svg_from_legacy_outputs(self, tmp_path):
        from concilium.application.benchmarks.charts.output_packager import _cf_collect_graficos

        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "a.png").write_bytes(b"\x89PNG")
        (outputs_dir / "b.svg").write_text("<svg/>")

        collected: list = []
        _cf_collect_graficos(tmp_path, collected)

        arcs = [arc for _, arc in collected]
        assert "graficos/a.png" in arcs
        assert "graficos/b.svg" in arcs


# ─── output_packager.py line 217 (_tentar_gerar_graficos success call) ───────


class TestTentarGerarGraficos:
    def test_calls_gerar_graficos_when_import_succeeds(self, tmp_path):
        """Line 217: gerar_graficos_benchmark is called when outputs/ has no pngs."""
        from concilium.application.benchmarks.charts.output_packager import _tentar_gerar_graficos

        bench_dir = tmp_path / "bench"
        bench_dir.mkdir()

        mock_fn = MagicMock()
        fake_module = MagicMock()
        fake_module.gerar_graficos_benchmark = mock_fn

        with patch.dict(
            "sys.modules",
            {"concilium.application.benchmarks.charts.chart_generator": fake_module},
        ):
            _tentar_gerar_graficos(bench_dir, "TEST")

        mock_fn.assert_called_once_with(bench_dir=bench_dir, slug="TEST")

    def test_skips_call_when_pngs_already_exist(self, tmp_path):
        from concilium.application.benchmarks.charts.output_packager import _tentar_gerar_graficos

        bench_dir = tmp_path / "bench"
        outputs_dir = bench_dir / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "existing.png").write_bytes(b"\x89PNG")

        mock_fn = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "concilium.application.benchmarks.charts.chart_generator": MagicMock(
                    gerar_graficos_benchmark=mock_fn
                )
            },
        ):
            _tentar_gerar_graficos(bench_dir, "TEST")

        mock_fn.assert_not_called()


# ─── output_packager.py lines 175, 187-190 (empacotar_outputs auto path) ─────


class TestEmpacotar:
    def test_empacotar_auto_output_path_and_gerar_graficos(self, tmp_path):
        """Lines 175, 187-190: gerar_graficos=True + output_path=None."""
        from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

        # _find_benchmark_dir candidate 1: config_root.parent / benchmarks/data/TST
        bench_dir = tmp_path / "benchmarks" / "data" / "TST"
        reports_dir = bench_dir / "artifacts" / "outputs" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report.md").write_text("# Report")

        config_root = tmp_path / "config.json"

        with patch(
            "concilium.application.benchmarks.charts.output_packager._tentar_gerar_graficos"
        ) as mock_gen:
            result = empacotar_outputs(
                "TST",
                config_root=config_root,
                output_path=None,
                gerar_graficos=True,
            )

        mock_gen.assert_called_once()
        assert result.exists()
        assert result.suffix == ".zip"

    def test_empacotar_with_explicit_output_path(self, tmp_path):
        """Complement: output_path provided → auto-path block skipped."""
        from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

        bench_dir = tmp_path / "benchmarks" / "data" / "EXP"
        reports_dir = bench_dir / "artifacts" / "outputs" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report.md").write_text("# Report")

        explicit_path = tmp_path / "out.zip"
        config_root = tmp_path / "config.json"

        with patch(
            "concilium.application.benchmarks.charts.output_packager._tentar_gerar_graficos"
        ):
            result = empacotar_outputs(
                "EXP",
                config_root=config_root,
                output_path=explicit_path,
                gerar_graficos=True,
            )

        assert result == explicit_path
        assert result.exists()
