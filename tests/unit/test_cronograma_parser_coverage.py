"""Tests targeting missing lines in concilium/application/benchmarks/cronograma_parser.py.

Covers:
- _load_produtividade_map: invalid float value (logger.debug path), exception branch (logger.warning)
- _infer_predecessores: item_num > 1, no previous item in section fallback to prev section,
  no prev section when item_num > 1, ValueError in item_ids_in_section build
- CronogramaParser.parse_file
- CronogramaParser.load_cpus_map: file missing, valid file
- parse_lines: duplicate item_ids, zero-quantity items, lines with < 3 parts,
  empty item_id, producao fields filled
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# _load_produtividade_map edge cases
# ---------------------------------------------------------------------------


class TestLoadProdutividadeMapEdgeCases:
    def test_invalid_float_value_is_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map

        tsv = tmp_path / "produtividade.txt"
        # 4 header lines; item with invalid float in column 3
        tsv.write_text("H\nH\nH\nH\n2.1\tServico\tunid\tNOT_A_NUMBER\n", encoding="utf-8")
        result = _load_produtividade_map(tsv)
        # Item should be silently skipped, not raise
        assert "2.1" not in result

    def test_exception_reading_file_returns_empty(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map
        from unittest.mock import patch

        tsv = tmp_path / "produtividade.txt"
        tsv.write_text("H\nH\nH\nH\n", encoding="utf-8")
        # Simulate IO error during read
        with patch("builtins.open", side_effect=OSError("disk error")):
            result = _load_produtividade_map(tsv)
        assert result == {}

    def test_line_starting_with_non_digit_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map

        tsv = tmp_path / "produtividade.txt"
        tsv.write_text("H\nH\nH\nH\nTOTAL\tServico\tunid\t10,0\n", encoding="utf-8")
        result = _load_produtividade_map(tsv)
        assert "TOTAL" not in result

    def test_empty_item_id_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map

        tsv = tmp_path / "produtividade.txt"
        tsv.write_text("H\nH\nH\nH\n\tServico\tunid\t10,0\n", encoding="utf-8")
        result = _load_produtividade_map(tsv)
        assert result == {}


# ---------------------------------------------------------------------------
# _infer_predecessores — additional branches
# ---------------------------------------------------------------------------


class TestInferPredecessoresAdditional:
    def _item(self, item_id):
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem

        return CronogramaItem(item_id=item_id, descricao="X", unidade="m³", quantitativo=10.0)

    def test_item_num_gt1_no_prev_in_section_falls_back_to_prev_section(self):
        """When item 2.3 exists but 2.1 and 2.2 don't, find last item in section 1."""
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores

        items = [self._item("1.1"), self._item("1.2"), self._item("2.3")]
        result = _infer_predecessores(items, "2.3", {})
        # No 2.1 or 2.2 exist, so falls back to 1.2 (last of section 1)
        assert len(result) == 1
        assert result[0]["item_id"] == "1.2"

    def test_item_num_gt1_no_prev_section_either(self):
        """item 1.3 exists but 1.1 and 1.2 don't → no predecessors."""
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores

        items = [self._item("1.3")]
        result = _infer_predecessores(items, "1.3", {})
        assert result == []

    def test_item_num_gt1_prev_found_in_section_with_gap(self):
        """2.3 exists, 2.1 exists, 2.2 doesn't → predecessor is 2.1."""
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores

        items = [self._item("2.1"), self._item("2.3")]
        result = _infer_predecessores(items, "2.3", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "2.1"

    def test_first_item_section1_no_predecessors(self):
        """1.1 has no predecessors — section == 1 branch."""
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores

        items = [self._item("1.1")]
        result = _infer_predecessores(items, "1.1", {})
        assert result == []

    def test_first_item_section2_previous_section_has_no_matching_items(self):
        """2.1 first of section 2, section 1 has no matching items → no predecessors."""
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores

        items = [self._item("2.1")]
        result = _infer_predecessores(items, "2.1", {})
        # section 1 has no items, so no predecessor
        assert result == []

    def test_invalid_item_parts_in_section_do_not_crash(self):
        """Items with non-integer sub-ids in same section are silently skipped."""
        from concilium.application.benchmarks.cronograma_parser import _infer_predecessores, CronogramaItem

        # Build an item with a non-numeric second part to hit ValueError branch
        bad = CronogramaItem(item_id="2.X", descricao="Bad", unidade="m", quantitativo=1.0)
        good = CronogramaItem(item_id="2.1", descricao="Good", unidade="m", quantitativo=1.0)
        items = [good, bad]
        # Should not raise even with "2.X" in items
        result = _infer_predecessores(items, "2.2", {})
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# CronogramaParser.parse_file
# ---------------------------------------------------------------------------


class TestCronogramaParserParseFile:
    def test_parse_file_reads_and_delegates(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        content = "H\nH\nH\nH\n2\tEscavação\t\t\n2.1\tEscavação mole\tm³\t500\n"
        f = tmp_path / "cronograma.txt"
        f.write_text(content, encoding="utf-8")

        parser = CronogramaParser()
        result = parser.parse_file(f)
        assert isinstance(result, list)
        assert any(item["item_id"] == "2.1" for item in result)

    def test_parse_file_empty_data(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        f = tmp_path / "cronograma.txt"
        f.write_text("H\nH\nH\nH\n", encoding="utf-8")
        parser = CronogramaParser()
        result = parser.parse_file(f)
        assert result == []


# ---------------------------------------------------------------------------
# CronogramaParser.load_cpus_map
# ---------------------------------------------------------------------------


class TestLoadCpusMap:
    def test_missing_file_returns_empty(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        result = CronogramaParser.load_cpus_map(tmp_path / "nonexistent.txt")
        assert result == {}

    def test_valid_tsv_file(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        cpus = tmp_path / "cpus.txt"
        cpus.write_text("CODIGO\tDESCRICAO\nCPU-ESC\tEscavação\nCPU-ATR\tAterro\n", encoding="utf-8")
        result = CronogramaParser.load_cpus_map(cpus)
        assert result["CPU-ESC"] == "Escavação"
        assert result["CPU-ATR"] == "Aterro"

    def test_row_with_empty_codigo_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        cpus = tmp_path / "cpus.txt"
        cpus.write_text("CODIGO\tDESCRICAO\n\tEscavação\nCPU-OK\tOk\n", encoding="utf-8")
        result = CronogramaParser.load_cpus_map(cpus)
        assert "" not in result
        assert "CPU-OK" in result

    def test_row_with_empty_descricao_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        cpus = tmp_path / "cpus.txt"
        cpus.write_text("CODIGO\tDESCRICAO\nCPU-EMPTY\t\nCPU-OK\tOk\n", encoding="utf-8")
        result = CronogramaParser.load_cpus_map(cpus)
        assert "CPU-EMPTY" not in result

    def test_row_with_too_few_columns_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        cpus = tmp_path / "cpus.txt"
        cpus.write_text("CODIGO\tDESCRICAO\nCPU-ALONE\n", encoding="utf-8")
        result = CronogramaParser.load_cpus_map(cpus)
        assert "CPU-ALONE" not in result


# ---------------------------------------------------------------------------
# parse_lines — additional branches
# ---------------------------------------------------------------------------


class TestParseLinesBranches:
    def test_duplicate_item_ids_deduped(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser()
        lines = ["H\n"] * 4 + [
            "2.1\tServico A\tm³\t100\n",
            "2.1\tServico A duplicado\tm³\t200\n",  # dup → kept first
        ]
        result = parser.parse_lines(lines)
        items_21 = [r for r in result if r["item_id"] == "2.1"]
        assert len(items_21) == 1
        assert items_21[0]["descricao"] == "Servico A"

    def test_zero_quantitativo_item_excluded(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser()
        lines = ["H\n"] * 4 + [
            "2.1\tServico A\tm³\t0\n",  # quantitativo = 0 → excluded
        ]
        result = parser.parse_lines(lines)
        assert result == []

    def test_line_with_too_few_parts_skipped(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser()
        lines = ["H\n"] * 4 + [
            "2.1\tServico\n",  # only 2 parts (< 3) → skipped
            "2.2\tServico B\tm³\t50\n",
        ]
        result = parser.parse_lines(lines)
        ids = [r["item_id"] for r in result]
        assert "2.1" not in ids
        assert "2.2" in ids

    def test_empty_item_id_line_skipped(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser()
        lines = ["H\n"] * 4 + [
            "\tServico\tm³\t100\n",  # empty item_id → skipped
        ]
        result = parser.parse_lines(lines)
        assert result == []

    def test_producao_fields_parsed(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser()
        # col0=item_id, col1=desc, col2=unid, col3=quant, col4=prod_horaria, col5=prod_diaria
        lines = ["H\n"] * 4 + [
            "1.1\tServico X\tm³\t500\t2,5\t20,0\n",
        ]
        result = parser.parse_lines(lines)
        assert len(result) == 1

    def test_cpu_mapping_applied(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser(cpus_map={"CPU-ESC": "servico x"})
        lines = ["H\n"] * 4 + ["1.1\tServico X\tm³\t100\n"]
        result = parser.parse_lines(lines)
        assert result[0]["cpu_id"] == "CPU-ESC"

    def test_unknown_cpu_maps_to_unknown(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser(cpus_map={})
        lines = ["H\n"] * 4 + ["1.1\tServico Qualquer\tm³\t100\n"]
        result = parser.parse_lines(lines)
        assert result[0]["cpu_id"] == "CPU-UNKNOWN"

    def test_empty_line_within_data_skipped(self):
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser()
        lines = ["H\n"] * 4 + [
            "\n",  # empty line → continue
            "1.1\tServico\tm³\t100\n",
        ]
        result = parser.parse_lines(lines)
        assert len(result) == 1
