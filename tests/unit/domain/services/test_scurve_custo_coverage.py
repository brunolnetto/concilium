from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.runtime.deliverables.visualizations.cube.scurve_custo import (
    _build_monthly_direto,
    _build_monthly_indireto,
    _iso_week_to_ym,
    build,
)

# ---------------------------------------------------------------------------
# _iso_week_to_ym
# ---------------------------------------------------------------------------


class TestIsoWeekToYm:
    def test_week_0_same_month(self):
        d = date(2026, 3, 2)  # Monday
        result = _iso_week_to_ym(0, d)
        assert result == "2026-03"

    def test_week_4_approx_one_month_later(self):
        d = date(2026, 1, 5)
        result = _iso_week_to_ym(4, d)
        # 4 weeks later is approximately February
        assert result == "2026-02"

    def test_week_5_may_cross_month(self):
        d = date(2026, 1, 1)
        result = _iso_week_to_ym(5, d)
        # 35 days from Jan 1 = Feb 5
        assert result == "2026-02"

    def test_large_offset(self):
        d = date(2026, 1, 1)
        result = _iso_week_to_ym(52, d)
        # 52 weeks from 2026-01-01 = 2026-12-24, still in December 2026
        assert result == "2026-12"

    def test_format_shape(self):
        result = _iso_week_to_ym(0, date(2026, 6, 1))
        assert len(result) == 7
        assert result[4] == "-"


# ---------------------------------------------------------------------------
# _build_monthly_direto
# ---------------------------------------------------------------------------


def _make_canonical_direto(planejamento=None, scheduled=None, data_inicio=None):
    cron = SimpleNamespace(scheduled_activities=scheduled or [])
    projeto = SimpleNamespace(data_inicio=data_inicio)
    return SimpleNamespace(planejamento=planejamento, cronograma=cron, projeto=projeto)


class TestBuildMonthlyDireto:
    def test_dict_items(self):
        planejamento = [{"item_id": "A", "subtotal": {"sem_bdi": {"total": 1000.0}}}]
        scheduled = [{"activity_id": "A", "start_week": 0, "end_week": 0}]
        canonical = _make_canonical_direto(planejamento, scheduled, "2026-01-05")
        result = _build_monthly_direto(canonical)
        assert "2026-01" in result
        assert result["2026-01"] == pytest.approx(1000.0)

    def test_object_items_with_model_attributes(self):
        sem_bdi = SimpleNamespace(total=2000.0)
        subtotal = SimpleNamespace(sem_bdi=sem_bdi)
        plan_item = SimpleNamespace(item_id="B", subtotal=subtotal)
        act = SimpleNamespace(activity_id="B", start_week=0, end_week=1)
        cron = SimpleNamespace(scheduled_activities=[act])
        projeto = SimpleNamespace(data_inicio="2026-02-02")
        canonical = SimpleNamespace(planejamento=[plan_item], cronograma=cron, projeto=projeto)
        result = _build_monthly_direto(canonical)
        # cost is spread over 2 weeks (0 and 1), each week = 1000
        assert sum(result.values()) == pytest.approx(2000.0)

    def test_custo_zero_skipped(self):
        planejamento = [{"item_id": "C", "subtotal": {"sem_bdi": {"total": 0.0}}}]
        scheduled = [{"activity_id": "C", "start_week": 0, "end_week": 0}]
        canonical = _make_canonical_direto(planejamento, scheduled, "2026-01-05")
        result = _build_monthly_direto(canonical)
        assert result == {}

    def test_end_before_start_skipped(self):
        planejamento = [{"item_id": "D", "subtotal": {"sem_bdi": {"total": 500.0}}}]
        scheduled = [{"activity_id": "D", "start_week": 5, "end_week": 3}]
        canonical = _make_canonical_direto(planejamento, scheduled, "2026-01-05")
        result = _build_monthly_direto(canonical)
        assert result == {}

    def test_invalid_data_inicio_fallback(self):
        planejamento = [{"item_id": "E", "subtotal": {"sem_bdi": {"total": 100.0}}}]
        scheduled = [{"activity_id": "E", "start_week": 0, "end_week": 0}]
        canonical = _make_canonical_direto(planejamento, scheduled, "not-a-date")
        result = _build_monthly_direto(canonical)
        # Falls back to 2026-01-01
        assert "2026-01" in result

    def test_none_data_inicio_fallback(self):
        planejamento = [{"item_id": "F", "subtotal": {"sem_bdi": {"total": 100.0}}}]
        scheduled = [{"activity_id": "F", "start_week": 0, "end_week": 0}]
        canonical = _make_canonical_direto(planejamento, scheduled, None)
        result = _build_monthly_direto(canonical)
        assert "2026-01" in result

    def test_unknown_activity_id_skipped(self):
        planejamento = [{"item_id": "G", "subtotal": {"sem_bdi": {"total": 800.0}}}]
        scheduled = [{"activity_id": "UNKNOWN", "start_week": 0, "end_week": 0}]
        canonical = _make_canonical_direto(planejamento, scheduled, "2026-01-05")
        result = _build_monthly_direto(canonical)
        assert result == {}

    def test_empty_planejamento(self):
        canonical = _make_canonical_direto([], [], "2026-01-05")
        result = _build_monthly_direto(canonical)
        assert result == {}

    def test_none_cronograma(self):
        planejamento = [{"item_id": "H", "subtotal": {"sem_bdi": {"total": 500.0}}}]
        projeto = SimpleNamespace(data_inicio="2026-01-05")
        canonical = SimpleNamespace(planejamento=planejamento, cronograma=None, projeto=projeto)
        result = _build_monthly_direto(canonical)
        assert result == {}


