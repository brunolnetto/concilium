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





from unittest.mock import patch  # noqa: E402

# ─── application/runtime/deliverables/visualizations/cube/__init__.py ─────────


class TestCubeInit:
    def test_build_graficos_dict_non_dict_returns_empty(self):
        """Line 61: _build_graficos_dict with non-dict relatorio returns {}."""
        from concilium.application.runtime.deliverables.visualizations.cube import _build_graficos_dict

        assert _build_graficos_dict("not_a_dict") == {}
        assert _build_graficos_dict(42) == {}
        assert _build_graficos_dict(None) == {}

    def test_build_faces_exception_is_swallowed(self):
        """Lines 75-76: _build_faces catches module.build() exceptions silently."""
        from concilium.application.runtime.deliverables.visualizations.cube import _build_faces

        def bad_build(*args, **kwargs):
            raise RuntimeError("chart failed")

        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube._FACE_BUILDERS",
            [(bad_build, "face.png", False)],
        ):
            result = _build_faces(MagicMock(), MagicMock(), {})
        assert result == {}

    def test_build_all_canonical_none_returns_empty(self):
        """Line 90: build_all with canonical=None returns {}."""
        from concilium.application.runtime.deliverables.visualizations.cube import build_all

        result = build_all(canonical=None)
        assert result == {}



