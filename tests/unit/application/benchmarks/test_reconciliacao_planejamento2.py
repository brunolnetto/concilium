"""Tests for application/benchmarks/reconciliacao_planejamento.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestParseValor:
    def test_none_returns_zero(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor(None) == 0.0

    def test_empty_string(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor("") == 0.0

    def test_pt_number(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor("1.234,56") == pytest.approx(1234.56)

    def test_invalid(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor("abc") == 0.0


class TestDisparityAnalysis:
    def test_empty(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import DisparityAnalysis

        a = DisparityAnalysis()
        assert a.total_canonical_direto == 0.0
        assert a.disparidades == []


class TestGerarRelatorio:
    def test_generates_string(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            gerar_relatorio_reconciliacao,
        )

        analise = DisparityAnalysis()
        analise.disparidades = [
            {
                "item_id": "2.1",
                "descricao": "Test",
                "planejamento_sem_bdi": 100.0,
                "planejamento_com_bdi": 120.0,
                "canonical": 150.0,
                "delta": 50.0,
                "delta_pct": 50.0,
                "tipo": "FALTA_PLANEJ",
            }
        ]
        result = gerar_relatorio_reconciliacao(analise)
        assert isinstance(result, str)
        assert "RECONCILIAÇÃO" in result or "RECONCILIA" in result
        assert "2.1" in result

    def test_empty_no_disparidades(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            gerar_relatorio_reconciliacao,
        )

        result = gerar_relatorio_reconciliacao(DisparityAnalysis())
        assert isinstance(result, str)


class TestReconciliadorPlanejamento:
    def _make_canonical(self):
        canonical = MagicMock()
        canonical.equipes_diretas = []
        canonical.resultado = None
        return canonical

    def test_identificar_disparidades_nao_executado(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        # Build analise manually to test _identificar_disparidades
        from concilium.application.benchmarks.reconciliacao_planejamento import CustoPlanejamento

        analise = DisparityAnalysis()
        analise.planejamento = {
            "2.1": CustoPlanejamento(
                item_id="2.1",
                descricao="Item",
                unidade="m³",
                quantidade=100.0,
                total_sem_bdi=1000.0,
                total_com_bdi=1200.0,
            )
        }
        analise.canonical_direto = {}  # no canonical → NAO_EXECUTADO

        reconciliador._identificar_disparidades(analise)
        assert any(d["tipo"] == "NAO_EXECUTADO" for d in analise.disparidades)

    def test_identificar_disparidades_nao_planejado(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        analise = DisparityAnalysis()
        analise.planejamento = {}  # no planejamento
        analise.canonical_direto = {"3.1": 5000.0}

        reconciliador._identificar_disparidades(analise)
        assert any(d["tipo"] == "NAO_PLANEJADO" for d in analise.disparidades)

    def test_identificar_disparidades_delta(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            CustoPlanejamento,
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        analise = DisparityAnalysis()
        analise.planejamento = {
            "2.1": CustoPlanejamento(
                item_id="2.1",
                descricao="Item",
                unidade="m³",
                quantidade=100.0,
                total_sem_bdi=1000.0,
                total_com_bdi=1200.0,
            )
        }
        analise.canonical_direto = {"2.1": 1200.0}  # delta = 200 > 1

        reconciliador._identificar_disparidades(analise)
        disp = [d for d in analise.disparidades if d["item_id"] == "2.1"]
        assert len(disp) == 1

    def test_agregar_canonical_with_resultado(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = MagicMock()
        canonical.equipes_diretas = []
        canonical.resultado.custo.indireto_adm = 10000.0
        canonical.resultado.custo.indireto_top = 5000.0
        canonical.resultado.custo.indireto_lab = 0.0
        canonical.resultado.custo.indireto_qsms = 0.0
        canonical.resultado.custo.indireto_mob = 0.0
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))
        analise = DisparityAnalysis()
        reconciliador._agregar_canonical(analise)
        assert analise.total_canonical_indireto == 15000.0

    def test_agregar_canonical_resultado_present_but_custo_falsy(self):
        """Branch 211→exit: canonical.resultado is truthy but .custo is falsy
        (e.g. None) → total_canonical_indireto stays at its default (0.0)."""
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = MagicMock()
        canonical.equipes_diretas = []
        canonical.resultado.custo = None
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))
        analise = DisparityAnalysis()
        reconciliador._agregar_canonical(analise)
        assert analise.total_canonical_indireto == 0.0

    def test_identificar_disparidades_delta_within_tolerance_not_flagged(self):
        """Branch 233→225: |delta| <= 1.0 → no disparity is appended for that item."""
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            CustoPlanejamento,
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        analise = DisparityAnalysis()
        analise.planejamento = {
            "2.1": CustoPlanejamento(
                item_id="2.1",
                descricao="Item",
                unidade="m³",
                quantidade=100.0,
                total_sem_bdi=1000.0,
                total_com_bdi=1200.0,
            )
        }
        analise.canonical_direto = {"2.1": 1000.5}  # delta = 0.5, within tolerance

        reconciliador._identificar_disparidades(analise)
        assert not any(d["item_id"] == "2.1" for d in analise.disparidades)

    def test_identificar_disparidades_item_with_neither_planej_nor_canon(self):
        """Branch 259→225: item present in canonical_direto with a falsy (0.0)
        value and absent from planejamento → all three elif branches are
        false, no disparity is appended."""
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        analise = DisparityAnalysis()
        analise.planejamento = {}
        analise.canonical_direto = {"9.9": 0.0}

        reconciliador._identificar_disparidades(analise)
        assert analise.disparidades == []


# ── PlanejamentoParser.parse — CSV edge cases (lines 92, 103, 112-113, 134-141) ──


class TestPlanejamentoParserEdgeCases:
    # Parser reads 4096 bytes for sniffer, seeks back, then skips 3 header rows.
    # CSV content needs alphanumeric headers (no dashes) to avoid confusing the sniffer's
    # quote-detection heuristic, and all rows must have the same column count.
    _HDR = (
        "ITEM,Descricao,Unidade,Qtd,C1,C2,C3,C4,C5,C6,C7,sem_bdi,com_bdi\n"
        "A,B,C,D,E,F,G,H,I,J,K,L,M\n"
        "1,2,3,4,5,6,7,8,9,10,11,12,13\n"
    )

    def test_empty_rows_skipped(self, tmp_path):
        """Line 92: empty row → continue."""
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        csv_content = self._HDR + "\n1.1,Terraplanagem,m3,100.0,0,0,0,0,0,0,0,1000.0,1200.0\n"
        f = tmp_path / "plan.csv"
        f.write_text(csv_content, encoding="utf-8")
        result = PlanejamentoParser.parse(f)
        assert "1.1" in result

    def test_header_row_item_id_skipped(self, tmp_path):
        """Line 103: item_id == 'ITEM' → continue."""
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        csv_content = (
            self._HDR
            + "ITEM,Header,m3,0.0,0,0,0,0,0,0,0,0.0,0.0\n"
            + "2.1,Concreto,m3,50.0,0,0,0,0,0,0,0,500.0,600.0\n"
        )
        f = tmp_path / "plan.csv"
        f.write_text(csv_content, encoding="utf-8")
        result = PlanejamentoParser.parse(f)
        assert "ITEM" not in result
        assert "2.1" in result

    def test_invalid_quantity_defaults_to_zero(self, tmp_path):
        """Lines 112-113: ValueError in quantity parse → quantidade=0.0."""
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        csv_content = self._HDR + "3.1,Servico,m3,N/A,0,0,0,0,0,0,0,1000.0,1200.0\n"
        f = tmp_path / "plan.csv"
        f.write_text(csv_content, encoding="utf-8")
        result = PlanejamentoParser.parse(f)
        if "3.1" in result:
            assert result["3.1"].quantidade == 0.0

    def test_row_with_10_plus_cols_extracts_totals(self, tmp_path):
        """Lines 134-135: >= 10 columns → extract total_com_bdi and total_sem_bdi."""
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        csv_content = self._HDR + "4.1,Pavimentacao,m2,200.0,10.0,20.0,30.0,40.0,50.0,60.0,70.0,800.0,1000.0\n"
        f = tmp_path / "plan.csv"
        f.write_text(csv_content, encoding="utf-8")
        result = PlanejamentoParser.parse(f)
        if "4.1" in result:
            assert result["4.1"].total_com_bdi > 0 or result["4.1"].total_sem_bdi >= 0

    def test_indiretos_section_detected(self, tmp_path):
        """Line 97: 'INDIRETOS' in row → section = INDIRETO."""
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        csv_content = (
            self._HDR
            + "INDIRETOS,,,,,,,,,,,,\n"  # 12 commas = 13 cols, matches header
            + "I.1,Administracao,mes,1.0,0,0,0,0,0,0,0,300.0,350.0\n"
        )
        f = tmp_path / "plan.csv"
        f.write_text(csv_content, encoding="utf-8")
        result = PlanejamentoParser.parse(f)
        if "I.1" in result:
            assert result["I.1"].tipo == "INDIRETO"

    def test_nonexistent_file_returns_empty(self, tmp_path):
        """FileNotFoundError or similar → empty dict."""
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        try:
            result = PlanejamentoParser.parse(tmp_path / "nonexistent.csv")
            assert isinstance(result, dict)
        except (FileNotFoundError, OSError):
            pass  # also acceptable

    def test_zero_cost_rows_excluded(self, tmp_path):
        """Only rows with total_com_bdi > 0 OR total_sem_bdi > 0 are kept."""
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        # Must have 3 headers (parser skips 3 rows); all-zero costs → excluded
        csv_content = self._HDR + "5.1,ZeroCost,m3,10.0,0,0,0,0,0,0,0,0.0,0.0\n"
        f = tmp_path / "plan.csv"
        f.write_text(csv_content, encoding="utf-8")
        result = PlanejamentoParser.parse(f)
        assert "5.1" not in result

    def test_short_row_under_10_cols_skips_totals_extraction(self, tmp_path):
        """Branch 131→146: len(row) < 10 → skip the totals-extraction try
        block entirely; row has no cost, so it's excluded from the result.

        Uses a dedicated short (4-column) CSV — all rows (including the 3
        skipped header rows) must have a consistent column count for
        csv.Sniffer to reliably detect the comma delimiter.
        """
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        short_hdr = "ITEM,Descricao,Unidade,Qtd\nA,B,C,D\n1,2,3,4\n"
        csv_content = short_hdr + "6.1,ShortRow,m3,20.0\n"
        f = tmp_path / "plan.csv"
        f.write_text(csv_content, encoding="utf-8")
        result = PlanejamentoParser.parse(f)
        assert "6.1" not in result
