"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# bar_tempo_natureza.py lines 25-26: init_mpl ImportError → return None
# ---------------------------------------------------------------------------


class TestBarTempoNaturezaImportError:
    def test_init_mpl_importerror_returns_none(self):
        """Lines 25-26: init_mpl raises ImportError → return None."""
        import concilium.application.runtime.deliverables.visualizations.cube.bar_tempo_natureza as mod

        canonical = MagicMock()
        cubo = MagicMock()

        with patch.object(mod, "build_payload", return_value={"rows": [{"a": 1}], "columns": ["a"]}):
            with patch.object(mod, "init_mpl", side_effect=ImportError("no matplotlib")):
                result = mod.build(canonical, cubo)
        assert result is None

