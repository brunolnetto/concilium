"""Tests for four 0%-coverage benchmark modules.

Covers:
  1. src/concilium/application/benchmarks/_chart_colors.py
  2. src/concilium/application/benchmarks/cronograma_parser.py
  3. src/concilium/application/benchmarks/reconciliacao_planejamento.py
  4. src/concilium/application/benchmarks/analise_llm_reconciliacao.py
  5. src/concilium/application/benchmarks/spec/spec_loader/_host_protocol.py
"""

from __future__ import annotations

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
            "HEADER1\nHEADER2\nHEADER3\nITEM\tSERVIÇO\tUNID\tPRODUÇÃO HORARIA\n2.1\tEscavação\tm³\t12,50\n",
            encoding="utf-8",
        )
        result = self._fn()(tsv_file)
        assert "2.1" in result
        assert result["2.1"] == 12.50

    def test_malformed_line_skipped(self, tmp_path):
        # line with fewer than 4 parts after header
        tsv_file = tmp_path / "produtividade.txt"
        tsv_file.write_text(
            "H\nH\nH\nH\nonly_two\tcolumns\n3.1\tOk\tm²\t5,0\n",
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
            "H\nH\nH\nH\nTOTAL\tAgg\t-\t999\n",
            encoding="utf-8",
        )
        result = self._fn()(tsv_file)
        assert result == {}


class TestInferPredecessores:
    def _fn(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem, _infer_predecessores

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

        lines = self._make_lines(
            [
                "1\tObra\t\t\t\t\n",  # section header → skipped
                "1.1\tEscavação\tm³\t100,0\t5,0\t40,0\n",
            ]
        )
        parser = CronogramaParser(cpus_map={"CPU-ESC": "Escavação"})
        items = parser.parse_lines(lines)
        assert len(items) == 1
        assert items[0]["item_id"] == "1.1"
        assert items[0]["quantitativo"] == 100.0
        assert items[0]["cpu_id"] == "CPU-ESC"

    def test_items_with_zero_quantitativo_excluded(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        lines = self._make_lines(
            [
                "1.1\tServico A\tm³\t0\t\t\n",
                "1.2\tServico B\tm³\t50\t\t\n",
            ]
        )
        parser = CronogramaParser()
        items = parser.parse_lines(lines)
        item_ids = [i["item_id"] for i in items]
        assert "1.1" not in item_ids
        assert "1.2" in item_ids

    def test_lines_with_missing_fields_handled_gracefully(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        # Line with only 1 part (< 3) → skipped without error
        lines = self._make_lines(
            [
                "only_one_field\n",
                "1.1\tOK\tm\t10\t\t\n",
            ]
        )
        parser = CronogramaParser()
        items = parser.parse_lines(lines)
        assert len(items) == 1

    def test_section_headers_skipped(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        lines = self._make_lines(
            [
                "2\tSeção 2\t\t\t\t\n",
                "2.1\tServico\tm\t20\t\t\n",
            ]
        )
        parser = CronogramaParser()
        items = parser.parse_lines(lines)
        item_ids = [i["item_id"] for i in items]
        assert "2" not in item_ids
        assert "2.1" in item_ids

    def test_unknown_cpu_falls_back_to_cpu_unknown(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        lines = self._make_lines(
            [
                "1.1\tAlgum Serviço Desconhecido\tm\t10\t\t\n",
            ]
        )
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
            "CODIGO\tDESCRICAO\nCPU-001\tEscavação em solo\nCPU-002\tAterro compactado\n",
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
            "CODIGO\tDESCRICAO\n\tDescricao Sem Codigo\nCPU-003\tValido\n",
            encoding="utf-8",
        )
        result = CronogramaParser.load_cpus_map(cpus_file)
        assert "CPU-003" in result
        assert "" not in result


# ---------------------------------------------------------------------------
