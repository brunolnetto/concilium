"""Tests for four 0%-coverage benchmark modules.

Covers:
  1. src/concilium/application/benchmarks/_chart_colors.py
  2. src/concilium/application/benchmarks/cronograma_parser.py
  3. src/concilium/application/benchmarks/reconciliacao_planejamento.py
  4. src/concilium/application/benchmarks/analise_llm_reconciliacao.py
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. _chart_colors
# ---------------------------------------------------------------------------

class TestChartColors:
    def test_cores_is_dict_with_at_least_10_keys(self):
        from concilium.application.benchmarks.charts._chart_colors import _CORES

        assert isinstance(_CORES, dict)
        assert len(_CORES) >= 10

    def test_cores_values_are_hex_strings(self):
        from concilium.application.benchmarks.charts._chart_colors import _CORES

        for key, value in _CORES.items():
            assert isinstance(value, str), f"Expected str for key {key!r}, got {type(value)}"
            assert value.startswith("#"), f"Value for {key!r} should start with '#': {value!r}"

    def test_bg_is_string_starting_with_hash(self):
        from concilium.application.benchmarks.charts._chart_colors import BG

        assert isinstance(BG, str)
        assert BG.startswith("#")


# ---------------------------------------------------------------------------
# 2. cronograma_parser
# ---------------------------------------------------------------------------

class TestCronogramaParserParseValor:
    def _fn(self):
        from concilium.application.benchmarks.cronograma_parser import _parse_valor
        return _parse_valor

    def test_empty_string_returns_zero(self):
        assert self._fn()("") == 0.0

    def test_dash_returns_zero(self):
        assert self._fn()("-") == 0.0

    def test_portuguese_format(self):
        assert self._fn()("1.234,56") == 1234.56

    def test_simple_integer_string(self):
        assert self._fn()("100") == 100.0

    def test_invalid_string_returns_zero(self):
        assert self._fn()("abc") == 0.0


class TestFindCpuForItem:
    def _fn(self):
        from concilium.application.benchmarks.cronograma_parser import _find_cpu_for_item
        return _find_cpu_for_item

    def test_exact_substring_match_returns_cpu_id(self):
        cpus_map = {"CPU-001": "Escavação em rocha"}
        result = self._fn()("Escavação em rocha compacta", cpus_map)
        assert result == "CPU-001"

    def test_keyword_match_first_three_words(self):
        # cpu_desc "corte e aterro de solo" → first 3 words "corte", "e", "aterro"
        # all three appear in the description
        cpus_map = {"CPU-002": "corte e aterro de solo"}
        result = self._fn()("serviço de corte e aterro", cpus_map)
        assert result == "CPU-002"

    def test_no_match_returns_none(self):
        cpus_map = {"CPU-003": "serviço completamente diferente"}
        result = self._fn()("escavação hidráulica", cpus_map)
        assert result is None


class TestLoadProdutividadeMap:
    def _fn(self):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map
        return _load_produtividade_map

    def test_nonexistent_path_returns_empty(self, tmp_path):
        result = self._fn()(tmp_path / "no_such_file.txt")
        assert result == {}

    def test_valid_tsv_parsed_correctly(self, tmp_path):
        # 4 header lines then a data row
        tsv_file = tmp_path / "produtividade.txt"
        tsv_file.write_text(
            "HEADER1\n"
            "HEADER2\n"
            "HEADER3\n"
            "ITEM\tSERVIÇO\tUNID\tPRODUÇÃO HORARIA\n"
            "2.1\tEscavação\tm³\t12,50\n",
            encoding="utf-8",
        )
        result = self._fn()(tsv_file)
        assert "2.1" in result
        assert result["2.1"] == 12.50

    def test_malformed_line_skipped(self, tmp_path):
        # line with fewer than 4 parts after header
        tsv_file = tmp_path / "produtividade.txt"
        tsv_file.write_text(
            "H\nH\nH\nH\n"
            "only_two\tcolumns\n"
            "3.1\tOk\tm²\t5,0\n",
            encoding="utf-8",
        )
        result = self._fn()(tsv_file)
        # "only_two" is skipped (< 4 parts), "3.1" parsed
        assert "only_two" not in result
        assert "3.1" in result
        assert result["3.1"] == 5.0

    def test_non_numeric_item_id_skipped(self, tmp_path):
        tsv_file = tmp_path / "produtividade.txt"
        tsv_file.write_text(
            "H\nH\nH\nH\n"
            "TOTAL\tAgg\t-\t999\n",
            encoding="utf-8",
        )
        result = self._fn()(tsv_file)
        assert result == {}


class TestInferPredecessores:
    def _fn(self):
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores, CronogramaItem
        return _infer_predecessores, CronogramaItem

    def _item(self, item_id, CronogramaItem):
        return CronogramaItem(
            item_id=item_id,
            descricao="desc",
            unidade="m³",
            quantitativo=10.0,
        )

    def test_section_header_returns_empty(self):
        fn, CI = self._fn()
        result = fn([], "2", {})
        assert result == []

    def test_first_item_overall_no_predecessors(self):
        fn, CI = self._fn()
        items = [self._item("1.1", CI)]
        result = fn(items, "1.1", {})
        assert result == []

    def test_first_item_in_section_2_depends_on_last_of_section_1(self):
        fn, CI = self._fn()
        items = [
            self._item("1.1", CI),
            self._item("1.2", CI),
            self._item("2.1", CI),
        ]
        result = fn(items, "2.1", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "1.2"
        assert result[0]["tipo"] == "FS"

    def test_second_item_in_section_depends_on_first(self):
        fn, CI = self._fn()
        items = [
            self._item("2.1", CI),
            self._item("2.2", CI),
        ]
        result = fn(items, "2.2", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "2.1"

    def test_gap_in_numbering_uses_last_existing(self):
        # 2.3 exists, 2.2 does not → should fall back to 2.1
        fn, CI = self._fn()
        items = [
            self._item("2.1", CI),
            self._item("2.3", CI),
        ]
        result = fn(items, "2.3", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "2.1"


class TestCronogramaParserParseLines:
    def _make_lines(self, data_rows):
        """Build a list of lines with 4 header lines then data."""
        headers = [
            "ITEM\tDESCRIÇÃO\tUNID\tQTD\tPROD_H\tPROD_D\n",
            "h2\n",
            "h3\n",
            "h4\n",
        ]
        return headers + data_rows

    def test_basic_parse_returns_eap_items(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        lines = self._make_lines([
            "1\tObra\t\t\t\t\n",           # section header → skipped
            "1.1\tEscavação\tm³\t100,0\t5,0\t40,0\n",
        ])
        parser = CronogramaParser(cpus_map={"CPU-ESC": "Escavação"})
        items = parser.parse_lines(lines)
        assert len(items) == 1
        assert items[0]["item_id"] == "1.1"
        assert items[0]["quantitativo"] == 100.0
        assert items[0]["cpu_id"] == "CPU-ESC"

    def test_items_with_zero_quantitativo_excluded(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        lines = self._make_lines([
            "1.1\tServico A\tm³\t0\t\t\n",
            "1.2\tServico B\tm³\t50\t\t\n",
        ])
        parser = CronogramaParser()
        items = parser.parse_lines(lines)
        item_ids = [i["item_id"] for i in items]
        assert "1.1" not in item_ids
        assert "1.2" in item_ids

    def test_lines_with_missing_fields_handled_gracefully(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        # Line with only 1 part (< 3) → skipped without error
        lines = self._make_lines([
            "only_one_field\n",
            "1.1\tOK\tm\t10\t\t\n",
        ])
        parser = CronogramaParser()
        items = parser.parse_lines(lines)
        assert len(items) == 1

    def test_section_headers_skipped(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        lines = self._make_lines([
            "2\tSeção 2\t\t\t\t\n",
            "2.1\tServico\tm\t20\t\t\n",
        ])
        parser = CronogramaParser()
        items = parser.parse_lines(lines)
        item_ids = [i["item_id"] for i in items]
        assert "2" not in item_ids
        assert "2.1" in item_ids

    def test_unknown_cpu_falls_back_to_cpu_unknown(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        lines = self._make_lines([
            "1.1\tAlgum Serviço Desconhecido\tm\t10\t\t\n",
        ])
        parser = CronogramaParser(cpus_map={})
        items = parser.parse_lines(lines)
        assert items[0]["cpu_id"] == "CPU-UNKNOWN"


class TestCronogramaParserLoadCpusMap:
    def test_nonexistent_path_returns_empty(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        result = CronogramaParser.load_cpus_map(tmp_path / "no_file.txt")
        assert result == {}

    def test_valid_tsv_returns_dict(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        cpus_file = tmp_path / "cpus.txt"
        cpus_file.write_text(
            "CODIGO\tDESCRICAO\n"
            "CPU-001\tEscavação em solo\n"
            "CPU-002\tAterro compactado\n",
            encoding="utf-8",
        )
        result = CronogramaParser.load_cpus_map(cpus_file)
        assert result == {
            "CPU-001": "Escavação em solo",
            "CPU-002": "Aterro compactado",
        }

    def test_rows_without_both_fields_excluded(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        cpus_file = tmp_path / "cpus.txt"
        # second row has empty codigo
        cpus_file.write_text(
            "CODIGO\tDESCRICAO\n"
            "\tDescricao Sem Codigo\n"
            "CPU-003\tValido\n",
            encoding="utf-8",
        )
        result = CronogramaParser.load_cpus_map(cpus_file)
        assert "CPU-003" in result
        assert "" not in result


# ---------------------------------------------------------------------------
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
            ReconciliadorPlanejamento,
            PlanejamentoParser,
            DisparityAnalysis,
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
            DisparityAnalysis,
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


