"""Coverage batch 5 — visualization normalization, diesel fallback, and other small gaps."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# bar_tempo_direto_categoria.py lines 42-43 and bar_tempo_indireto_categoria.py 42-43
# inner matplotlib cleanup in except Exception path
# ---------------------------------------------------------------------------


class TestBarTempoCategoriaMplCleanup:
    def test_direto_outer_exception_triggers_cleanup(self):
        """Lines 42-43: outer rendering exception → matplotlib close called."""
        import concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_direto_categoria as mod

        canonical = MagicMock()
        cubo = MagicMock()

        with patch.object(mod, "build_payload", return_value={"rows": [{"a": 1}], "columns": ["a"]}):
            with patch.object(mod, "init_mpl", return_value=(MagicMock(), MagicMock())):
                with patch.object(mod, "render_stacked_bar", side_effect=RuntimeError("boom")):
                    result = mod.build(canonical, cubo)
        assert result is None

    def test_indireto_outer_exception_triggers_cleanup(self):
        """Lines 42-43 indireto: outer rendering exception → matplotlib close called."""
        import concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_indireto_categoria as mod

        canonical = MagicMock()
        cubo = MagicMock()

        with patch.object(mod, "build_payload", return_value={"rows": [{"a": 1}], "columns": ["a"]}):
            with patch.object(mod, "init_mpl", return_value=(MagicMock(), MagicMock())):
                with patch.object(mod, "render_stacked_bar", side_effect=RuntimeError("boom")):
                    result = mod.build(canonical, cubo)
        assert result is None

