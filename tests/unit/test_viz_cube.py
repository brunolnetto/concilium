"""Coverage sweep 3 — files with 20-35 lines missing."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── application/runtime/deliverables/visualizations/cube/__init__ ───────────


class TestVizCubeInit:
    def test_build_all_function_exists(self):
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        assert callable(build_all)

    def test_build_all_empty_relatorio(self):
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        canonical = MagicMock()
        canonical.cubo_analitico = None
        canonical.cronograma = None
        result = build_all(relatorio={}, canonical=canonical)
        assert isinstance(result, dict)

    def test_module_has_build_all(self):
        from concilium.application.runtime.deliverables.visualizations import cube

        assert hasattr(cube, "build_all")