# ---------------------------------------------------------------------------
# _build_monthly_indireto
# ---------------------------------------------------------------------------


class TestBuildMonthlyIndireto:
    def test_dict_items(self):
        item = {"semana": 0, "custo_semanal": 500.0}
        canonical = SimpleNamespace(indiretos_semanal=[item])
        result = _build_monthly_indireto(canonical, date(2026, 1, 5))
        assert "2026-01" in result
        assert result["2026-01"] == pytest.approx(500.0)

    def test_object_items(self):
        item = SimpleNamespace(semana=0, custo_semanal=300.0)
        canonical = SimpleNamespace(indiretos_semanal=[item])
        result = _build_monthly_indireto(canonical, date(2026, 1, 5))
        assert "2026-01" in result
        assert result["2026-01"] == pytest.approx(300.0)

    def test_semana_none_skipped(self):
        item = {"semana": None, "custo_semanal": 100.0}
        canonical = SimpleNamespace(indiretos_semanal=[item])
        result = _build_monthly_indireto(canonical, date(2026, 1, 5))
        assert result == {}

    def test_semana_zero_not_skipped(self):
        # Line 86-93: semana=0 must NOT be skipped (it is a valid week)
        item = SimpleNamespace(semana=0, custo_semanal=250.0)
        canonical = SimpleNamespace(indiretos_semanal=[item])
        result = _build_monthly_indireto(canonical, date(2026, 1, 5))
        assert len(result) == 1
        assert sum(result.values()) == pytest.approx(250.0)

    def test_two_month_spread(self):
        items = [
            {"semana": 0, "custo_semanal": 100.0},
            {"semana": 5, "custo_semanal": 200.0},
        ]
        canonical = SimpleNamespace(indiretos_semanal=items)
        result = _build_monthly_indireto(canonical, date(2026, 1, 1))
        assert "2026-01" in result
        assert "2026-02" in result

    def test_empty_list(self):
        canonical = SimpleNamespace(indiretos_semanal=[])
        result = _build_monthly_indireto(canonical, date(2026, 1, 5))
        assert result == {}

    def test_object_semana_none_skipped(self):
        item = SimpleNamespace(semana=None, custo_semanal=400.0)
        canonical = SimpleNamespace(indiretos_semanal=[item])
        result = _build_monthly_indireto(canonical, date(2026, 1, 5))
        assert result == {}


# ---------------------------------------------------------------------------
# _bdi_decomp removida (ADR-183 adendo): código morto, nunca chamada por build()
# — verificado que o gráfico real (scurve_custo.png) deriva overhead/lucro/tributos
# do cubo analítico (_build_bdi_multipliers_from_cubo), sem misturar bases
# catálogo/operacional. A função tinha o mesmo bug de bdi_lucro_impostos já
# corrigido em projection.py, mas nunca chegava a afetar o entregável.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# build()
# ---------------------------------------------------------------------------


def _make_rows_nat(direto_val=100.0, indireto_val=50.0):
    return [
        {"periodo": "2026-01", "valor_rs": direto_val, "natureza": "direto"},
        {"periodo": "2026-01", "valor_rs": indireto_val, "natureza": "indireto"},
    ]


