"""Tests for modules at 0% coverage:

- src/concilium/application/runtime/deliverables/visualizations/eficiencia/eta_obra.py
- src/concilium/application/runtime/deliverables/visualizations/eficiencia/pareto_perdas.py
- src/concilium/application/runtime/deliverables/visualizations/eficiencia/__init__.py

proxy.py foi extraído para tools/mcp-proxy/ (pacote standalone, isolado do
restante do monorepo) — seus testes vivem em tools/mcp-proxy/tests/test_proxy.py.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

_mock_matplotlib = MagicMock()
_mock_plt = MagicMock()
_mock_matplotlib.pyplot = _mock_plt


# Section 5: eficiencia __init__.py — verify it exports the four functions
# ─────────────────────────────────────────────────────────────────────────────

_INIT_MOD = "concilium.application.runtime.deliverables.visualizations.eficiencia"


class TestEficienciaInit:
    def test_module_loads_and_exports_all(self):
        """The eficiencia __init__ exports the four expected functions."""
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": _mock_matplotlib,
                "matplotlib.pyplot": _mock_plt,
            },
        ):
            # Clean any cached submodule imports so __init__ re-runs with mocked plt
            for key in list(sys.modules.keys()):
                if key.startswith(_INIT_MOD):
                    del sys.modules[key]

            import importlib

            mod = importlib.import_module(_INIT_MOD)

        assert hasattr(mod, "plot_eta_obra")
        assert hasattr(mod, "plot_pareto_perdas")
        assert hasattr(mod, "plot_heatmap_top_n")
        assert hasattr(mod, "plot_waterfall_causal")

    def test_all_exports_are_callable(self):
        """All four symbols exported from the package are callable."""
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": _mock_matplotlib,
                "matplotlib.pyplot": _mock_plt,
            },
        ):
            for key in list(sys.modules.keys()):
                if key.startswith(_INIT_MOD):
                    del sys.modules[key]
            import importlib

            mod = importlib.import_module(_INIT_MOD)

        for name in ("plot_eta_obra", "plot_pareto_perdas", "plot_heatmap_top_n", "plot_waterfall_causal"):
            assert callable(getattr(mod, name)), f"{name} must be callable"

