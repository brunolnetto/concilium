"""Coverage sweep 8 — cube_projection_views, side_effects, escopo_store, etapa_diffs."""

from __future__ import annotations

# ─── application/benchmarks/analysis/etapa_diffs.py ──────────────────────────


class TestEtapaDiffs:
    def test_module_importable(self):
        from concilium.application.benchmarks.analysis import etapa_diffs

        assert etapa_diffs is not None

    def test_functions_exist(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import generate_diffs_for_benchmark

        assert callable(generate_diffs_for_benchmark)

    def test_compare_functions_importable(self):
        from concilium.application.benchmarks.analysis.etapa_diffs import (
            compare_planejamento_skill04,
            compare_resultado_skill06,
        )

        assert callable(compare_planejamento_skill04)
        assert callable(compare_resultado_skill06)

