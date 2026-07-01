"""Coverage tests for 10-relatorio-e-artefatos/_skill_helpers_b.py.

Targets missing lines: 34, 56->54, 68->63, 83-84, 98-99, 110->exit, 125, 137.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Load module via the registered package name (set when run_relatorio_e_artefatos is imported)
from concilium.application.skills import run_relatorio_e_artefatos  # noqa: F401  triggers registration

# Ensure the helpers_b sub-module is loaded (it's lazily imported inside helpers_a)
if "_concilium_skillpkg_10_relatorio_e_artefatos._skill_helpers_b" not in sys.modules:
    importlib.import_module("_concilium_skillpkg_10_relatorio_e_artefatos._skill_helpers_b")

_MOD = sys.modules["_concilium_skillpkg_10_relatorio_e_artefatos._skill_helpers_b"]

_add_part_cost = _MOD._add_part_cost
_build_particao_by_item = _MOD._build_particao_by_item
_build_sched_by_item = _MOD._build_sched_by_item
_build_pesos_semana = _MOD._build_pesos_semana
_resolve_item_cost = _MOD._resolve_item_cost
_apply_pesos_to_result = _MOD._apply_pesos_to_result
_distribute_item_cost = _MOD._distribute_item_cost
_distribute_indirect = _MOD._distribute_indirect
_monthly_direct_costs = _MOD._monthly_direct_costs
_monthly_indirect_costs = _MOD._monthly_indirect_costs


# ---------------------------------------------------------------------------
# _add_part_cost — line 34 (continue when item_id is empty)
# ---------------------------------------------------------------------------


class TestAddPartCost:
    def test_empty_item_id_skips_entry(self):
        part = SimpleNamespace(item_id="", custo_total_particionado=999.0)
        contrato = SimpleNamespace(particao_por_item=[part])
        particao: dict = {}
        _add_part_cost(particao, contrato)
        assert particao == {}

    def test_falsy_item_id_none_skips(self):
        part = SimpleNamespace(item_id=None, custo_total_particionado=500.0)
        contrato = SimpleNamespace(particao_por_item=[part])
        particao: dict = {}
        _add_part_cost(particao, contrato)
        assert particao == {}

    def test_valid_item_id_accumulates(self):
        part1 = SimpleNamespace(item_id="A1", custo_total_particionado=100.0)
        part2 = SimpleNamespace(item_id="A1", custo_total_particionado=50.0)
        contrato = SimpleNamespace(particao_por_item=[part1, part2])
        particao: dict = {}
        _add_part_cost(particao, contrato)
        assert particao["A1"] == pytest.approx(150.0)

    def test_no_particao_por_item_noop(self):
        contrato = SimpleNamespace(particao_por_item=None)
        particao: dict = {}
        _add_part_cost(particao, contrato)
        assert particao == {}


# ---------------------------------------------------------------------------
# _build_sched_by_item — line 52 (no cronograma), 56->54 (empty aid skipped)
# ---------------------------------------------------------------------------


class TestBuildSchedByItem:
    def _make_canonical(self, cronograma):
        can = MagicMock()
        can.cronograma = cronograma
        return can

    def test_no_cronograma_returns_empty(self):
        can = self._make_canonical(None)
        result = _build_sched_by_item(can)
        assert result == {}

    def test_empty_activity_id_skipped(self):
        sa = SimpleNamespace(activity_id="")
        cron = SimpleNamespace(scheduled_activities=[sa])
        can = self._make_canonical(cron)
        result = _build_sched_by_item(can)
        assert result == {}

    def test_valid_activity_id_included(self):
        sa = SimpleNamespace(activity_id="ACT-01")
        cron = SimpleNamespace(scheduled_activities=[sa])
        can = self._make_canonical(cron)
        result = _build_sched_by_item(can)
        assert "ACT-01" in result

    def test_no_scheduled_activities_returns_empty(self):
        cron = SimpleNamespace(scheduled_activities=None)
        can = self._make_canonical(cron)
        result = _build_sched_by_item(can)
        assert result == {}


# ---------------------------------------------------------------------------
# _build_pesos_semana — line 65-66 (zero peso skipped), 68->63 (ym not in result)
# ---------------------------------------------------------------------------


class TestBuildPesosSemana:
    def test_zero_peso_skipped(self):
        dist = {"2024-W01": SimpleNamespace(num_equipes=0.0)}
        result_dict = {(2024, 1): 0.0}
        result = _build_pesos_semana(dist, result_dict)
        assert result == {}

    def test_negative_peso_skipped(self):
        dist = {"2024-W01": SimpleNamespace(num_equipes=-1.0)}
        result_dict = {(2024, 1): 0.0}
        result = _build_pesos_semana(dist, result_dict)
        assert result == {}

    def test_ym_not_in_result_dict_skipped(self):
        # _week_to_month returns a (year, month) tuple; if not in result, skip
        dist = {"2020-W01": SimpleNamespace(num_equipes=2.0)}
        # Use empty result dict so no key matches
        result = _build_pesos_semana(dist, {})
        assert result == {}

    def test_valid_peso_and_ym_accumulated(self):
        _week_to_month = sys.modules["_concilium_skillpkg_10_relatorio_e_artefatos._skill_helpers_a"]._week_to_month
        ym = _week_to_month("2024-W01")
        dist = {"2024-W01": SimpleNamespace(num_equipes=3.0)}
        result_dict = {ym: 0.0}
        result = _build_pesos_semana(dist, result_dict)
        assert ym in result
        assert result[ym] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# _apply_pesos_to_result — lines 83-84 (soma_pesos <= 0 → first month)
# ---------------------------------------------------------------------------


class TestApplyPesosToResult:
    def test_zero_soma_pesos_fallback_to_first_month(self):
        months = [(2024, 1), (2024, 2)]
        result = {m: 0.0 for m in months}
        _apply_pesos_to_result(result, {}, 1000.0, months)
        assert result[(2024, 1)] == pytest.approx(1000.0)
        assert result[(2024, 2)] == pytest.approx(0.0)

    def test_positive_pesos_distributed_proportionally(self):
        months = [(2024, 1), (2024, 2)]
        result = {m: 0.0 for m in months}
        pesos = {(2024, 1): 1.0, (2024, 2): 3.0}
        _apply_pesos_to_result(result, pesos, 400.0, months)
        assert result[(2024, 1)] == pytest.approx(100.0)
        assert result[(2024, 2)] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# _distribute_item_cost — lines 98-99 (no dist → first month)
# ---------------------------------------------------------------------------


class TestDistributeItemCost:
    def test_no_dist_uses_first_month(self):
        months = [(2024, 1), (2024, 2)]
        result = {m: 0.0 for m in months}
        eq = SimpleNamespace(custo_total=500.0)
        sa = SimpleNamespace(distribuicao_semanal=None)
        _distribute_item_cost(result, "A1", eq, {}, {"A1": sa}, months)
        assert result[(2024, 1)] == pytest.approx(500.0)

    def test_zero_custo_item_noop(self):
        months = [(2024, 1)]
        result = {m: 0.0 for m in months}
        eq = SimpleNamespace(custo_total=0.0)
        _distribute_item_cost(result, "A1", eq, {}, {}, months)
        assert result[(2024, 1)] == pytest.approx(0.0)

    def test_no_sa_entry_uses_first_month(self):
        months = [(2024, 1)]
        result = {m: 0.0 for m in months}
        eq = SimpleNamespace(custo_total=200.0)
        _distribute_item_cost(result, "A1", eq, {}, {}, months)
        assert result[(2024, 1)] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# _distribute_indirect — line 106-107 (MOB), 110->exit (empty meses_ativos)
# ---------------------------------------------------------------------------


class TestDistributeIndirect:
    def test_mob_adds_to_first_month(self):
        months = [(2024, 1), (2024, 2)]
        result = {m: 0.0 for m in months}
        ind = SimpleNamespace(categoria="MOB", custo_total=300.0, permanencia_meses=None)
        _distribute_indirect(result, ind, months, len(months))
        assert result[(2024, 1)] == pytest.approx(300.0)
        assert result[(2024, 2)] == pytest.approx(0.0)

    def test_empty_meses_ativos_noop(self):
        # permanencia_meses=None with n=0 and empty months → meses_ativos=[] → no-op
        result: dict = {}
        ind = SimpleNamespace(categoria="ADM", custo_total=600.0, permanencia_meses=None)
        _distribute_indirect(result, ind, [], 0)
        assert result == {}

    def test_non_mob_distributes_evenly(self):
        months = [(2024, 1), (2024, 2)]
        result = {m: 0.0 for m in months}
        ind = SimpleNamespace(categoria="ADM", custo_total=400.0, permanencia_meses=2)
        _distribute_indirect(result, ind, months, len(months))
        assert result[(2024, 1)] == pytest.approx(200.0)
        assert result[(2024, 2)] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# _monthly_direct_costs — line 125 (empty project_months early return)
# ---------------------------------------------------------------------------


class TestMonthlyDirectCosts:
    def test_empty_months_returns_empty_dict(self):
        can = MagicMock()
        result = _monthly_direct_costs(can, [])
        assert result == {}

    def test_months_with_no_equipes_returns_zeros(self):
        can = MagicMock()
        can.contratos_recurso = []
        can.equipes_diretas = []
        months = [(2024, 1)]
        result = _monthly_direct_costs(can, months)
        assert result[(2024, 1)] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _monthly_indirect_costs — line 137 (empty project_months early return)
# ---------------------------------------------------------------------------


class TestMonthlyIndirectCosts:
    def test_empty_months_returns_empty_dict(self):
        can = MagicMock()
        result = _monthly_indirect_costs(can, [])
        assert result == {}

    def test_months_with_no_indiretos_returns_zeros(self):
        can = MagicMock()
        can.indiretos = []
        months = [(2024, 1)]
        result = _monthly_indirect_costs(can, months)
        assert result[(2024, 1)] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _build_particao_by_item — line 41 (_add_part_cost is called)
# ---------------------------------------------------------------------------


class TestBuildParticaoByItem:
    def test_with_contratos_accumulates(self):
        part = SimpleNamespace(item_id="A1", custo_total_particionado=200.0)
        contrato = SimpleNamespace(particao_por_item=[part])
        can = MagicMock()
        can.contratos_recurso = [contrato]
        result = _build_particao_by_item(can)
        assert result["A1"] == pytest.approx(200.0)

    def test_no_contratos_returns_empty(self):
        can = MagicMock()
        can.contratos_recurso = []
        result = _build_particao_by_item(can)
        assert result == {}


# ---------------------------------------------------------------------------
# _resolve_item_cost — line 75->77 (custo from particao, not from eq)
# ---------------------------------------------------------------------------


class TestResolveItemCost:
    def test_custo_from_particao_skips_eq_fallback(self):
        eq = SimpleNamespace(custo_total=999.0)
        # particao has a positive value → if custo <= 0.0 branch is NOT taken
        result = _resolve_item_cost({"A1": 500.0}, "A1", eq)
        assert result == pytest.approx(500.0)

    def test_zero_in_particao_falls_back_to_eq(self):
        eq = SimpleNamespace(custo_total=300.0)
        result = _resolve_item_cost({"A1": 0.0}, "A1", eq)
        assert result == pytest.approx(300.0)

    def test_missing_in_particao_falls_back_to_eq(self):
        eq = SimpleNamespace(custo_total=150.0)
        result = _resolve_item_cost({}, "A1", eq)
        assert result == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# _monthly_indirect_costs — line 140 (loop body with actual indiretos)
# ---------------------------------------------------------------------------


class TestMonthlyIndirectCostsWithData:
    def test_mob_indirect_goes_to_first_month(self):
        months = [(2024, 1), (2024, 2)]
        can = MagicMock()
        can.indiretos = [SimpleNamespace(categoria="MOB", custo_total=500.0, permanencia_meses=None)]
        result = _monthly_indirect_costs(can, months)
        assert result[(2024, 1)] == pytest.approx(500.0)
        assert result[(2024, 2)] == pytest.approx(0.0)

    def test_non_mob_indirect_distributed_evenly(self):
        months = [(2024, 1), (2024, 2)]
        can = MagicMock()
        can.indiretos = [SimpleNamespace(categoria="ADM", custo_total=400.0, permanencia_meses=2)]
        result = _monthly_indirect_costs(can, months)
        assert result[(2024, 1)] == pytest.approx(200.0)
        assert result[(2024, 2)] == pytest.approx(200.0)
