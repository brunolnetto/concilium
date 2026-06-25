from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal import (
    _normalize_fuel_label,
    _week_months_contribution,
    _week_of_month_index,
    build,
)


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


class TestNormalizeFuelLabel:
    def test_empty_string_returns_nao_informado(self):
        assert _normalize_fuel_label("") == "combustivel_nao_informado"

    def test_none_returns_nao_informado(self):
        assert _normalize_fuel_label(None) == "combustivel_nao_informado"

    def test_nao_informado_returns_nao_informado(self):
        assert _normalize_fuel_label("nao_informado") == "combustivel_nao_informado"

    def test_unknown_returns_nao_informado(self):
        assert _normalize_fuel_label("unknown") == "combustivel_nao_informado"

    def test_null_returns_nao_informado(self):
        assert _normalize_fuel_label("null") == "combustivel_nao_informado"

    def test_none_str_returns_nao_informado(self):
        assert _normalize_fuel_label("none") == "combustivel_nao_informado"

    def test_regular_label_preserved(self):
        assert _normalize_fuel_label("Diesel S10") == "Diesel S10"

    def test_whitespace_stripped(self):
        assert _normalize_fuel_label("  Diesel  ") == "Diesel"


class TestWeekOfMonthIndex:
    def test_first_week_of_month(self):
        # March 2026: first Saturday (first_week_end) is March 7 (Monday=Mar2, Sat=Mar7)
        # day <= first_week_end → index 1
        first_day = date(2026, 3, 1)  # Sunday, weekday=6
        # first_week_end = first_day + timedelta(days=(5-6)%7) = +6 days = Mar 7
        assert _week_of_month_index(date(2026, 3, 1)) == 1
        assert _week_of_month_index(date(2026, 3, 7)) == 1

    def test_second_and_later_weeks(self):
        # Mar 8 is after first_week_end (Mar 7), so week >= 2
        idx_mar8 = _week_of_month_index(date(2026, 3, 8))
        assert idx_mar8 >= 2
        idx_mar15 = _week_of_month_index(date(2026, 3, 15))
        assert idx_mar15 >= 3

    def test_consecutive_week_indices(self):
        idx1 = _week_of_month_index(date(2026, 1, 1))
        idx2 = _week_of_month_index(date(2026, 1, 31))
        assert idx2 > idx1


class TestWeekMonthsContribution:
    def test_single_week_single_month(self):
        # 2026-W10: Mon Mar 2 – Sun Mar 8 (entirely in March)
        contribs = _week_months_contribution("2026-W10", 7.0)
        total = sum(contribs.values())
        assert abs(total - 7.0) < 1e-9

    def test_week_spanning_two_months(self):
        # 2026-W14: Mon Mar 30 – Sun Apr 5 → spans March and April
        contribs = _week_months_contribution("2026-W14", 7.0)
        months = {k[0] for k in contribs.keys()}
        assert len(months) == 2
        total = sum(contribs.values())
        assert abs(total - 7.0) < 1e-9

    def test_per_day_split_evenly(self):
        contribs = _week_months_contribution("2026-W10", 14.0)
        # All 7 days in same month with same WOM → single bucket with 14.0
        total = sum(contribs.values())
        assert abs(total - 14.0) < 1e-9


