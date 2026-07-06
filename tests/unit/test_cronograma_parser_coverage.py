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
        from unittest.mock import patch

        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map

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

    def test_blank_line_within_data_is_skipped(self, tmp_path):
        from concilium.application.benchmarks.cronograma_parser import _load_produtividade_map

        tsv = tmp_path / "produtividade.txt"
        tsv.write_text("H\nH\nH\nH\n\n2.1\tServico\tunid\t10,0\n", encoding="utf-8")
        result = _load_produtividade_map(tsv)
        assert "2.1" in result


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

    def test_first_item_of_section_skips_malformed_ids_in_prev_section(self):
        """1º item da seção 2 (item_num==1); seção 1 tem item malformado (1.X) e um
        item válido (1.2) — deve ignorar o malformado e usar 1.2 como predecessor."""
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem, _infer_predecessores

        bad = CronogramaItem(item_id="1.X", descricao="Bad", unidade="m", quantitativo=1.0)
        good = CronogramaItem(item_id="1.2", descricao="Good", unidade="m", quantitativo=1.0)
        items = [bad, good]
        result = _infer_predecessores(items, "2.1", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "1.2"

    def test_first_item_of_section_prev_section_out_of_order_keeps_max(self):
        """1º item da seção 2; seção 1 tem itens fora de ordem (1.5 antes de 1.2)
        — o item de menor número não deve sobrescrever o max já encontrado
        (cobre o ramo False de `prev_num > max_prev_num`)."""
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem, _infer_predecessores

        items = [
            CronogramaItem(item_id="1.5", descricao="Fifth", unidade="m", quantitativo=1.0),
            CronogramaItem(item_id="1.2", descricao="Second", unidade="m", quantitativo=1.0),
        ]
        result = _infer_predecessores(items, "2.1", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "1.5"

    def test_no_prev_in_section_fallback_prev_section_out_of_order_keeps_max(self):
        """item_num > 1, sem item anterior na própria seção → cai no fallback
        para a última item da seção anterior; itens fora de ordem na seção
        anterior cobrem o ramo False de `prev_num > max_prev_num` no 2º bloco."""
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem, _infer_predecessores

        items = [
            CronogramaItem(item_id="1.5", descricao="Fifth", unidade="m", quantitativo=1.0),
            CronogramaItem(item_id="1.2", descricao="Second", unidade="m", quantitativo=1.0),
            CronogramaItem(item_id="2.3", descricao="Third of section 2", unidade="m", quantitativo=1.0),
        ]
        result = _infer_predecessores(items, "2.3", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "1.5"

    def test_invalid_item_parts_in_section_do_not_crash(self):
        """Items with non-integer sub-ids in same section are silently skipped."""
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem, _infer_predecessores

        # Build an item with a non-numeric second part to hit ValueError branch
        bad = CronogramaItem(item_id="2.X", descricao="Bad", unidade="m", quantitativo=1.0)
        good = CronogramaItem(item_id="2.1", descricao="Good", unidade="m", quantitativo=1.0)
        items = [good, bad]
        # Should not raise even with "2.X" in items
        result = _infer_predecessores(items, "2.2", {})
        assert isinstance(result, list)

    def test_item_num_gt1_fallback_to_prev_section_skips_malformed_ids(self):
        """item_num > 1, no direct predecessor in its own section (2.1/2.2 absent),
        falls back to the previous section — which itself contains a malformed
        id ("1.X") that must be skipped via the ValueError branch while a valid
        one ("1.2") is still picked as the predecessor."""
        from concilium.application.benchmarks.cronograma_parser import CronogramaItem, _infer_predecessores

        bad = CronogramaItem(item_id="1.X", descricao="Bad", unidade="m", quantitativo=1.0)
        good = CronogramaItem(item_id="1.2", descricao="Good", unidade="m", quantitativo=1.0)
        items = [bad, good, self._item("2.3")]
        result = _infer_predecessores(items, "2.3", {})
        assert len(result) == 1
        assert result[0]["item_id"] == "1.2"


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

    def test_three_part_item_id_neither_section_nor_subitem_ignored(self):
        """item_id like '2.1.1' is neither a section header (1 part) nor a
        sub-item (2 parts) — falls through with no action taken."""
        from concilium.application.benchmarks.cronograma_parser import CronogramaParser

        parser = CronogramaParser()
        lines = ["H\n"] * 4 + [
            "2.1.1\tSub-sub item\tm³\t100\n",  # 3 parts → falls through, ignored
            "2.2\tServico B\tm³\t50\n",
        ]
        result = parser.parse_lines(lines)
        ids = [r["item_id"] for r in result]
        assert "2.1.1" not in ids
        assert "2.2" in ids
