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

# ─────────────────────────────────────────────────────────────────────────────
# Section 3: eta_obra.py
# ─────────────────────────────────────────────────────────────────────────────

# We load the module with matplotlib mocked so the import succeeds in CI.
_mock_matplotlib = MagicMock()
_mock_plt = MagicMock()
_mock_matplotlib.pyplot = _mock_plt


def _make_campo_eta(eta_dict: dict) -> MagicMock:
    campo = MagicMock()
    campo.eta_obra.return_value = eta_dict
    campo.semanas = list(eta_dict.keys())
    campo.atividades = ["eap-1"]
    campo.E = {"eap-1": eta_dict}
    return campo


class TestPlotEtaObra:
    def test_matplotlib_not_installed_returns_none(self):
        """plot_eta_obra returns None when matplotlib is not available."""
        with patch.dict(
            "sys.modules",
            {"matplotlib": None, "matplotlib.pyplot": None},
        ):
            # Force reimport without matplotlib
            mod_name = "concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra import (
                plot_eta_obra,
            )

            campo = MagicMock()
            result = plot_eta_obra(campo)
            assert result is None

    def test_empty_eta_serie_returns_none(self):
        """plot_eta_obra returns None when campo.eta_obra() returns {}."""
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": _mock_matplotlib,
                "matplotlib.pyplot": _mock_plt,
            },
        ):
            mod_name = "concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra import (
                plot_eta_obra,
            )

            campo = _make_campo_eta({})
            result = plot_eta_obra(campo)
            assert result is None

    def test_with_data_calls_plt_and_returns_figure(self):
        """plot_eta_obra calls pyplot and returns the figure mock when data is present."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        local_plt = MagicMock()
        local_plt.subplots.return_value = (mock_fig, mock_ax)

        local_mpl = MagicMock()
        local_mpl.pyplot = local_plt

        with patch.dict(
            "sys.modules",
            {
                "matplotlib": local_mpl,
                "matplotlib.pyplot": local_plt,
            },
        ):
            mod_name = "concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra"
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.eta_obra import (
                plot_eta_obra,
            )

            campo = _make_campo_eta({"2026-W01": 0.9, "2026-W02": 0.85})
            result = plot_eta_obra(campo)

        assert result is mock_fig
        local_plt.subplots.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: pareto_perdas.py
# ─────────────────────────────────────────────────────────────────────────────

_PARETO_DATA = [
    {"item_id": "eap-1", "pct_perda": 25.0, "perda_fisica_total": 1000.0},
    {"item_id": "eap-2", "pct_perda": 15.0, "perda_fisica_total": 500.0},
]

_PARETO_MOD = "concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas"


def _make_campo_pareto(pareto_list: list) -> MagicMock:
    campo = MagicMock()
    campo.pareto_perdas.return_value = pareto_list
    return campo


class TestPlotParetoPerdas:
    def test_matplotlib_not_installed_returns_none(self):
        """plot_pareto_perdas returns None when matplotlib is not available."""
        with patch.dict("sys.modules", {"matplotlib": None, "matplotlib.pyplot": None}):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = MagicMock()
            result = plot_pareto_perdas(campo)
            assert result is None

    def test_empty_pareto_returns_none(self):
        """plot_pareto_perdas returns None when pareto_perdas() returns []."""
        with patch.dict(
            "sys.modules",
            {"matplotlib": _mock_matplotlib, "matplotlib.pyplot": _mock_plt},
        ):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = _make_campo_pareto([])
            result = plot_pareto_perdas(campo)
            assert result is None

    def test_with_data_calls_plt_and_returns_figure(self):
        """plot_pareto_perdas calls pyplot and returns figure mock when data is present."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        # barh returns a list of bar objects; ax.text does nothing
        mock_bars = [MagicMock(), MagicMock()]
        mock_ax.barh.return_value = mock_bars
        # Each bar needs get_width(), get_y(), get_height()
        for bar in mock_bars:
            bar.get_width.return_value = 500.0
            bar.get_y.return_value = 0.0
            bar.get_height.return_value = 0.5

        local_plt = MagicMock()
        local_plt.subplots.return_value = (mock_fig, mock_ax)
        local_mpl = MagicMock()
        local_mpl.pyplot = local_plt

        with patch.dict(
            "sys.modules",
            {"matplotlib": local_mpl, "matplotlib.pyplot": local_plt},
        ):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = _make_campo_pareto(_PARETO_DATA)
            result = plot_pareto_perdas(campo)

        assert result is mock_fig
        local_plt.subplots.assert_called_once()

    def test_pareto_perdas_called_with_default_top_n(self):
        """plot_pareto_perdas passes top_n=10 by default to campo.pareto_perdas."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_bar = MagicMock()
        mock_bar.get_width.return_value = 100.0
        mock_bar.get_y.return_value = 0.0
        mock_bar.get_height.return_value = 0.5
        mock_ax.barh.return_value = [mock_bar]

        local_plt = MagicMock()
        local_plt.subplots.return_value = (mock_fig, mock_ax)
        local_mpl = MagicMock()
        local_mpl.pyplot = local_plt

        with patch.dict(
            "sys.modules",
            {"matplotlib": local_mpl, "matplotlib.pyplot": local_plt},
        ):
            if _PARETO_MOD in sys.modules:
                del sys.modules[_PARETO_MOD]
            from concilium.application.runtime.deliverables.visualizations.eficiencia.pareto_perdas import (
                plot_pareto_perdas,
            )

            campo = _make_campo_pareto([{"item_id": "eap-X", "pct_perda": 50.0, "perda_fisica_total": 200.0}])
            plot_pareto_perdas(campo)

        campo.pareto_perdas.assert_called_once_with(top_n=10)


# ─────────────────────────────────────────────────────────────────────────────
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