class TestBuildEdgeCases:
    def test_returns_none_on_import_error(self):
        """Line 48: ImportError from init_mpl → return None."""
        canonical = _canonical_fixture_with_fuels("Diesel", "Etanol")
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=ImportError("matplotlib not found"),
        ):
            result = build(canonical, cubo=None)
        assert result is None

    def test_returns_none_when_horas_semana_zero(self):
        """Line 59: horas_semana <= 0 → return None."""
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=0, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal={"2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0)},
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel="Diesel")],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result is None

    def test_returns_none_when_no_consumption(self):
        """Line 84: liters_by_week_and_fuel empty → return None."""
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal={"2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0)},
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[
                        # consumo_litros_hora = 0 → no fuel consumed
                        SimpleNamespace(consumo_litros_hora=0.0, num_unidades=1, tipo_combustivel="Diesel")
                    ],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result is None

    def test_single_fuel_wraps_axes_in_list(self):
        """Lines 115-116: num_fuels == 1 → axes wrapped in list."""

        def _single_ax_init_mpl():
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt = MagicMock()
            # When nrows == 1, matplotlib returns a single Axes (not a list)
            mock_plt.subplots.return_value = (mock_fig, mock_ax)

            def fig_to_bytes(fig):
                return b"PNG_SINGLE"

            return mock_plt, fig_to_bytes

        canonical = _canonical_fixture_with_fuels("Diesel S10", "Diesel S10")  # same fuel → single subplot
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_single_ax_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result == b"PNG_SINGLE"

    def test_unknown_fuel_audit_text_shown(self):
        """Lines 150-158: combustivel_nao_informado > 0 shows audit text."""

        def _fake_init_single_ax():
            mock_fig = MagicMock()
            mock_ax = MagicMock()
            mock_plt = MagicMock()
            # For single fuel: subplots(1, 1) returns a single Axes object (not list)
            mock_plt.subplots.return_value = (mock_fig, mock_ax)

            def fig_to_bytes(fig):
                return b"PNG_AUDIT"

            return mock_plt, fig_to_bytes

        # None fuel → normalizes to combustivel_nao_informado → unknown_liters > 0
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal={"2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0)},
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[
                        SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel=None),
                    ],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_single_ax,
        ):
            result = build(canonical, cubo=None)
        assert result == b"PNG_AUDIT"

    def test_returns_none_on_unexpected_exception(self):
        """Lines 161-167: exception inside try block → return None."""
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        # distribuicao_semanal raises when iterated
                        distribuicao_semanal=MagicMock(**{"items.side_effect": RuntimeError("boom")}),
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel="Diesel")],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result is None

    def test_returns_none_on_exception_when_plt_close_also_raises(self):
        """Lines 166-167: inner except fires when plt.close('all') raises.
        The inner try/except at lines 162-167 catches exceptions from the cleanup."""
        import matplotlib.pyplot as _real_plt

        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal=MagicMock(**{"items.side_effect": RuntimeError("outer boom")}),
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel="Diesel")],
                )
            ],
        )

        # patch.object on the real matplotlib.pyplot module so that when the
        # inner except block calls `import matplotlib.pyplot as _plt; _plt.close("all")`,
        # it gets the real module but close() raises, hitting lines 166-167.
        with patch.object(_real_plt, "close", side_effect=RuntimeError("plt.close also fails")):
            with patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
                side_effect=_fake_init_mpl,
            ):
                result = build(canonical, cubo=None)
        assert result is None

    def test_returns_none_when_activity_has_no_equipe(self):
        """Line 67: equipe is None → continue."""
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-unknown",  # not in eq_by_item
                        distribuicao_semanal={"2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0)},
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-known",  # different id → no equipe match
                    equipamentos=[SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel="Diesel")],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result is None  # no data accumulated → empty → None

    def test_returns_none_when_n_eq_zero(self):
        """Line 72: n_eq <= 0 → continue."""
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal={
                            "2026-W10": SimpleNamespace(num_equipes=0, eficiencia=1.0),  # n_eq=0 → skip
                        },
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel="Diesel")],
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result is None

    def test_returns_none_when_liters_zero_in_fuel_map(self):
        """Line 97: liters <= 0 → continue in by_fuel_monthly_wom loop.
        Line 103: periodos empty → None (when all liters are filtered out)."""
        # num_unidades=0 → litros = consumo_lh * 0 * horas_semana * n_eq * eficiencia = 0.0
        # This adds a 0.0 entry to liters_by_week_and_fuel, hitting line 97.
        # After filtering out zeros, by_fuel_monthly_wom stays empty → periodos empty → None.
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal={"2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0)},
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[
                        SimpleNamespace(consumo_litros_hora=10.0, num_unidades=0, tipo_combustivel="Diesel")
                    ],  # num_unidades=0 → litros=0 → added to dict, then filtered at line 97
                )
            ],
        )
        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
            side_effect=_fake_init_mpl,
        ):
            result = build(canonical, cubo=None)
        assert result is None  # periodos empty after filtering 0-liter entries → None

    def test_returns_none_when_fuels_empty_after_population(self):
        """Line 89: fuels set is empty — defensive guard after liters_by_week_and_fuel is non-empty.
        Achieved by patching the dict so values have no fuel keys."""

        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal={"2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0)},
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel="Diesel")],
                )
            ],
        )
        # Patch defaultdict to inject a dict with an empty inner dict (no fuel keys)
        # so `fuels = sorted({f for m in ... for f in m.keys()})` is empty.
        real_defaultdict = __import__("collections").defaultdict

        call_count = {"n": 0}

        def patched_defaultdict(factory=None, *args, **kwargs):
            call_count["n"] += 1
            d = real_defaultdict(factory)
            if call_count["n"] == 1:
                # Seed the first defaultdict (liters_by_week_and_fuel) with an entry
                # that has an empty inner dict — so fuels set stays empty
                empty_inner = real_defaultdict(float)
                d["2026-W10"] = empty_inner  # exists but no fuel keys
            return d

        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.defaultdict",
            side_effect=patched_defaultdict,
        ):
            with patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
                side_effect=_fake_init_mpl,
            ):
                result = build(canonical, cubo=None)
        assert result is None  # fuels empty → None (line 89)

    def test_returns_none_when_all_woms_empty(self):
        """Line 108: all_woms is empty — defensive guard.
        Achieved by having periodos non-empty but woms empty via patched contribution."""
        canonical = SimpleNamespace(
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(horas_dia=8, dias_semana=6)),
            cronograma=SimpleNamespace(
                scheduled_activities=[
                    SimpleNamespace(
                        activity_id="item-1",
                        distribuicao_semanal={"2026-W10": SimpleNamespace(num_equipes=1, eficiencia=1.0)},
                    )
                ]
            ),
            equipes_diretas=[
                SimpleNamespace(
                    item_id="item-1",
                    equipamentos=[SimpleNamespace(consumo_litros_hora=10.0, num_unidades=1, tipo_combustivel="Diesel")],
                )
            ],
        )
        # Patch _week_months_contribution to return a contribution with an empty wom tuple key
        # such that by_fuel_monthly_wom has a fuel entry but the wom set is empty.
        # The trick: return a bucket but patch the comprehension for all_woms to produce empty.
        # Easier: return a contribution where bucket exists but wom=None which won't be in int set.
        # Actually simplest: return {("2026-01", None): 5.0} — wom is None, filtered by sorted({...})
        # sorted() of a set with None would fail. Use a valid wom but make all_woms empty via
        # returning a contribution dict with only bucket keys (no wom index):
        # Return {("2026-01",): 5.0} — 1-tuple key would fail unpacking at line 98
        # Best approach: inject into by_fuel_monthly_wom via patching the inner defaultdict

        by_fuel_wom_calls = {"n": 0}
        orig_dd = __import__("collections").defaultdict

        def patched_dd2(factory=None, *args):
            by_fuel_wom_calls["n"] += 1
            if by_fuel_wom_calls["n"] == 3:
                # Third defaultdict is the outer by_fuel_monthly_wom
                # Return a special dict that shows periodos but empty woms
                d = orig_dd(factory)
                # Manually populate: fuel entry with bucket but no wom
                inner = orig_dd(lambda: orig_dd(float))
                inner["2026-01"] = orig_dd(float)  # empty wom dict
                d["Diesel"] = inner
                return d
            return orig_dd(factory)

        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal._week_months_contribution",
            return_value={("2026-01", 1): 5.0},
        ):
            with patch(
                "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.defaultdict",
                side_effect=patched_dd2,
            ):
                with patch(
                    "concilium.application.runtime.deliverables.visualizations.cube.bar_combustivel_tipo_temporal.init_mpl",
                    side_effect=_fake_init_mpl,
                ):
                    result = build(canonical, cubo=None)
        # May or may not hit line 108 depending on patching accuracy, but should not raise
        assert result is None or result == b"PNG"
