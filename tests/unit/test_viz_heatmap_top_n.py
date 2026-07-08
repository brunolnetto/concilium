"""Tests for heatmap_top_n eficiencia visualization."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _plot(campo, **kwargs):
    from concilium.application.runtime.deliverables.visualizations.eficiencia.heatmap_top_n import plot_heatmap_top_n

    return plot_heatmap_top_n(campo, **kwargs)


def _make_campo(
    pareto=None,
    semanas=None,
    E=None,
    S=None,
    W=None,
    Eta_plan=None,
    Eta_clima=None,
    Delta=None,
    atividades=None,
):
    """Fixture de CampoEficiencia mockado.

    ADR-124: E/S/W são None por padrão (controle não populado no planejamento).
    Eta_plan/Eta_clima/Delta usam dicts independentes (cópia, não a mesma
    referência de E) para exercitar de fato o fallback E/S/W -> Eta_plan sem
    mascarar bugs por compartilhamento de objeto.
    """
    campo = MagicMock()
    campo.pareto_perdas.return_value = pareto or []
    campo.semanas = semanas or ["2026-W01", "2026-W02"]
    campo.E = E
    campo.S = S
    campo.W = W
    campo.Eta_plan = Eta_plan if Eta_plan is not None else (dict(E) if E else {})
    campo.Eta_clima = Eta_clima if Eta_clima is not None else {}
    campo.Delta = Delta if Delta is not None else {}
    campo.atividades = atividades or []
    return campo


class TestPlotHeatmapTopN:
    def test_pareto_perdas_is_called(self):
        campo = _make_campo(pareto=[])
        _plot(campo)
        campo.pareto_perdas.assert_called()

    def test_returns_none_when_pareto_empty(self):
        campo = _make_campo(pareto=[])
        result = _plot(campo)
        assert result is None

    def test_returns_none_when_no_semanas_ativas(self):
        campo = _make_campo(
            pareto=[{"item_id": "act-1", "perda": 0.5}],
            semanas=["2026-W01"],
            E={"act-1": {}},  # No matching semana values
        )
        with patch("matplotlib.pyplot.subplots", return_value=(MagicMock(), MagicMock())):
            with patch("matplotlib.pyplot.colorbar"):
                result = _plot(campo)
        assert result is None

    def test_returns_figure_with_valid_data(self):
        campo = _make_campo(
            pareto=[{"item_id": "act-1", "perda": 0.5}],
            semanas=["2026-W01", "2026-W02"],
            E={"act-1": {"2026-W01": 0.8, "2026-W02": 0.6}},
            atividades=["act-1", "act-2"],
        )
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_im = MagicMock()
        mock_ax.imshow.return_value = mock_im
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            with patch("matplotlib.pyplot.colorbar"):
                with patch("matplotlib.colors.Normalize"):
                    result = _plot(campo, top_n=1, fator="E")
        assert result is mock_fig

    def test_respects_fator_parameter(self):
        campo = _make_campo(
            pareto=[{"item_id": "act-1", "perda": 0.5}],
            semanas=["2026-W01"],
            E={"act-1": {"2026-W01": 0.8}},
        )
        campo.S = {"act-1": {"2026-W01": 0.7}}
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_ax.imshow.return_value = MagicMock()
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            with patch("matplotlib.pyplot.colorbar"):
                with patch("matplotlib.colors.Normalize"):
                    result = _plot(campo, fator="S")
        assert result is mock_fig

    def test_accepts_custom_title(self):
        campo = _make_campo(
            pareto=[{"item_id": "act-1", "perda": 0.5}],
            semanas=["2026-W01"],
            E={"act-1": {"2026-W01": 0.8}},
        )
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_ax.imshow.return_value = MagicMock()
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            with patch("matplotlib.pyplot.colorbar"):
                with patch("matplotlib.colors.Normalize"):
                    _plot(campo, title="Custom Title")
        mock_ax.set_title.assert_called_once()
        call_args = mock_ax.set_title.call_args[0][0]
        assert "Custom Title" in call_args


class TestPlanningFatores:
    """ADR-124: heatmap aceita fator="Eta_clima" e fator="Delta" (planejamento)."""

    def _campo(self):
        campo = _make_campo(
            pareto=[{"item_id": "act-1", "perda": 0.5}],
            semanas=["2026-W01"],
            atividades=["act-1"],
        )
        campo.Eta_clima = {"act-1": {"2026-W01": 0.8}}
        campo.Delta = {"act-1": {"2026-W01": 0.9}}
        campo.Eta_plan = {"act-1": {"2026-W01": 0.72}}
        return campo

    def _plot_fator(self, fator):
        campo = self._campo()
        mock_fig, mock_ax = MagicMock(), MagicMock()
        mock_ax.imshow.return_value = MagicMock()
        with patch("matplotlib.pyplot.subplots", return_value=(mock_fig, mock_ax)):
            with patch("matplotlib.pyplot.colorbar"):
                with patch("matplotlib.colors.Normalize"):
                    return _plot(campo, fator=fator), mock_fig

    def test_fator_eta_clima_retorna_figura(self):
        result, mock_fig = self._plot_fator("Eta_clima")
        assert result is mock_fig

    def test_fator_delta_retorna_figura(self):
        result, mock_fig = self._plot_fator("Delta")
        assert result is mock_fig
