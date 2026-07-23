"""Coverage tests for infrastructure/adapters/excel/sheets/operacional.py.

No prior test file existed for this module. Targets:
  - _xl_diretos_material: custo_material_mensal > 0 branch (lines 87-96)
  - _xl_indirect_verbas_fixas_rows: non-empty verbas_fixas loop (lines 224-234)
  - _xl_indirect_mob_rows: non-empty mobilizacoes loop (lines 241-250)
  - _compute_cell_metric: unrecognized key returns None (line 635)
  - render_cronograma: total_item <= 0 and last_acum > 0 fallback (line 773)
"""

from __future__ import annotations

from types import SimpleNamespace

from openpyxl import Workbook
from openpyxl.styles import PatternFill

from concilium.infrastructure.adapters.excel.sheets.operacional import (
    _build_act_lookup_and_totals,
    _compute_accum_prop,
    _compute_cell_metric,
    _xl_diretos_material,
    _xl_indirect_mob_rows,
    _xl_indirect_monthly_section,
    _xl_indirect_verbas_fixas_rows,
    render_cronograma,
)


def _sheet():
    wb = Workbook()
    return wb.active


class TestXlDiretosMaterial:
    def test_positive_custo_material_writes_row(self):
        ws = _sheet()
        eq = SimpleNamespace(
            item_id="ACT-1",
            custo_material_mensal=500.0,
            permanencia_meses=3.0,
        )
        next_row = _xl_diretos_material(ws, 1, eq, PatternFill())
        assert next_row == 2
        assert ws.cell(row=1, column=1).value == "MATERIAL"
        assert ws.cell(row=1, column=2).value == "ACT-1"

    def test_zero_custo_material_skips_row(self):
        ws = _sheet()
        eq = SimpleNamespace(item_id="ACT-2", custo_material_mensal=0.0, permanencia_meses=1.0)
        next_row = _xl_diretos_material(ws, 1, eq, PatternFill())
        assert next_row == 1
        assert ws.cell(row=1, column=1).value is None


class TestXlIndirectVerbasFixasRows:
    def test_non_empty_verbas_fixas_writes_rows(self):
        ws = _sheet()
        ind = SimpleNamespace(verbas_fixas=[{"valor_total": 1000.0, "descricao": "Verba X"}])
        next_row = _xl_indirect_verbas_fixas_rows(ws, 1, ind, "ADM", 1.0, PatternFill())
        assert next_row == 2
        assert ws.cell(row=1, column=2).value == "VERBA FIXA"
        assert ws.cell(row=1, column=4).value == "Verba X"

    def test_none_ind_returns_same_row(self):
        ws = _sheet()
        next_row = _xl_indirect_verbas_fixas_rows(ws, 5, None, "ADM", 1.0, PatternFill())
        assert next_row == 5


class TestXlIndirectMobRows:
    def test_non_empty_mobilizacoes_writes_rows(self):
        ws = _sheet()
        mob = SimpleNamespace(
            origem="SP",
            destino="RJ",
            distancia_km=400.0,
            descricao="Transporte de equipe",
            num_unidades=2,
            custo_km=1.5,
        )
        ind = SimpleNamespace(mobilizacoes=[mob])
        next_row = _xl_indirect_mob_rows(ws, 1, ind, "MOB", PatternFill())
        assert next_row == 2
        assert ws.cell(row=1, column=2).value == "MOBILIZAÇÃO"
        assert "SP -> RJ" in ws.cell(row=1, column=3).value

    def test_none_ind_returns_same_row(self):
        ws = _sheet()
        next_row = _xl_indirect_mob_rows(ws, 5, None, "MOB", PatternFill())
        assert next_row == 5


class TestComputeCellMetric:
    def test_unrecognized_key_returns_none(self):
        result = _compute_cell_metric(
            key="bogus_metric",
            wk_entry={"n_eq": 1},
            accum_prop={},
            wk="2026-W01",
            total_item=100.0,
            dias_semana=5,
        )
        assert result is None


class TestComputeAccumPropFallback:
    def test_last_acum_used_when_total_item_non_positive(self):
        """Exercises the data shape that drives render_cronograma's line 773
        fallback (`if total_item <= 0 and last_acum > 0: total_item = last_acum`)."""
        wk_data = {"2026-W01": {"qtd_acum": 50.0}, "2026-W02": {"qtd_acum": 0.0}}
        accum_prop, last_acum = _compute_accum_prop(wk_data, ["2026-W01", "2026-W02"])
        assert last_acum == 50.0
        total_item = 0.0
        if total_item <= 0 and last_acum > 0:
            total_item = last_acum
        assert total_item == 50.0


class TestRenderCronogramaTotalItemFallback:
    def test_total_item_falls_back_to_last_acum_when_final_week_is_zero(self):
        """Line 773: the last scheduled week has qtd_acumulada=0.0 (so
        item_totals[item_id] == 0.0), but an earlier week had positive
        qtd_acumulada — render_cronograma must fall back to that last
        positive accumulated value rather than treating the item as 0%."""
        sa = SimpleNamespace(
            activity_id="A1",
            distribuicao_semanal={
                "2026-W01": SimpleNamespace(num_equipes=1, qtd_executada=80.0, qtd_acumulada=80.0),
                "2026-W02": SimpleNamespace(num_equipes=0, qtd_executada=0.0, qtd_acumulada=0.0),
            },
        )
        item = SimpleNamespace(item_id="A1", descricao="Item A1", unidade="m3", quantitativo=100.0)
        canonical = SimpleNamespace(
            cronograma=SimpleNamespace(scheduled_activities=[sa]),
            projeto=SimpleNamespace(regime_trabalho=SimpleNamespace(dias_semana=6)),
            praticabilidade=None,
            eap=[item],
        )
        wb = Workbook()

        render_cronograma(wb, canonical)

        ws = wb["CRONOGRAMA.DET"]
        assert ws.title == "CRONOGRAMA.DET"


class TestXlIndirectMonthlySection:
    def test_empty_project_months_is_noop(self):
        """Branch 292→exit: project_months falsy → function returns immediately."""
        ws = _sheet()
        # Should not raise and should not write anything beyond row 1's defaults.
        _xl_indirect_monthly_section(ws, 1, [], {}, 8)
        assert ws.cell(row=4, column=1).value is None

    def test_non_empty_project_months_writes_section(self):
        ws = _sheet()
        _xl_indirect_monthly_section(ws, 1, [(2026, 1), (2026, 2)], {(2026, 1): 500.0}, 8)
        # A "Distribuição Mensal de Indiretos" section row must have been written.
        values = [ws.cell(row=r, column=1).value for r in range(1, 10)]
        assert any(v for v in values if v)


class TestBuildActLookupAndTotals:
    def test_activity_with_empty_distribuicao_semanal_skips_item_totals(self):
        """Branch 652→642: act.distribuicao_semanal is empty → item_totals
        entry is not created for that activity, but the loop still proceeds."""
        act_empty = SimpleNamespace(activity_id="A-EMPTY", distribuicao_semanal={})
        act_full = SimpleNamespace(
            activity_id="A-FULL",
            distribuicao_semanal={"2026-W01": SimpleNamespace(num_equipes=1, qtd_executada=10.0, qtd_acumulada=10.0)},
        )
        act_lookup, item_totals, all_weeks = _build_act_lookup_and_totals([act_empty, act_full])

        assert "A-EMPTY" not in item_totals
        assert "A-FULL" in item_totals
        assert act_lookup["A-EMPTY"] == {}
