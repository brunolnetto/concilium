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

