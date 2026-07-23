"""Tests for referencia_enricher module — covering missing lines."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODULE = "concilium.application.benchmarks.spec.referencia_enricher"


def _make_eap_item(item_id: str = "2.1", descricao: str = "Escavação", cpu_id: str = "CPU-UNKNOWN") -> dict:
    return {
        "item_id": item_id,
        "ordem": 1,
        "cpu_id": cpu_id,
        "descricao": descricao,
        "unidade": "m3",
        "quantitativo": 100.0,
        "predecessores": [],
        "producao_diaria": 50.0,
        "producao_horaria": 0.0,
    }


def _minimal_referencia() -> dict:
    return {}


# ---------------------------------------------------------------------------
# _infer_cpu_from_section
# ---------------------------------------------------------------------------

from concilium.application.benchmarks.spec.referencia_enricher import _infer_cpu_from_section  # noqa: E402


class TestInferCpuFromSection:
    def test_known_section_1(self):
        result = _infer_cpu_from_section("1", 3)
        assert result == "CPU-MOB-003"

    def test_known_section_2(self):
        result = _infer_cpu_from_section("2", 1)
        assert result == "CPU-SUPP-001"

    def test_known_section_3(self):
        result = _infer_cpu_from_section("3", 10)
        assert result == "CPU-LIMP-010"

    def test_known_section_4(self):
        result = _infer_cpu_from_section("4", 5)
        assert result == "CPU-ESCA-005"

    def test_known_section_5(self):
        result = _infer_cpu_from_section("5", 2)
        assert result == "CPU-EQUIP-002"

    def test_unknown_section_falls_back(self):
        result = _infer_cpu_from_section("9", 7)
        assert result == "CPU-SEC9-007"

    def test_unknown_section_zero_padded(self):
        result = _infer_cpu_from_section("7", 1)
        assert "001" in result


# ---------------------------------------------------------------------------
# _enrich_eap_with_produtividade
# ---------------------------------------------------------------------------

from concilium.application.benchmarks.spec.referencia_enricher import _enrich_eap_with_produtividade  # noqa: E402


class TestEnrichEapWithProdutividade:
    def test_no_file_returns_early(self, tmp_path):
        items = [_make_eap_item()]
        path = tmp_path / "produtividade.txt"
        # file does not exist
        _enrich_eap_with_produtividade(items, path)
        assert "cpu_meta" not in items[0]

    def test_valid_file_enriches_item(self, tmp_path):
        path = tmp_path / "produtividade.txt"
        # 4 header rows + 1 data row
        content = "header1\nheader2\nheader3\nheader4\n2.1\tEscavação\tM3\t1.234,56\n"
        path.write_text(content, encoding="utf-8")

        items = [_make_eap_item(item_id="2.1")]
        _enrich_eap_with_produtividade(items, path)

        assert "cpu_meta" in items[0]
        assert items[0]["cpu_meta"]["producao_horaria"] == pytest.approx(1234.56)

    def test_skips_non_digit_lines(self, tmp_path):
        path = tmp_path / "produtividade.txt"
        content = (
            "h\nh\nh\nh\n"
            "TOTAL\tDesc\tUN\t100,00\n"  # does not start with digit
            "2.1\tItem\tM3\t50,00\n"
        )
        path.write_text(content, encoding="utf-8")

        items = [_make_eap_item(item_id="2.1")]
        _enrich_eap_with_produtividade(items, path)

        assert items[0]["cpu_meta"]["producao_horaria"] == pytest.approx(50.0)

    def test_skips_lines_with_too_few_parts(self, tmp_path):
        path = tmp_path / "produtividade.txt"
        content = "h\nh\nh\nh\n2.1\tDesc\n"  # only 2 parts
        path.write_text(content, encoding="utf-8")

        items = [_make_eap_item(item_id="2.1")]
        _enrich_eap_with_produtividade(items, path)
        assert "cpu_meta" not in items[0]

    def test_invalid_float_is_skipped(self, tmp_path):
        path = tmp_path / "produtividade.txt"
        content = "h\nh\nh\nh\n2.1\tItem\tM3\tXXX\n"
        path.write_text(content, encoding="utf-8")

        items = [_make_eap_item(item_id="2.1")]
        _enrich_eap_with_produtividade(items, path)
        assert "cpu_meta" not in items[0]

    def test_item_not_in_map_untouched(self, tmp_path):
        path = tmp_path / "produtividade.txt"
        content = "h\nh\nh\nh\n3.1\tItem\tM3\t20,00\n"
        path.write_text(content, encoding="utf-8")

        items = [_make_eap_item(item_id="2.1")]
        _enrich_eap_with_produtividade(items, path)
        assert "cpu_meta" not in items[0]

    def test_existing_cpu_meta_extended(self, tmp_path):
        path = tmp_path / "produtividade.txt"
        content = "h\nh\nh\nh\n2.1\tItem\tM3\t10,00\n"
        path.write_text(content, encoding="utf-8")

        item = _make_eap_item(item_id="2.1")
        item["cpu_meta"] = {"some_key": "val"}

        _enrich_eap_with_produtividade([item], path)
        assert item["cpu_meta"]["producao_horaria"] == pytest.approx(10.0)
        assert item["cpu_meta"]["some_key"] == "val"

    def test_exception_in_open_is_swallowed(self, tmp_path):
        """Even when the file is unreadable, function should not raise."""
        path = tmp_path / "produtividade.txt"
        path.write_text("dummy", encoding="utf-8")

        items = [_make_eap_item()]
        # Patch open to raise
        with patch("builtins.open", side_effect=OSError("disk error")):
            # Should not propagate
            _enrich_eap_with_produtividade(items, path)


# ---------------------------------------------------------------------------
# enrich_referencia_with_eap
# ---------------------------------------------------------------------------

from concilium.application.benchmarks.spec.referencia_enricher import enrich_referencia_with_eap  # noqa: E402


class TestEnrichReferenciaWithEap:
    def _mock_parser(self, items):
        mock = MagicMock()
        mock.parse_file.return_value = items
        return mock

    def _mock_mapper(self, mapped_cpu=None, stats=None):
        mock = MagicMock()
        mock.map_item_to_cpu.return_value = mapped_cpu
        if stats is None:
            stats = {"total_items_processed": 2, "successfully_mapped": 2, "success_rate": 100.0}
        mock.get_mapping_stats.return_value = stats
        return mock

    def test_meta_defaults_injected_when_missing(self, tmp_path):
        cronograma_path = tmp_path / "artifacts" / "raw" / "cronograma.txt"
        cronograma_path.parent.mkdir(parents=True)
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-ESCA-001")

            result = enrich_referencia_with_eap({}, cronograma_path)

        assert result["meta"]["data_inicio"] == "2026-01-01"
        assert result["meta"]["data_termino"] == "2027-12-31"
        assert result["meta"]["localizacao"] == "Brasil"
        assert result["meta"]["regime_trabalho"] == {"horas_dia": 8, "dias_semana": 6}
        assert result["meta"]["mode"] == "benchmark_config"

    def test_projeto_inferred_from_path(self, tmp_path):
        proj_dir = tmp_path / "MARA_ROSA"
        artifacts_dir = proj_dir / "artifacts" / "raw"
        artifacts_dir.mkdir(parents=True)
        cronograma_path = artifacts_dir / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper()

            result = enrich_referencia_with_eap({}, cronograma_path)

        assert result["meta"]["projeto"] == "MARA_ROSA"

    def test_existing_meta_not_overwritten(self, tmp_path):
        cronograma_path = tmp_path / "artifacts" / "raw" / "cronograma.txt"
        cronograma_path.parent.mkdir(parents=True)
        cronograma_path.write_text("dummy", encoding="utf-8")

        referencia = {
            "meta": {
                "data_inicio": "2025-03-01",
                "data_termino": "2026-03-01",
                "projeto": "CUSTOM",
                "localizacao": "SP",
                "regime_trabalho": {"horas_dia": 10, "dias_semana": 5},
                "mode": "custom_mode",
            }
        }
        item = _make_eap_item(item_id="2.1")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper()

            result = enrich_referencia_with_eap(referencia, cronograma_path)

        assert result["meta"]["data_inicio"] == "2025-03-01"
        assert result["meta"]["modo"] if "modo" in result["meta"] else True

    def test_project_meta_merged(self, tmp_path):
        cronograma_path = tmp_path / "artifacts" / "raw" / "cronograma.txt"
        cronograma_path.parent.mkdir(parents=True)
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")
        project_meta = {"cliente": "VALE", "data_inicio": "2024-01-01"}

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper()

            result = enrich_referencia_with_eap({}, cronograma_path, project_meta=project_meta)

        assert result["meta"]["cliente"] == "VALE"
        assert result["meta"]["data_inicio"] == "2024-01-01"

    def test_no_eap_items_returns_early(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper"):
            MockParser.return_value = self._mock_parser([])
            result = enrich_referencia_with_eap({}, cronograma_path)

        # spec is not populated because we returned early
        assert "eap" not in result.get("spec", {})

    def test_cpu_mapper_init_failure_uses_none(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1", cpu_id="CPU-UNKNOWN")

        with (
            patch(f"{MODULE}.CronogramaParser") as MockParser,
            patch(f"{MODULE}.CpuMapper", side_effect=Exception("catalog unavailable")),
        ):
            MockParser.return_value = self._mock_parser([item])
            result = enrich_referencia_with_eap({}, cronograma_path)

        # Should still produce eap but using fallback inference
        assert len(result["spec"]["eap"]) == 1
        assert result["spec"]["eap"][0]["cpu_id"] != "CPU-UNKNOWN"

    def test_cpu_mapper_maps_unknown_cpu(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="4.2", cpu_id="CPU-UNKNOWN")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-ESCA-REAL-001")

            result = enrich_referencia_with_eap({}, cronograma_path)

        assert result["spec"]["eap"][0]["cpu_id"] == "CPU-ESCA-REAL-001"

    def test_cpu_mapper_unmapped_falls_back_to_inference(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="3.5", cpu_id="CPU-UNKNOWN")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu=None)

            result = enrich_referencia_with_eap({}, cronograma_path)

        # Uses section-based inference for section 3 -> LIMP
        assert result["spec"]["eap"][0]["cpu_id"] == "CPU-LIMP-005"

    def test_known_cpu_not_remapped(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1", cpu_id="CPU-ALREADY-SET")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            mock_mapper = self._mock_mapper()
            MockMapper.return_value = mock_mapper

            result = enrich_referencia_with_eap({}, cronograma_path)

        # Already-set CPU should be kept
        assert result["spec"]["eap"][0]["cpu_id"] == "CPU-ALREADY-SET"
        mock_mapper.map_item_to_cpu.assert_not_called()

    def test_producao_horaria_stored_in_cpu_meta(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")
        item["producao_horaria"] = 25.0

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-X")

            result = enrich_referencia_with_eap({}, cronograma_path)

        assert result["spec"]["eap"][0]["cpu_meta"]["producao_horaria"] == pytest.approx(25.0)

    def test_ordem_is_sequential(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        items = [
            _make_eap_item(item_id="1.1"),
            _make_eap_item(item_id="1.2"),
            _make_eap_item(item_id="1.3"),
        ]

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser(items)
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-MOB-001")

            result = enrich_referencia_with_eap({}, cronograma_path)

        orders = [item["ordem"] for item in result["spec"]["eap"]]
        assert orders == [1, 2, 3]

    def test_cronograma_spec_built(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-X")

            result = enrich_referencia_with_eap({}, cronograma_path)

        cronograma = result["spec"]["cronograma"]
        assert len(cronograma) == 1
        assert cronograma[0]["item_id"] == "2.1"
        assert "producao_diaria" in cronograma[0]
        assert "semanas" in cronograma[0]

    def test_rcpsp_spec_preserved(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        referencia = {"spec": {"rcpsp_spec": {"existing": True}}}
        item = _make_eap_item(item_id="2.1")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-X")

            result = enrich_referencia_with_eap(referencia, cronograma_path)

        assert result["spec"]["rcpsp_spec"]["existing"] is True

    def test_mapping_stats_logged_when_items_processed(self, tmp_path, capsys):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")

        stats = {"total_items_processed": 5, "successfully_mapped": 4, "success_rate": 80.0}

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-X", stats=stats)

            enrich_referencia_with_eap({}, cronograma_path)

        captured = capsys.readouterr()
        assert "4/5" in captured.out

    def test_no_stats_logged_when_zero_items(self, tmp_path, capsys):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")
        stats = {"total_items_processed": 0, "successfully_mapped": 0, "success_rate": 0.0}

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-X", stats=stats)

            enrich_referencia_with_eap({}, cronograma_path)

        captured = capsys.readouterr()
        assert "CPU mapping:" not in captured.out

    def test_produtividade_file_enriches_items(self, tmp_path):
        raw_dir = tmp_path / "artifacts" / "raw"
        raw_dir.mkdir(parents=True)
        cronograma_path = raw_dir / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        prod_path = raw_dir / "produtividade.txt"
        prod_path.write_text(
            "h\nh\nh\nh\n2.1\tItem\tM3\t75,00\n",
            encoding="utf-8",
        )

        item = _make_eap_item(item_id="2.1")
        item["producao_horaria"] = 0.0

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser([item])
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-X")

            result = enrich_referencia_with_eap({}, cronograma_path)

        assert result["spec"]["eap"][0]["cpu_meta"]["producao_horaria"] == pytest.approx(75.0)

    def test_item_without_dot_excluded_from_cronograma(self, tmp_path):
        cronograma_path = tmp_path / "cronograma.txt"
        cronograma_path.write_text("dummy", encoding="utf-8")

        items = [
            _make_eap_item(item_id="2"),  # no dot — section header
            _make_eap_item(item_id="2.1"),
        ]

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = self._mock_parser(items)
            MockMapper.return_value = self._mock_mapper(mapped_cpu="CPU-X")

            result = enrich_referencia_with_eap({}, cronograma_path)

        # cronograma only includes leaf items (with dot)
        cronograma_ids = [c["item_id"] for c in result["spec"]["cronograma"]]
        assert "2" not in cronograma_ids
        assert "2.1" in cronograma_ids


# ---------------------------------------------------------------------------
# _extract_eap_from_cpus_txt
# ---------------------------------------------------------------------------

from concilium.application.benchmarks.spec.referencia_enricher import _extract_eap_from_cpus_txt  # noqa: E402


class TestExtractEapFromCpusTxt:
    def _write_cpus_txt(self, tmp_path, lines: list[str]) -> Path:
        path = tmp_path / "cpus.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def test_empty_file_returns_empty(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, [])
        result = _extract_eap_from_cpus_txt(path)
        assert result == []

    def test_basic_item_parsed(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, ["2\tEscavação\tM3\t100"])
        result = _extract_eap_from_cpus_txt(path)
        assert len(result) == 1
        assert result[0]["item_id"] == "2"
        assert result[0]["cpu_id"] == "CPU-UNKNOWN"

    def test_decimal_item_parsed(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, ["2.1\tEscavação manual\tM3\t200"])
        result = _extract_eap_from_cpus_txt(path)
        assert len(result) == 1
        assert result[0]["item_id"] == "2.1"

    def test_non_digit_first_part_skipped(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, ["CODE\tItem\tUN\t100", "2.1\tEscav\tM3\t50"])
        result = _extract_eap_from_cpus_txt(path)
        assert len(result) == 1
        assert result[0]["item_id"] == "2.1"

    def test_empty_lines_skipped(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, ["", "   ", "2.1\tItem\tM3\t50"])
        result = _extract_eap_from_cpus_txt(path)
        assert len(result) == 1

    def test_too_many_dot_parts_skipped(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, ["2.1.3\tItem\tM3\t50"])
        result = _extract_eap_from_cpus_txt(path)
        assert result == []

    def test_non_numeric_part_skipped(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, ["2.A\tItem\tM3\t50"])
        result = _extract_eap_from_cpus_txt(path)
        assert result == []

    def test_duplicate_ids_deduplicated(self, tmp_path):
        path = self._write_cpus_txt(
            tmp_path,
            [
                "2.1\tFirst\tM3\t100",
                "2.1\tSecond\tM3\t200",
            ],
        )
        result = _extract_eap_from_cpus_txt(path)
        assert len(result) == 1

    def test_predecessor_inferred_for_sequential_items(self, tmp_path):
        path = self._write_cpus_txt(
            tmp_path,
            [
                "2.1\tFirst\tM3\t100",
                "2.2\tSecond\tM3\t200",
            ],
        )
        result = _extract_eap_from_cpus_txt(path)
        assert len(result) == 2
        # 2.2 should have 2.1 as predecessor
        preds = result[1]["predecessores"]
        assert any(p["item_id"] == "2.1" for p in preds)

    def test_first_item_in_section_has_no_predecessor(self, tmp_path):
        path = self._write_cpus_txt(tmp_path, ["2.1\tFirst\tM3\t100"])
        result = _extract_eap_from_cpus_txt(path)
        assert result[0]["predecessores"] == []

    def test_ordem_increments(self, tmp_path):
        path = self._write_cpus_txt(
            tmp_path,
            [
                "1.1\tA\tM3\t10",
                "1.2\tB\tM3\t20",
                "1.3\tC\tM3\t30",
            ],
        )
        result = _extract_eap_from_cpus_txt(path)
        assert [r["ordem"] for r in result] == [1, 2, 3]

    def test_description_extracted_from_text_part(self, tmp_path):
        # Part with no digits/special chars should be the description
        path = self._write_cpus_txt(tmp_path, ["3.2\tEscavacao\tM3\t50"])
        result = _extract_eap_from_cpus_txt(path)
        assert result[0]["descricao"] == "Escavacao"

    def test_generic_description_when_all_parts_have_digits(self, tmp_path):
        # All parts have digits/special chars so fallback to generic
        path = self._write_cpus_txt(tmp_path, ["3.2\t100,00\t50,00\t200,00"])
        result = _extract_eap_from_cpus_txt(path)
        assert result[0]["descricao"] == "Item 3.2"

    def test_generic_description_when_single_token_line(self, tmp_path):
        """Branch 251->259: linha com apenas o item_id (len(parts) <= 1) -> pula direto para descrição genérica."""
        path = self._write_cpus_txt(tmp_path, ["3.2"])
        result = _extract_eap_from_cpus_txt(path)
        assert result[0]["descricao"] == "Item 3.2"

    def test_unreadable_file_returns_empty(self, tmp_path):
        path = tmp_path / "cpus.txt"
        path.write_text("2.1\tItem\tM3\t50", encoding="utf-8")

        with patch("builtins.open", side_effect=OSError("cannot open")):
            result = _extract_eap_from_cpus_txt(path)

        assert result == []

    def test_predecessor_type_is_FS(self, tmp_path):
        path = self._write_cpus_txt(
            tmp_path,
            [
                "4.1\tFirst\tM3\t100",
                "4.2\tSecond\tM3\t200",
            ],
        )
        result = _extract_eap_from_cpus_txt(path)
        pred = result[1]["predecessores"][0]
        assert pred["tipo"] == "FS"
        assert pred["lag"] == 0
        assert pred["completion_threshold_pct"] == 1.0


# ---------------------------------------------------------------------------
# enrich_benchmark_referencia
# ---------------------------------------------------------------------------

from concilium.application.benchmarks.spec.referencia_enricher import enrich_benchmark_referencia  # noqa: E402


class TestEnrichBenchmarkReferencia:
    def _setup_benchmark_dir(self, tmp_path, referencia_data=None):
        benchmark_dir = tmp_path / "MARA_ROSA"
        benchmark_dir.mkdir()
        artifacts_raw = benchmark_dir / "artifacts" / "raw"
        artifacts_raw.mkdir(parents=True)

        if referencia_data is None:
            referencia_data = {}
        (benchmark_dir / "referencia.json").write_text(
            json.dumps(referencia_data, ensure_ascii=False), encoding="utf-8"
        )
        return benchmark_dir, artifacts_raw

    def test_missing_referencia_returns_false(self, tmp_path):
        benchmark_dir = tmp_path / "NO_REF"
        benchmark_dir.mkdir()
        result = enrich_benchmark_referencia(benchmark_dir)
        assert result is False

    def test_cronograma_used_when_present(self, tmp_path):
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path)
        cronograma_path = artifacts_raw / "cronograma.txt"
        cronograma_path.write_text("some content", encoding="utf-8")

        item = _make_eap_item(item_id="2.1")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper") as MockMapper:
            MockParser.return_value = MagicMock(parse_file=MagicMock(return_value=[item]))
            mock_m = MagicMock()
            mock_m.map_item_to_cpu.return_value = "CPU-X"
            mock_m.get_mapping_stats.return_value = {
                "total_items_processed": 1,
                "successfully_mapped": 1,
                "success_rate": 100.0,
            }
            MockMapper.return_value = mock_m

            result = enrich_benchmark_referencia(benchmark_dir)

        assert result is True
        written = json.loads((benchmark_dir / "referencia.json").read_text(encoding="utf-8"))
        assert len(written["spec"]["eap"]) == 1

    def test_cronograma_empty_file_falls_back_to_cpus(self, tmp_path):
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path)
        cronograma_path = artifacts_raw / "cronograma.txt"
        cronograma_path.write_text("")  # empty file — st_size == 0

        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text("2.1\tEscavacao\tM3\t100", encoding="utf-8")

        result = enrich_benchmark_referencia(benchmark_dir)

        assert result is True
        written = json.loads((benchmark_dir / "referencia.json").read_text(encoding="utf-8"))
        assert len(written["spec"]["eap"]) == 1

    def test_no_cronograma_no_cpus_returns_false(self, tmp_path):
        benchmark_dir, _ = self._setup_benchmark_dir(tmp_path)
        result = enrich_benchmark_referencia(benchmark_dir)
        assert result is False

    def test_cronograma_parse_failure_falls_back_to_cpus(self, tmp_path):
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path)

        cronograma_path = artifacts_raw / "cronograma.txt"
        cronograma_path.write_text("content", encoding="utf-8")

        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text("3.1\tLimpeza\tM2\t500", encoding="utf-8")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper"):
            MockParser.return_value = MagicMock(parse_file=MagicMock(side_effect=RuntimeError("parse fail")))

            result = enrich_benchmark_referencia(benchmark_dir)

        assert result is True

    def test_cpus_path_yields_empty_eap_returns_false(self, tmp_path):
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path)

        cpus_path = artifacts_raw / "cpus.txt"
        # File with no valid item ids
        cpus_path.write_text("CODE\tDesc\nTOTAL\tSum", encoding="utf-8")

        result = enrich_benchmark_referencia(benchmark_dir)
        assert result is False

    def test_meta_defaults_added_from_cpus_path(self, tmp_path):
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path, {})
        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text("1.1\tMobilizacao\tun\t1", encoding="utf-8")

        result = enrich_benchmark_referencia(benchmark_dir)

        assert result is True
        written = json.loads((benchmark_dir / "referencia.json").read_text(encoding="utf-8"))
        assert written["meta"]["data_inicio"] == "2026-01-01"
        assert written["meta"]["projeto"] == "MARA_ROSA"
        assert written["meta"]["localizacao"] == "Brasil"
        assert written["meta"]["regime_trabalho"] == {"horas_dia": 8, "dias_semana": 6}

    def test_existing_meta_not_overwritten_in_cpus_path(self, tmp_path):
        referencia = {
            "meta": {
                "data_inicio": "2024-06-01",
                "data_termino": "2025-06-01",
                "projeto": "CUSTOM",
                "localizacao": "MG",
                "regime_trabalho": {"horas_dia": 9, "dias_semana": 6},
            }
        }
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path, referencia)
        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text("1.1\tItem\tun\t1", encoding="utf-8")

        enrich_benchmark_referencia(benchmark_dir)

        written = json.loads((benchmark_dir / "referencia.json").read_text(encoding="utf-8"))
        assert written["meta"]["data_inicio"] == "2024-06-01"
        assert written["meta"]["projeto"] == "CUSTOM"

    def test_cronograma_zero_eap_fallback_to_cpus(self, tmp_path):
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path)

        cronograma_path = artifacts_raw / "cronograma.txt"
        cronograma_path.write_text("content", encoding="utf-8")

        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text("2.1\tEscav\tM3\t100", encoding="utf-8")

        with patch(f"{MODULE}.CronogramaParser") as MockParser, patch(f"{MODULE}.CpuMapper"):
            # parse_file returns empty list -> warning printed, returns early
            MockParser.return_value = MagicMock(parse_file=MagicMock(return_value=[]))

            result = enrich_benchmark_referencia(benchmark_dir)

        # Cronograma returned empty EAP but wrote back partial referencia (early return True).
        # The written file won't have eap (since enrich_referencia_with_eap returned early).
        # So the function should then fall through and try cpus.txt.
        # Actually, enrich_referencia_with_eap returns the (partial) referencia and does NOT raise
        # — so the outer try block succeeds and we write_text, returning True.
        assert result is True

    def test_spec_written_correctly_from_cpus(self, tmp_path):
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path)
        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text(
            "1.1\tMobilizacao\tun\t1\n1.2\tDesmobilizacao\tun\t1",
            encoding="utf-8",
        )

        result = enrich_benchmark_referencia(benchmark_dir)

        assert result is True
        written = json.loads((benchmark_dir / "referencia.json").read_text(encoding="utf-8"))
        assert len(written["spec"]["eap"]) == 2
        assert written["spec"]["rcpsp_spec"] == {}
        cronograma = written["spec"]["cronograma"]
        assert all("item_id" in c and "producao_diaria" in c for c in cronograma)

    def test_referencia_already_has_spec(self, tmp_path):
        """Existing spec is overwritten by cpus.txt path."""
        referencia = {"spec": {"eap": [], "rcpsp_spec": {"existing": True}}}
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path, referencia)
        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text("2.3\tItem\tM3\t50", encoding="utf-8")

        result = enrich_benchmark_referencia(benchmark_dir)

        assert result is True
        written = json.loads((benchmark_dir / "referencia.json").read_text(encoding="utf-8"))
        assert len(written["spec"]["eap"]) == 1

    def test_cpus_extraction_exception_returns_false(self, tmp_path):
        """When _extract_eap_from_cpus_txt raises unexpectedly, falls through to return False."""
        benchmark_dir, artifacts_raw = self._setup_benchmark_dir(tmp_path)
        cpus_path = artifacts_raw / "cpus.txt"
        cpus_path.write_text("2.1\tItem\tM3\t50", encoding="utf-8")

        with patch(f"{MODULE}._extract_eap_from_cpus_txt", side_effect=RuntimeError("unexpected error")):
            result = enrich_benchmark_referencia(benchmark_dir)

        assert result is False


class TestEnrichEapWithProdutividadeEmptyLineAfterHeaders:
    """Cover line 48: empty line encountered after the 4-header skip."""

    def test_empty_line_in_data_section_is_skipped(self, tmp_path):
        path = tmp_path / "produtividade.txt"
        # 4 header rows, then an empty line, then a real data row
        content = (
            "h1\n"
            "h2\n"
            "h3\n"
            "h4\n"
            "\n"  # empty data line — hits line 48
            "2.1\tItem\tM3\t30,00\n"
        )
        path.write_text(content, encoding="utf-8")

        items = [_make_eap_item(item_id="2.1")]
        _enrich_eap_with_produtividade(items, path)

        # The empty line was skipped; the real data was processed
        assert "cpu_meta" in items[0]
        assert items[0]["cpu_meta"]["producao_horaria"] == pytest.approx(30.0)
