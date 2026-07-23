"""Tests for concilium.infrastructure.adapters.excel.cash_flow module."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

# ─── helpers for building minimal CanonicalModel ──────────────────────────────


def _make_minimal_canonical():
    """Build a CanonicalModel with only required fields populated."""
    from concilium.domain.models.canonical import CanonicalModel

    data = {
        "meta": {"gerado_em": "2026-01-01T00:00:00Z", "contexto_id": "ctx-test"},
        "projeto": {
            "id": "proj-test",
            "nome": "Test Project",
            "tipo_obra": "terraplenagem",
            "localizacao": "SP",
            "coordenadas": {"lat": -23.5, "lng": -46.6},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-01-01",
            "data_termino": "2026-12-31",
            "snapshot_catalogo_id": "cat-v1",
            "snapshot_perfil_id": "perf-v1",
        },
    }
    return CanonicalModel.model_validate(data)


# ─── helpers: _next_month ─────────────────────────────────────────────────────


class TestNextMonth:
    def test_next_month_mid_year(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _next_month

        assert _next_month((2026, 6)) == (2026, 7)

    def test_next_month_december_wraps_to_january(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _next_month

        assert _next_month((2026, 12)) == (2027, 1)

    def test_next_month_january(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _next_month

        assert _next_month((2025, 1)) == (2025, 2)


# ─── _mdc_accumulate_act ──────────────────────────────────────────────────────


class TestMdcAccumulateAct:
    def _make_dist(self, qtd):
        dist = MagicMock()
        dist.qtd_executada = qtd
        return dist

    def test_skips_when_cpu_zero(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _mdc_accumulate_act

        act = MagicMock()
        act.activity_id = "A1"
        act.distribuicao_semanal = {"2026-W02": self._make_dist(10.0)}
        result = {(2026, 1): 0.0}
        _mdc_accumulate_act(act, {"A1": 0.0}, result)
        assert result[(2026, 1)] == 0.0

    def test_skips_when_cpu_negative(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _mdc_accumulate_act

        act = MagicMock()
        act.activity_id = "A1"
        act.distribuicao_semanal = {"2026-W02": self._make_dist(5.0)}
        result = {(2026, 1): 0.0}
        _mdc_accumulate_act(act, {"A1": -1.0}, result)
        assert result[(2026, 1)] == 0.0

    def test_accumulates_correctly(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _mdc_accumulate_act

        act = MagicMock()
        act.activity_id = "A1"
        # 2026-W02 and 2026-W03 both map to January 2026
        act.distribuicao_semanal = {
            "2026-W02": self._make_dist(10.0),  # Jan 2026
            "2026-W03": self._make_dist(5.0),  # Jan 2026
        }
        result = {(2026, 1): 0.0}
        _mdc_accumulate_act(act, {"A1": 100.0}, result)
        assert result[(2026, 1)] == 1500.0  # (10+5)*100

    def test_skips_zero_qtd(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _mdc_accumulate_act

        act = MagicMock()
        act.activity_id = "A1"
        act.distribuicao_semanal = {"2026-W02": self._make_dist(0.0)}
        result = {(2026, 1): 5.0}
        _mdc_accumulate_act(act, {"A1": 50.0}, result)
        assert result[(2026, 1)] == 5.0  # unchanged

    def test_skips_month_not_in_result(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _mdc_accumulate_act

        act = MagicMock()
        act.activity_id = "A1"
        # 2026-W50 is in December 2026
        act.distribuicao_semanal = {"2026-W50": self._make_dist(10.0)}
        # result only has January
        result = {(2026, 1): 0.0}
        _mdc_accumulate_act(act, {"A1": 100.0}, result)
        # Not added — month not in result
        assert result == {(2026, 1): 0.0}

    def test_activity_not_in_cost_per_unit(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _mdc_accumulate_act

        act = MagicMock()
        act.activity_id = "A-MISSING"
        act.distribuicao_semanal = {"2026-W02": self._make_dist(5.0)}
        result = {(2026, 1): 0.0}
        _mdc_accumulate_act(act, {}, result)
        # cpu=0.0 (default) → skipped
        assert result[(2026, 1)] == 0.0


# ─── _monthly_direct_costs ────────────────────────────────────────────────────


class TestMonthlyDirectCosts:
    def _make_canonical_empty(self):
        canonical = MagicMock()
        canonical.cronograma = None
        canonical.planejamento = None
        return canonical

    def test_returns_zeros_when_no_cronograma(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_direct_costs

        canonical = self._make_canonical_empty()
        months = [(2026, 1), (2026, 2)]
        result = _monthly_direct_costs(canonical, months)
        assert result == {(2026, 1): 0.0, (2026, 2): 0.0}

    def test_returns_zeros_when_no_planejamento(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_direct_costs

        canonical = MagicMock()
        canonical.cronograma = MagicMock()
        canonical.cronograma.scheduled_activities = []
        canonical.planejamento = None
        months = [(2026, 1)]
        result = _monthly_direct_costs(canonical, months)
        assert result == {(2026, 1): 0.0}

    def test_distributes_cost_by_qty(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_direct_costs

        # Build a planejamento item
        plan_item = MagicMock()
        plan_item.item_id = "A1"
        plan_item.quantitativo = 10.0
        plan_item.subtotal = MagicMock()
        plan_item.subtotal.sem_bdi = MagicMock()
        plan_item.subtotal.sem_bdi.total = 1000.0  # 100/unit

        # Build a scheduled activity
        dist = MagicMock()
        dist.qtd_executada = 5.0
        act = MagicMock()
        act.activity_id = "A1"
        # 2026-W02 maps to January 2026
        act.distribuicao_semanal = {"2026-W02": dist}

        canonical = MagicMock()
        canonical.planejamento = [plan_item]
        canonical.cronograma = MagicMock()
        canonical.cronograma.scheduled_activities = [act]

        months = [(2026, 1), (2026, 2)]
        result = _monthly_direct_costs(canonical, months)
        assert result[(2026, 1)] == 500.0  # 100/unit × 5 units

    def test_zero_quantitativo_uses_default(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_direct_costs

        plan_item = MagicMock()
        plan_item.item_id = "A1"
        plan_item.quantitativo = 0.0
        plan_item.subtotal = MagicMock()
        plan_item.subtotal.sem_bdi = MagicMock()
        plan_item.subtotal.sem_bdi.total = 100.0

        dist = MagicMock()
        dist.qtd_executada = 3.0
        act = MagicMock()
        act.activity_id = "A1"
        act.distribuicao_semanal = {"2026-W01": dist}

        canonical = MagicMock()
        canonical.planejamento = [plan_item]
        canonical.cronograma = MagicMock()
        canonical.cronograma.scheduled_activities = [act]

        months = [(2026, 1)]
        result = _monthly_direct_costs(canonical, months)
        # qty=0 → cost_per_unit = 0 → no accumulation
        assert result[(2026, 1)] == 0.0

    def test_none_subtotal_treated_as_zero(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_direct_costs

        plan_item = MagicMock()
        plan_item.item_id = "A1"
        plan_item.quantitativo = 5.0
        plan_item.subtotal = None

        canonical = MagicMock()
        canonical.planejamento = [plan_item]
        canonical.cronograma = MagicMock()
        canonical.cronograma.scheduled_activities = []

        months = [(2026, 1)]
        result = _monthly_direct_costs(canonical, months)
        assert result[(2026, 1)] == 0.0


# ─── _monthly_indirect_costs ──────────────────────────────────────────────────


class TestMonthlyIndirectCosts:
    def test_empty_months_returns_empty(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_indirect_costs

        canonical = MagicMock()
        canonical.indiretos = []
        result = _monthly_indirect_costs(canonical, [])
        assert result == {}

    def test_mob_concentrated_in_first_month(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_indirect_costs

        ind = MagicMock()
        ind.categoria = "MOB"
        ind.custo_total = 50000.0

        canonical = MagicMock()
        canonical.indiretos = [ind]
        months = [(2026, 1), (2026, 2), (2026, 3)]
        result = _monthly_indirect_costs(canonical, months)
        assert result[(2026, 1)] == 50000.0
        assert result[(2026, 2)] == 0.0
        assert result[(2026, 3)] == 0.0

    def test_adm_distributed_evenly(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_indirect_costs

        ind = MagicMock()
        ind.categoria = "ADM"
        ind.custo_total = 30000.0
        ind.permanencia_meses = None  # use all months

        canonical = MagicMock()
        canonical.indiretos = [ind]
        months = [(2026, 1), (2026, 2), (2026, 3)]
        result = _monthly_indirect_costs(canonical, months)
        assert abs(result[(2026, 1)] - 10000.0) < 0.01
        assert abs(result[(2026, 2)] - 10000.0) < 0.01
        assert abs(result[(2026, 3)] - 10000.0) < 0.01

    def test_permanencia_meses_limits_distribution(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_indirect_costs

        ind = MagicMock()
        ind.categoria = "TOP"
        ind.custo_total = 20000.0
        ind.permanencia_meses = 2  # only 2 months

        canonical = MagicMock()
        canonical.indiretos = [ind]
        months = [(2026, 1), (2026, 2), (2026, 3)]
        result = _monthly_indirect_costs(canonical, months)
        assert abs(result[(2026, 1)] - 10000.0) < 0.01
        assert abs(result[(2026, 2)] - 10000.0) < 0.01
        assert result[(2026, 3)] == 0.0  # beyond permanencia


# ─── _cash_flow ───────────────────────────────────────────────────────────────


class TestCashFlow:
    def _make_canonical(self, total_com_bdi=1_000_000.0):
        """Build a minimal canonical for cash flow testing with mocked resultado."""
        canonical = _make_minimal_canonical()
        resultado = MagicMock()
        resultado.venda = MagicMock()
        resultado.venda.total_com_bdi = total_com_bdi
        canonical.resultado = resultado
        return canonical

    def test_returns_empty_when_no_resultado(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        canonical = _make_minimal_canonical()  # resultado=None
        result = _cash_flow(canonical)
        assert result == []

    def test_returns_empty_when_no_project_months(self):
        from unittest.mock import patch

        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        canonical = self._make_canonical()
        # _project_months returns [] → n=0 → early return
        with patch(
            "concilium.infrastructure.adapters.excel.cash_flow._project_months",
            return_value=[],
        ):
            result = _cash_flow(canonical)
        assert result == []

    def test_total_revenue_equals_M(self):
        """Sum of all receitas over all months (incl. extra month) must equal M."""
        from unittest.mock import patch

        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        M = 600_000.0
        canonical = self._make_canonical(total_com_bdi=M)
        months = [(2026, 1), (2026, 2), (2026, 3)]  # n=3

        with (
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._project_months",
                return_value=months,
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_direct_costs",
                return_value={m: 0.0 for m in months},
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_indirect_costs",
                return_value={m: 0.0 for m in months},
            ),
        ):
            rows = _cash_flow(canonical)

        total_receita = sum(r["receita"] for r in rows)
        assert abs(total_receita - M) < 0.01

    def test_month_1_receita_is_zero(self):
        """Receita in the first month (index 0) is always 0."""
        from unittest.mock import patch

        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        M = 900_000.0
        canonical = self._make_canonical(total_com_bdi=M)
        months = [(2026, 1), (2026, 2), (2026, 3)]

        with (
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._project_months",
                return_value=months,
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_direct_costs",
                return_value={m: 0.0 for m in months},
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_indirect_costs",
                return_value={m: 0.0 for m in months},
            ),
        ):
            rows = _cash_flow(canonical)

        assert rows[0]["receita"] == 0.0

    def test_extra_month_has_residuo(self):
        """The last row corresponds to the extra month (n+1) and contains the residuo."""
        from unittest.mock import patch

        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        n = 3
        M = 1_000_000.0
        canonical = self._make_canonical(total_com_bdi=M)
        months = [(2026, i) for i in range(1, n + 1)]

        with (
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._project_months",
                return_value=months,
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_direct_costs",
                return_value={m: 0.0 for m in months},
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_indirect_costs",
                return_value={m: 0.0 for m in months},
            ),
        ):
            rows = _cash_flow(canonical)

        # n+1 total rows (n months + 1 extra residuo month)
        assert len(rows) == n + 1
        parcela_base = math.floor(M / n)
        residuo_expected = M - parcela_base * (n - 1)
        assert abs(rows[-1]["receita"] - residuo_expected) < 0.01

    def test_row_fields_complete(self):
        """Each row contains all required keys."""
        from unittest.mock import patch

        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        canonical = self._make_canonical(total_com_bdi=100_000.0)
        months = [(2026, 1), (2026, 2)]
        expected_keys = {
            "mes_label",
            "mes_ym",
            "despesa",
            "receita",
            "despesa_acumulada",
            "receita_acumulada",
            "saldo",
            "saldo_atual",
            "exposicao_acumulada",
        }

        with (
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._project_months",
                return_value=months,
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_direct_costs",
                return_value={m: 0.0 for m in months},
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_indirect_costs",
                return_value={m: 0.0 for m in months},
            ),
        ):
            rows = _cash_flow(canonical)

        for row in rows:
            assert expected_keys.issubset(row.keys())

    def test_exposicao_equals_minus_saldo_atual(self):
        """exposicao_acumulada == -(saldo_atual) by definition."""
        from unittest.mock import patch

        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        canonical = self._make_canonical(total_com_bdi=500_000.0)
        months = [(2026, 1), (2026, 2), (2026, 3)]

        with (
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._project_months",
                return_value=months,
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_direct_costs",
                return_value={m: 50000.0 for m in months},
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_indirect_costs",
                return_value={m: 10000.0 for m in months},
            ),
        ):
            rows = _cash_flow(canonical)

        for row in rows:
            assert abs(row["exposicao_acumulada"] + row["saldo_atual"]) < 0.01

    def test_single_month_project(self):
        """Edge: single month project (n=1): parcela_base=floor(M/1)=M, residuo=M-M*0=M."""
        from unittest.mock import patch

        from concilium.infrastructure.adapters.excel.cash_flow import _cash_flow

        M = 200_000.0
        canonical = self._make_canonical(total_com_bdi=M)
        months = [(2026, 1)]

        with (
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._project_months",
                return_value=months,
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_direct_costs",
                return_value={(2026, 1): 0.0},
            ),
            patch(
                "concilium.infrastructure.adapters.excel.cash_flow._monthly_indirect_costs",
                return_value={(2026, 1): 0.0},
            ),
        ):
            rows = _cash_flow(canonical)

        # 2 rows: month 1 + extra
        assert len(rows) == 2
        total_receita = sum(r["receita"] for r in rows)
        assert abs(total_receita - M) < 0.01


# ─── _monthly_qty_by_item ─────────────────────────────────────────────────────


class TestMonthlyQtyByItem:
    def test_returns_empty_without_cronograma(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_qty_by_item

        canonical = _make_minimal_canonical()  # cronograma=None
        result = _monthly_qty_by_item(canonical, [(2026, 1)])
        assert result == {}

    def test_aggregates_by_activity_and_month(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_qty_by_item

        dist1 = MagicMock()
        dist1.qtd_executada = 10.0
        dist2 = MagicMock()
        dist2.qtd_executada = 5.0

        act = MagicMock()
        act.activity_id = "ACT-1"
        # 2026-W02 and 2026-W03 both map to January 2026; W06 maps to February 2026
        act.distribuicao_semanal = {
            "2026-W02": dist1,  # January 2026
            "2026-W03": dist2,  # January 2026
        }

        canonical = MagicMock()
        canonical.cronograma = MagicMock()
        canonical.cronograma.scheduled_activities = [act]

        months = [(2026, 1), (2026, 2)]
        result = _monthly_qty_by_item(canonical, months)
        assert "ACT-1" in result
        assert result["ACT-1"][(2026, 1)] == 15.0
        assert result["ACT-1"][(2026, 2)] == 0.0

    def test_skips_weeks_not_in_project_months(self):
        from concilium.infrastructure.adapters.excel.cash_flow import _monthly_qty_by_item

        dist = MagicMock()
        dist.qtd_executada = 7.0

        act = MagicMock()
        act.activity_id = "ACT-2"
        # 2026-W50 maps to December 2026
        act.distribuicao_semanal = {"2026-W50": dist}

        canonical = MagicMock()
        canonical.cronograma = MagicMock()
        canonical.cronograma.scheduled_activities = [act]

        months = [(2026, 1)]  # December not in months
        result = _monthly_qty_by_item(canonical, months)
        assert result["ACT-2"][(2026, 1)] == 0.0
