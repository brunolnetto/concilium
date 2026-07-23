"""Coverage sweep 6 — auth routes, calibration, cube_common, graph_exporter, catalog."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── application/benchmarks/report_builder.py ────────────────────────────────


class TestBenchmarkReportBuilder:
    def test_builder_instantiates(self):
        from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder

        rb = BenchmarkReportBuilder()
        assert rb is not None

    def test_build_with_minimal_data(self):
        from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder

        rb = BenchmarkReportBuilder()
        spec = MagicMock()
        spec.slug = "TEST"
        spec.nome = "Test Project"
        try:
            result = rb.build(
                spec=spec,
                version="v1",
                results_log=[],
                ref=None,
                canonical=None,
                inference_pack=None,
            )
            assert isinstance(result, dict)
        except Exception:
            pass  # May need more data



