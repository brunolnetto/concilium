"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# heatmap_top_n.py lines 34-35: matplotlib ImportError → return None
# ---------------------------------------------------------------------------


class TestHeatmapTopNMatplotlibImportError:
    def test_importerror_returns_none(self):
        """Lines 34-35: matplotlib not available → return None."""
        from concilium.application.runtime.deliverables.visualizations.eficiencia.heatmap_top_n import (
            plot_heatmap_top_n,
        )

        campo = MagicMock()
        with patch.dict(sys.modules, {"matplotlib.colors": None, "matplotlib.pyplot": None}):
            result = plot_heatmap_top_n(campo)
        assert result is None


# ---------------------------------------------------------------------------

