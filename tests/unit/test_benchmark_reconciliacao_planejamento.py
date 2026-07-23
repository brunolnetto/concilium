"""Tests for four 0%-coverage benchmark modules.

Covers:
  1. src/concilium/application/benchmarks/_chart_colors.py
  2. src/concilium/application/benchmarks/cronograma_parser.py
  3. src/concilium/application/benchmarks/reconciliacao_planejamento.py
  4. src/concilium/application/benchmarks/analise_llm_reconciliacao.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

# 3. reconciliacao_planejamento
# ---------------------------------------------------------------------------


class TestReconciliacaoParseValor:
    def _fn(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        return _parse_valor

    def test_none_returns_zero(self):
        assert self._fn()(None) == 0.0

    def test_dash_returns_zero(self):
        assert self._fn()("-") == 0.0

    def test_portuguese_currency_format(self):
        assert self._fn()("R$ 1.234,56") == 1234.56

    def test_valid_float_string(self):
        assert self._fn()("500,00") == 500.0

    def test_empty_string_returns_zero(self):
        assert self._fn()("") == 0.0


class TestCustoPlanejamento:
    def test_instantiate_minimal_fields(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import CustoPlanejamento

        cp = CustoPlanejamento(
            item_id="1.1",
            descricao="Escavação",
            quantidade=100.0,
            unidade="m³",
        )
        assert cp.item_id == "1.1"
        assert cp.descricao == "Escavação"
        assert cp.quantidade == 100.0
        assert cp.unidade == "m³"

    def test_tipo_defaults_to_direto(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import CustoPlanejamento

        cp = CustoPlanejamento(
            item_id="2.1",
            descricao="Aterro",
            quantidade=50.0,
            unidade="m³",
        )
        assert cp.tipo == "DIRETO"

    def test_numeric_fields_default_to_zero(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import CustoPlanejamento

        cp = CustoPlanejamento(item_id="x", descricao="d", quantidade=0.0, unidade="un")
        assert cp.mo_sem_bdi == 0.0
        assert cp.total_com_bdi == 0.0
        assert cp.bdi_pct == 0.0


class TestDisparityAnalysis:
    def test_instantiate_with_defaults(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import DisparityAnalysis

        da = DisparityAnalysis()
        assert da.planejamento == {}
        assert da.canonical_direto == {}
        assert da.canonical_indireto == {}
        assert da.disparidades == []
        assert da.total_planej_direto_sem_bdi == 0.0
        assert da.total_canonical_direto == 0.0

    def test_populate_fields(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import DisparityAnalysis

        da = DisparityAnalysis(total_canonical_direto=999.0)
        assert da.total_canonical_direto == 999.0


class TestPlanejamentoParserParse:
    def _build_tsv(self, tmp_path: Path, rows: list[str]) -> Path:
        """Create a TSV planejamento file with 3 header rows + provided data rows.

        Headers use realistic column names so csv.Sniffer can detect the tab delimiter.
        """
        # 11 columns: ITEM, DESC, UNID, QTD, MO, EQ, COMB, MAT, col8, TOTAL_SEM, TOTAL_COM
        content = (
            "ITEM\tDESCRICAO\tUNID\tQTD\tMO\tEQ\tCOMB\tMAT\tSUBTOTAL\tTOTAL_SEM_BDI\tTOTAL_COM_BDI\n"
            "ITEM\tDESCRICAO\tUNID\tQTD\tMO_BDI\tEQ_BDI\tCOMB_BDI\tMAT_BDI\tSUBT\tTOTAL_SEM\tTOTAL_COM\n"
            "ITEM\tDESCRICAO\tUNID\tQTD\tVALOR_MO\tVALOR_EQ\tVALOR_COMB\tVALOR_MAT\tVSUB\tSEM_BDI\tCOM_BDI\n"
        )
        content += "\n".join(rows)
        p = tmp_path / "planejamento.txt"
        p.write_text(content, encoding="utf-8")
        return p

    def test_returns_dict_of_custo_planejamento(self, tmp_path):
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        # The parser assigns: total_com_bdi = row[-2], total_sem_bdi = row[-3]
        # row: ITEM, DESC, UNID, QTD, col4, col5, col6, col7, col8(sem_bdi), col9(com_bdi), col10(last)
        # so row[-2] = col9 = total_com_bdi, row[-3] = col8 = total_sem_bdi
        row = "\t".join(["1.1", "Escavação", "m³", "100", "0", "0", "0", "0", "50000,00", "60000,00", "extra"])
        p = self._build_tsv(tmp_path, [row])
        result = PlanejamentoParser.parse(p)
        assert "1.1" in result
        cp = result["1.1"]
        assert cp.total_com_bdi == 60000.0
        assert cp.total_sem_bdi == 50000.0

    def test_zero_cost_items_excluded(self, tmp_path):
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        row = "\t".join(["2.1", "Serviço Zero", "m", "0", "0", "0", "0", "0", "0", "0", "0"])
        p = self._build_tsv(tmp_path, [row])
        result = PlanejamentoParser.parse(p)
        assert "2.1" not in result

    def test_indiretos_section_sets_tipo(self, tmp_path):
        from concilium.application.benchmarks.reconciliacao_planejamento import PlanejamentoParser

        rows = [
            "INDIRETOS\t\t\t\t\t\t\t\t\t\t",
            "\t".join(["ADM", "Administração", "vb", "1", "0", "0", "0", "0", "0", "10000,00", "12000,00"]),
        ]
        p = self._build_tsv(tmp_path, rows)
        result = PlanejamentoParser.parse(p)
        assert "ADM" in result
        assert result["ADM"].tipo == "INDIRETO"


class TestGerarRelatorioReconciliacao:
    def test_returns_string_containing_reconciliacao(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            gerar_relatorio_reconciliacao,
        )

        analise = DisparityAnalysis()
        result = gerar_relatorio_reconciliacao(analise)
        assert isinstance(result, str)
        assert "RECONCILIAÇÃO" in result

    def test_empty_disparidades_shows_nenhuma(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            gerar_relatorio_reconciliacao,
        )

        analise = DisparityAnalysis()
        result = gerar_relatorio_reconciliacao(analise)
        assert "Nenhuma disparidade > 5%" in result

    def test_disparidade_above_5pct_included_in_output(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            gerar_relatorio_reconciliacao,
        )

        analise = DisparityAnalysis(
            disparidades=[
                {
                    "item_id": "1.1",
                    "tipo": "FALTA_PLANEJ",
                    "descricao": "Escavação",
                    "planejamento_sem_bdi": 10000.0,
                    "planejamento_com_bdi": 12000.0,
                    "canonical": 20000.0,
                    "delta": 10000.0,
                    "delta_pct": 100.0,
                }
            ]
        )
        result = gerar_relatorio_reconciliacao(analise)
        assert "1.1" in result
        assert "Nenhuma disparidade > 5%" not in result


class TestReconciliadorPlanejamento:
    def test_analisar_returns_disparity_analysis(self, tmp_path):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        # Headers must include tabs so csv.Sniffer can detect the delimiter
        p = tmp_path / "planejamento.txt"
        p.write_text("H1\tA\tB\nH2\tC\tD\nH3\tE\tF\n", encoding="utf-8")

        mock_canonical = MagicMock()
        mock_canonical.equipes_diretas = []
        mock_canonical.resultado = None

        rec = ReconciliadorPlanejamento(canonical=mock_canonical, planejamento_path=p)
        result = rec.analisar()
        assert isinstance(result, DisparityAnalysis)

    def test_analisar_aggregates_equipes_diretas(self, tmp_path):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            ReconciliadorPlanejamento,
        )

        p = tmp_path / "planejamento.txt"
        p.write_text("H1\tA\tB\nH2\tC\tD\nH3\tE\tF\n", encoding="utf-8")

        eq = MagicMock()
        eq.item_id = "1.1"
        eq.custo_total = 5000.0
        eq.num_equipes_base = 2

        mock_canonical = MagicMock()
        mock_canonical.equipes_diretas = [eq]
        mock_canonical.resultado = None

        rec = ReconciliadorPlanejamento(canonical=mock_canonical, planejamento_path=p)
        result = rec.analisar()
        assert result.total_canonical_direto == 10000.0
        assert result.canonical_direto["1.1"] == 10000.0

