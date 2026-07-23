"""Coverage batch 34 — precificacao skill helpers, resultado.py render functions."""

from __future__ import annotations

from types import SimpleNamespace

from openpyxl import Workbook

# resultado.py line 159: _xl_resultado_ref with ref_row not None
# resultado.py line 179: _xl_resultado_indirect_cats body
# ---------------------------------------------------------------------------


class TestXlResultadoHelpers:
    def test_xl_resultado_ref_with_row_returns_formula(self):
        """Line 159: ref_row is not None → returns Excel formula string."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import _xl_resultado_ref

        result = _xl_resultado_ref("PLANEJAMENTO", 13, 5, 0.0)
        assert result.startswith("=")
        assert "$M$5" in result  # col 13 = M

    def test_xl_resultado_ref_with_special_sheet_name_quotes(self):
        """Line 159: sheet with spaces → quoted in formula."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import _xl_resultado_ref

        result = _xl_resultado_ref("INDIRETOS.DET", 8, 3, 0.0)
        assert "INDIRETOS.DET" in result
        assert "$H$3" in result  # col 8 = H

    def test_xl_resultado_ref_with_no_row_returns_fallback(self):
        """ref_row is None → returns fallback value."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import _xl_resultado_ref

        result = _xl_resultado_ref("INDIRETOS.DET", 8, None, 99.5)
        assert result == 99.5

    def test_xl_resultado_indirect_cats_calls_linha_fn(self):
        """Line 179: _xl_resultado_indirect_cats iterates categories and calls linha_fn."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import _xl_resultado_indirect_cats

        calls = []
        res = SimpleNamespace(custo=SimpleNamespace(indireto_adm=100.0, indireto_top=0.0))

        _xl_resultado_indirect_cats(res, None, lambda label, val: calls.append((label, val)))

        assert len(calls) == 5  # ADM, TOP, LAB, QSMS, MOB
        assert any("ADM" in c[0] for c in calls)

    def test_xl_resultado_custo_composicao_cd_zero_uses_zero_razao(self):
        """Line 181: cd <= 0 → razao falls back to 0.0 instead of dividing by zero."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import (
            _xl_resultado_custo_composicao,
        )

        res = SimpleNamespace(
            custo=SimpleNamespace(direto_equipes=0.0, total=500.0),
            venda=SimpleNamespace(total_com_bdi=0.0, total_sem_bdi=0.0),
        )
        calls = []
        cd = _xl_resultado_custo_composicao(res, None, lambda label, val, **kw: calls.append((label, val)))

        assert cd == 0.0
        razao_call = next(c for c in calls if "RAZÃO" in c[0])
        assert razao_call[1] == 0.0

    def test_xl_resultado_custo_composicao_none_res_returns_zero(self):
        """Branch 180->181: res falsy → retorna 0.0 imediatamente sem chamar linha_fn."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import (
            _xl_resultado_custo_composicao,
        )

        calls = []
        cd = _xl_resultado_custo_composicao(None, None, lambda label, val, **kw: calls.append((label, val)))
        assert cd == 0.0
        assert calls == []

    def test_xl_resultado_cap_giro_rows_skips_when_n_exec_zero(self):
        """Branch 199->-197 (false): n_exec<=0 → nenhuma linha é escrita."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import (
            _xl_resultado_cap_giro_rows,
        )

        calls = []
        canonical = SimpleNamespace(resultado=SimpleNamespace(venda=SimpleNamespace(total_com_bdi=1000.0)))
        _xl_resultado_cap_giro_rows(0, canonical, lambda label, val, **kw: calls.append((label, val)))
        assert calls == []

    def test_rcr_build_qty_by_item_repeated_activity_and_out_of_range_month(self):
        """Lines 739 (false branch), 745 (false branch): two scheduled_activities
        entries sharing the same activity_id reuse the existing dict entry
        (the outer `if act.activity_id not in qty_by_item` init only runs once
        per distinct activity_id, not per week), and a week resolving to a
        year-month outside project_months is silently ignored."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import (
            _rcr_build_qty_by_item,
        )

        dist1 = SimpleNamespace(qtd_executada=10.0)
        dist2 = SimpleNamespace(qtd_executada=5.0)
        dist_out_of_range = SimpleNamespace(qtd_executada=99.0)
        act1 = SimpleNamespace(
            activity_id="A1",
            distribuicao_semanal={"2026-W01": dist1},
        )
        # Same activity_id as act1 — hits the false branch of the outer
        # `if act.activity_id not in qty_by_item` init check.
        act2 = SimpleNamespace(
            activity_id="A1",
            distribuicao_semanal={
                "2026-W02": dist2,
                # A week far outside project_months' year-months
                "2030-W20": dist_out_of_range,
            },
        )
        canonical = SimpleNamespace(cronograma=SimpleNamespace(scheduled_activities=[act1, act2]))

        from concilium.infrastructure.adapters.excel.helpers import _week_to_month

        project_months = [_week_to_month("2026-W01"), _week_to_month("2026-W02")]

        result = _rcr_build_qty_by_item(canonical, project_months)

        assert "A1" in result
        # Both activities accumulate into the same dict entry (line 739 false branch)
        total = sum(result["A1"].values())
        assert total == 15.0
        # The out-of-range week's qty must not have been added anywhere
        assert 99.0 not in result["A1"].values()


