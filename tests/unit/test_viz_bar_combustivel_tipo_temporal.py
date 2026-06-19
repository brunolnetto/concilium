from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal import build


def _fake_init_mpl():
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_plt = MagicMock()
    # When nrows > 1, matplotlib returns array-like axes
    mock_plt.subplots.return_value = (mock_fig, [mock_ax, mock_ax])

    def fig_to_bytes(fig):  # noqa: ARG001
        return b"PNG"

    return mock_plt, fig_to_bytes


def _canonical_fixture_with_fuels(tipo_a: object, tipo_b: object):
    return SimpleNamespace(
        projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
        cronograma=SimpleNamespace(
            scheduled_activities=[
                SimpleNamespace(
                    activity_id="item-1",
                    distribuicao_semanal={
                        "2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0),
                        "2026-W14": SimpleNamespace(num_equipes=1, eficiencia=1.0),
                    },
                )
            ]
        ),
        equipes_diretas=[
            SimpleNamespace(
                item_id="item-1",
                equipamentos=[
                    SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel=tipo_a),
                    SimpleNamespace(consumo_litros_hora=4.0, num_unidades=1, tipo_combustivel=tipo_b),
                ],
            )
        ],
    )


class TestBarCombustivelTipoTemporal:
    def test_returns_none_without_schedule(self):
        canonical = SimpleNamespace(cronograma=None, equipes_diretas=[])
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            assert build(canonical, cubo=None) is None

    def test_returns_png_with_multiple_fuel_subplots(self):
        canonical = _canonical_fixture_with_fuels("Diesel S10", "Gasolina")
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result == b"PNG"

    def test_normalizes_missing_fuel_label_and_still_renders(self):
        canonical = _canonical_fixture_with_fuels(None, "Etanol")
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result == b"PNG"
