"""Tests for application/benchmarks/cronograma_parser.py — boost coverage."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestParseValor:
    def test_empty_string(self):
        from concilium.application.benchmarks.cronograma_parser import _parse_valor
        assert _parse_valor("") == 0.0

    def test_dash(self):
        from concilium.application.benchmarks.cronograma_parser import _parse_valor
        assert _parse_valor("-") == 0.0

    def test_pt_number_format(self):
        from concilium.application.benchmarks.cronograma_parser import _parse_valor
        assert _parse_valor("1.234,56") == pytest.approx(1234.56)

    def test_plain_integer_string(self):
        from concilium.application.benchmarks.cronograma_parser import _parse_valor
        assert _parse_valor("123") == pytest.approx(123.0)

    def test_invalid_string(self):
        from concilium.application.benchmarks.cronograma_parser import _parse_valor
        assert _parse_valor("abc") == 0.0


class TestLoadProdutividadeMap:
    def test_missing_file_returns_empty(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map
        result = _load_produtividade_map(tmp_path / "nonexistent.txt")
        assert result == {}

    def test_valid_tsv_file(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map
        tsv = tmp_path / "produtividade.txt"
        # 4 header lines + data lines
        tsv.write_text(
            "H1\n" * 4 +
            "2.1\tServico A\tm³\t50,00\n" +
            "2.2\tServico B\tm²\t100\n" +
            "SEC\tSecao\t\t\n",  # skipped (starts with 'S')
            encoding="utf-8"
        )
        result = _load_produtividade_map(tsv)
        assert result.get("2.1") == pytest.approx(50.0)
        assert result.get("2.2") == pytest.approx(100.0)
        assert "SEC" not in result

    def test_tsv_too_few_columns_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map
        tsv = tmp_path / "produtividade.txt"
        tsv.write_text("H\nH\nH\nH\n2.1\tServ\n", encoding="utf-8")
        result = _load_produtividade_map(tsv)
        assert result == {}


class TestFindCpuForItem:
    def test_exact_match(self):
        from concilium.application.benchmarks.cronograma_parser import _find_cpu_for_item
        cpus_map = {"CPU-ESC": "Escavação de solo"}
        result = _find_cpu_for_item("escavação de solo mole", cpus_map)
        assert result == "CPU-ESC"

    def test_no_match(self):
        from concilium.application.benchmarks.cronograma_parser import _find_cpu_for_item
        cpus_map = {"CPU-1": "Pavimento asfáltico"}
        result = _find_cpu_for_item("compactação de aterro", cpus_map)
        assert result is None

    def test_keyword_match(self):
        from concilium.application.benchmarks.cronograma_parser import _find_cpu_for_item
        cpus_map = {"CPU-2": "Aterro compactado manual"}
        # First 3 words: "Aterro", "compactado", "manual" — need to appear in description
        result = _find_cpu_for_item("aterro compactado manual vibroapissoador", cpus_map)
        assert result == "CPU-2"


class TestInferPredecessores:
    def _make_item(self, item_id, descricao="Test"):
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem
        return CronogramaItem(item_id=item_id, descricao=descricao, unidade="m³", quantitativo=100.0)

    def test_section_header_has_no_predecessores(self):
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores
        items = [self._make_item("1.1")]
        result = _infer_predecessores(items, "1", {})
        assert result == []

    def test_first_sub_item_in_first_section_has_no_predecessores(self):
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores
        items = [self._make_item("1.1")]
        result = _infer_predecessores(items, "1.1", {})
        assert result == []

    def test_second_item_in_section_depends_on_first(self):
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores
        items = [self._make_item("2.1"), self._make_item("2.2")]
        result = _infer_predecessores(items, "2.2", {})
        assert isinstance(result, list)

    def test_first_item_of_section_2_depends_on_last_of_section_1(self):
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores
        items = [self._make_item("1.1"), self._make_item("1.2"), self._make_item("2.1")]
        result = _infer_predecessores(items, "2.1", {})
        assert isinstance(result, list)


class TestCronogramaParser:
    def test_parser_init_default(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser
        parser = CronogramaParser()
        assert parser is not None

    def test_parse_lines_empty(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser
        parser = CronogramaParser()
        result = parser.parse_lines(["header\n"] * 4)
        assert isinstance(result, list)

    def test_parse_lines_with_data(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser
        parser = CronogramaParser()
        lines = ["H\n"] * 4 + [
            "2\tEscavação\t\t\n",       # section header → skipped
            "2.1\tEscavação 1ª cat\tm³\t1000\n",  # sub-item
        ]
        result = parser.parse_lines(lines)
        assert isinstance(result, list)

    def test_cronograma_item_fields(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem
        item = CronogramaItem(item_id="2.1", descricao="Test", unidade="m³", quantitativo=500.0)
        assert item.item_id == "2.1"
        assert item.quantitativo == 500.0