# ---------------------------------------------------------------------------


# resultado.py lines 418-491: render_bdi
# ---------------------------------------------------------------------------


class TestRenderBdi:
    def test_render_bdi_creates_sheet(self):
        """Lines 418-491: render_bdi writes BDI sheet using DEFAULT_BDI_TABELA."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import render_bdi

        wb = Workbook()
        render_bdi(wb, canonical=None)

        assert "BDI" in wb.sheetnames
        ws = wb["BDI"]
        # Header row should have category names
        assert ws.cell(row=1, column=1).value is not None  # title row


# ---------------------------------------------------------------------------


# resultado.py lines 768-769: render_cronograma_res early return (no months)
# ---------------------------------------------------------------------------


class TestRenderCronogramaRes:
    def test_early_return_when_no_months(self):
        """Lines 768-769: canonical with no cronograma and no projeto → early return."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import render_cronograma_res

        canonical = SimpleNamespace(
            cronograma=None,
            projeto=None,
            eap=[],
            indiretos=None,
            resultado=None,
            ponto_equilibrio=[],
        )

        wb = Workbook()
        render_cronograma_res(wb, canonical)

        ws = wb["CRONOGRAMA.RES"]
        assert ws.cell(row=1, column=1).value == "Sem dados de cronograma."


# ---------------------------------------------------------------------------


# resultado.py lines 817-841: render_equilibrio with ponto_equilibrio and bpe
# ---------------------------------------------------------------------------


class TestRenderEquilibrio:
    def _make_canonical(self, with_bpe: bool = False):
        pe = SimpleNamespace(
            item_id="EAP-001",
            status_validacao="OK",
            custo_fixo_equipe=100_000.0,
            custo_venda_cpu=120_000.0,
            delta=20_000.0,
            preco_venda_cpu=120_000.0,
            gap_escala_abs=0.0,
            gap_praticabilidade_abs=0.0,
        )
        bpe = None
        if with_bpe:
            bpe = SimpleNamespace(
                total_hc_operacional=10,
                total_hc_indireto=2,
                total_hc=12,
                custo_fixo_mensal=500_000.0,
                custo_fixo_total=6_000_000.0,
                numero_equipes_diretas=5,
            )
        resultado = SimpleNamespace(balanco_ponto_equilibrio=bpe)
        return SimpleNamespace(
            eap=[SimpleNamespace(item_id="EAP-001", cpu_id="CPU-001")],
            ponto_equilibrio=[pe],
            resultado=resultado,
            indiretos=None,
        )

    def test_render_equilibrio_with_pe_items(self):
        """Lines 817-820: iterates ponto_equilibrio and writes each row."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import render_equilibrio

        canonical = self._make_canonical(with_bpe=False)
        wb = Workbook()
        render_equilibrio(wb, canonical)

        ws = wb["EQUILIBRIO"]
        assert ws.cell(row=1, column=1).value is not None  # title

    def test_render_equilibrio_with_bpe_block(self):
        """Lines 828-841: bpe is truthy → BALANÇO section rendered."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import render_equilibrio

        canonical = self._make_canonical(with_bpe=True)
        wb = Workbook()
        render_equilibrio(wb, canonical)

        ws = wb["EQUILIBRIO"]
        # Sheet was created without error; bpe section added rows
        assert ws.max_row > 3


# ---------------------------------------------------------------------------


# resultado.py lines 876-877: render_referencia body (indireto_total)
# ---------------------------------------------------------------------------


class TestRenderReferencia:
    def test_render_referencia_with_null_resultado(self):
        """Lines 876-877: render_referencia with canonical.resultado=None runs without error."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import render_referencia

        canonical = SimpleNamespace(
            resultado=None,
            indiretos=None,
            ponto_equilibrio=[],
            eap=[],
        )
        wb = Workbook()
        render_referencia(wb, canonical)

        assert "REFERÊNCIA" in wb.sheetnames

    def test_render_referencia_sv_exception_falls_back_to_default(self):
        """Lines 884-885: _sv's inner except branch — a field whose value cannot be
        coerced to float (e.g. a non-numeric string) falls back to the default 0.0
        instead of propagating."""
        from concilium.infrastructure.adapters.excel.sheets.resultado import render_referencia

        custo = SimpleNamespace(
            direto_equipes="not-a-number",  # float("not-a-number") raises ValueError
            direto_pool=0.0,
            indireto_total=0.0,
            total=0.0,
        )
        venda = SimpleNamespace(total_sem_bdi=0.0, total_com_bdi=0.0)
        resultado = SimpleNamespace(custo=custo, venda=venda, margem_pct=0.0)
        canonical = SimpleNamespace(
            resultado=resultado,
            indiretos=None,
            ponto_equilibrio=[],
            eap=[],
        )
        wb = Workbook()
        render_referencia(wb, canonical)

        assert "REFERÊNCIA" in wb.sheetnames