class TestBuild:
    def _mock_plt(self):
        fig = MagicMock()
        ax1 = MagicMock()
        ax2 = MagicMock()
        ax1.get_ylim.return_value = (0, 100)
        fig.subplots.return_value = (fig, (ax1, ax2))
        plt_mock = MagicMock()
        plt_mock.subplots.return_value = (fig, (ax1, ax2))
        fig_to_bytes = MagicMock(return_value=b"PNG")
        return plt_mock, fig_to_bytes

    def test_nat_payload_returns_none_gives_none(self):
        canonical = SimpleNamespace(cubo_analitico=None, resultado=None)

        def fake_build_payload(key, *args, **kwargs):
            if key == "tempo_natureza":
                return None
            return {"rows": []}

        with (
            patch("concilium.application.runtime.deliverables.visualizations.cube.scurve_custo.init_mpl") as mock_init,
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.scurve_custo.build_payload",
                side_effect=fake_build_payload,
            ),
        ):
            mock_init.return_value = (MagicMock(), MagicMock())
            result = build(canonical, None)
        assert result is None

    def test_nat_payload_empty_rows_gives_none(self):
        canonical = SimpleNamespace(cubo_analitico=None, resultado=None)

        def fake_build_payload(key, *args, **kwargs):
            if key == "tempo_natureza":
                return {"rows": []}
            return {"rows": []}

        with (
            patch("concilium.application.runtime.deliverables.visualizations.cube.scurve_custo.init_mpl") as mock_init,
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.scurve_custo.build_payload",
                side_effect=fake_build_payload,
            ),
        ):
            mock_init.return_value = (MagicMock(), MagicMock())
            result = build(canonical, None)
        assert result is None

    def test_periodos_empty_returns_none(self):
        # rows with natureza not 'direto'/'indireto' → direto_m and indireto_m empty → periodos empty
        canonical = SimpleNamespace(cubo_analitico=None, resultado=None)

        def fake_build_payload(key, *args, **kwargs):
            if key == "tempo_natureza":
                return {"rows": [{"periodo": "2026-01", "valor_rs": 100.0, "natureza": "unknown"}]}
            return {"rows": []}

        with (
            patch("concilium.application.runtime.deliverables.visualizations.cube.scurve_custo.init_mpl") as mock_init,
            patch(
                "concilium.application.runtime.deliverables.visualizations.cube.scurve_custo.build_payload",
                side_effect=fake_build_payload,
            ),
        ):
            mock_init.return_value = (MagicMock(), MagicMock())
            result = build(canonical, None)
        # periodos will be empty since no direto/indireto/bdi rows
        assert result is None

    def test_import_error_from_init_mpl_returns_none(self):
        canonical = SimpleNamespace(cubo_analitico=None, resultado=None)

        with patch(
            "concilium.application.runtime.deliverables.visualizations.cube.scurve_custo.init_mpl",
            side_effect=ImportError("no matplotlib"),
        ):
            result = build(canonical, None)
        assert result is None


# s_curve_builder.py lines 59, 67: continue paths in _scb_collect_direct_costs
# ---------------------------------------------------------------------------


class TestSCurveBuilderDirectCosts:
    def test_equipe_not_found_in_lookup_skipped(self):
        """Line 59: equipe_lookup.get(sa.activity_id) returns None → continue."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_collect_direct_costs

        sa = SimpleNamespace(activity_id="B1", distribuicao_semanal={})
        equipe_lookup = {}  # B1 not in lookup
        custo, equip, n = _scb_collect_direct_costs([sa], equipe_lookup)
        assert sum(custo.values()) == 0.0

    def test_n_equipes_zero_skipped(self):
        """Line 67: n_equipes=0 → continue."""
        from concilium.domain.services.analytics.s_curve_builder import _scb_collect_direct_costs

        dist = SimpleNamespace(num_equipes=0, eficiencia=1.0, fator_total=None)
        sa = SimpleNamespace(activity_id="A1", distribuicao_semanal={"2024-W01": dist})
        equipe = SimpleNamespace(
            custo_mao_obra_mensal=5000.0,
            custo_equipamentos_mensal=2000.0,
            custo_material_mensal=0.0,
            custo_combustivel_total_mensal=1000.0,
            equipamentos=[],
        )
        custo, equip, n = _scb_collect_direct_costs([sa], {"A1": equipe})
        assert sum(custo.values()) == 0.0


# ---------------------------------------------------------------------------

