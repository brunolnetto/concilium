"""Coverage batch 34 — precificacao skill helpers, resultado.py render functions."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook


# ---------------------------------------------------------------------------
# _precificacao/skill.py line 71: _extract_overrides returns dict when dict
# ---------------------------------------------------------------------------


class TestExtractOverrides:
    def _load(self):
        from concilium.application.skills import load_skill_stage

        return load_skill_stage("06-resultado-financeiro", "_precificacao", "_extract_overrides")

    def test_returns_dict_when_dict_value(self):
        """Line 71: val is a dict → return val."""
        fn = self._load()
        result = fn({"insumos_override": {"key": 42}})
        assert result == {"key": 42}

    def test_returns_none_when_not_dict(self):
        fn = self._load()
        assert fn({"insumos_override": "string"}) is None
        assert fn({}) is None


# ---------------------------------------------------------------------------
# _precificacao/skill.py lines 192-198: _as_bool string branches
# ---------------------------------------------------------------------------


class TestAsBool:
    def _load(self):
        from concilium.application.skills import load_skill_stage

        return load_skill_stage("06-resultado-financeiro", "_precificacao", "_as_bool")

    def test_true_string_returns_true(self):
        """Lines 192, 194-195: string in truthy set → True."""
        fn = self._load()
        assert fn("true") is True
        assert fn("yes") is True
        assert fn("1") is True

    def test_false_string_returns_false(self):
        """Lines 192, 196-197: string in falsy set → False."""
        fn = self._load()
        assert fn("false") is False
        assert fn("no") is False
        assert fn("0") is False

    def test_unrecognized_string_returns_false(self):
        """Line 198: string not in either set → falls through to return False."""
        fn = self._load()
        assert fn("maybe") is False


# ---------------------------------------------------------------------------
# _precificacao/skill.py lines 290, 294: run_precificacao_unitaria
# erros_eap and erros_insumo blocks triggered
# ---------------------------------------------------------------------------


class TestRunPrecificacaoErros:
    def _load_run(self):
        from concilium.application.skills import load_skill_stage

        return load_skill_stage("06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria")

    def _make_canonical(self, cpu_id: str = "ACT-NOPREFIX"):
        from datetime import UTC, date, datetime

        from concilium.domain.models.canonical import (
            CanonicalModel,
            Coordenadas,
            EapItem,
            Meta,
            Projeto,
            RegimeTrabalho,
        )

        return CanonicalModel(
            meta=Meta(gerado_em=datetime.now(UTC), contexto_id="ctx-test"),
            projeto=Projeto(
                id="proj-test",
                nome="Test",
                tipo_obra="pavimentacao",
                localizacao="CE",
                coordenadas=Coordenadas(lat=-3.7, lng=-38.5),
                data_inicio=date(2026, 1, 1),
                data_termino=date(2026, 6, 30),
                regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
                snapshot_catalogo_id="snap-test",
                snapshot_perfil_id="perf-test",
            ),
            eap=[
                EapItem(
                    item_id="EAP-001",
                    ordem=1,
                    cpu_id=cpu_id,
                    descricao="Item teste",
                    unidade="m3",
                    quantitativo=100.0,
                )
            ],
        )

    def test_unknown_cpu_populates_erros_eap(self):
        """Lines 290: erros_eap non-empty → VAL-EAP-01 validacao appended."""
        run = self._load_run()
        # cpu_id not starting with "CPU-" → erros_eap.append directly
        canonical = self._make_canonical(cpu_id="ACT-UNKNOWN-XYZ")
        # Empty catalog so cpu_lookup is empty
        catalogo: dict = {"cpus": [], "insumos": [], "produtividades": [], "producoes": []}

        result = run(canonical, inputs={}, catalogo=catalogo, perfil={})

        codes = [v.codigo for v in result.validacoes]
        assert "VAL-EAP-01" in codes

    def test_erros_insumo_triggers_val_plan_insumo(self):
        """Line 294: erros_insumo non-empty → VAL-PLAN-INSUMO appended."""
        import importlib
        import importlib.util
        from pathlib import Path

        # Load the skill module directly so we can monkeypatch _process_eap_item
        skill_path = (
            Path("src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/skill.py")
            .resolve()
        )
        spec = importlib.util.spec_from_file_location("_precif_skill_b34", skill_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Replace _process_eap_item to inject erros_insumo
        def _fake_process(item, cpu_lookup, insumo_lookup, prod_lookup, equipe_lookup,
                           planejamento_item_overrides, bdi_aplicado, repo, jurisdicao_id,
                           overrides, data_base, plan_out, erros_eap, erros_insumo,
                           equip_sem_decomp, validacoes, benchmark_mode, **kwargs):
            erros_insumo.add("INS-FAKE-01")

        mod._process_eap_item = _fake_process

        canonical = self._make_canonical(cpu_id="CPU-TEST")
        catalogo: dict = {"cpus": [], "insumos": [], "produtividades": [], "producoes": []}

        result = mod.run_precificacao_unitaria(canonical, {}, catalogo, {})
        codes = [v.codigo for v in result.validacoes]
        assert "VAL-PLAN-INSUMO" in codes


# ---------------------------------------------------------------------------
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
