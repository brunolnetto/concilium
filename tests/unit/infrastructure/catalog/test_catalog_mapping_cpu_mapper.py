"""Tests for catalog mapping modules at 0% coverage.

Covers:
- cpu_fixer.fix_referencia_mappings
- cpu_mapper (private helpers + public API)
- equipes_normalizer (all helpers + public API)
- healer.heal_catalog
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

# 2. cpu_mapper
# ---------------------------------------------------------------------------
from concilium.infrastructure.catalog.mapping.cpu_mapper import (  # noqa: E402
    _clean_keyword_list,
    _load_mapping_keywords,
    apply_cpu_mappings,
    map_desc,
)

_MAPPER_MODULE = "concilium.infrastructure.catalog.mapping.cpu_mapper"


class TestCleanKeywordList:
    def test_empty_list_returns_empty(self) -> None:
        assert _clean_keyword_list([]) == []

    def test_strings_are_uppercased(self) -> None:
        result = _clean_keyword_list(["aterro", "corte"])
        assert result == ["ATERRO", "CORTE"]

    def test_blank_strings_are_removed(self) -> None:
        result = _clean_keyword_list(["  ", "", "aterro"])
        assert result == ["ATERRO"]

    def test_non_string_values_converted_and_uppercased(self) -> None:
        result = _clean_keyword_list([123, "abc"])
        assert "123" in result
        assert "ABC" in result

    def test_mixed_values_blanks_removed(self) -> None:
        result = _clean_keyword_list(["  ", None, "escavacao"])
        # "None".strip() == "None" — non-empty so it stays
        assert "ESCAVACAO" in result
        assert "NONE" in result

    def test_only_blanks_returns_empty(self) -> None:
        assert _clean_keyword_list(["   ", "  "]) == []


class TestLoadMappingKeywords:
    def test_file_not_exists_returns_empty(self, tmp_path: Path) -> None:
        missing = tmp_path / "no_file.json"
        with patch(f"{_MAPPER_MODULE}._rules_file", return_value=missing):
            result = _load_mapping_keywords()
        assert result == {}

    def test_valid_mapping_keywords_key(self, tmp_path: Path) -> None:
        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps({"mapping_keywords": {"ATI-001": ["ATERRO"]}}), encoding="utf-8")
        with patch(f"{_MAPPER_MODULE}._rules_file", return_value=rules):
            result = _load_mapping_keywords()
        assert "ATI-001" in result
        assert result["ATI-001"] == ["ATERRO"]

    def test_valid_direct_dict_without_mapping_keywords_key(self, tmp_path: Path) -> None:
        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps({"CPU-X": ["ESCAVACAO"]}), encoding="utf-8")
        with patch(f"{_MAPPER_MODULE}._rules_file", return_value=rules):
            result = _load_mapping_keywords()
        assert "CPU-X" in result

    def test_invalid_json_returns_empty(self, tmp_path: Path) -> None:
        rules = tmp_path / "rules.json"
        rules.write_text("not valid json{{", encoding="utf-8")
        with patch(f"{_MAPPER_MODULE}._rules_file", return_value=rules):
            result = _load_mapping_keywords()
        assert result == {}

    def test_payload_not_dict_returns_empty(self, tmp_path: Path) -> None:
        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with patch(f"{_MAPPER_MODULE}._rules_file", return_value=rules):
            result = _load_mapping_keywords()
        assert result == {}

    def test_keywords_value_not_list_is_skipped(self, tmp_path: Path) -> None:
        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps({"CPU-BAD": "not_a_list", "CPU-OK": ["CORTE"]}), encoding="utf-8")
        with patch(f"{_MAPPER_MODULE}._rules_file", return_value=rules):
            result = _load_mapping_keywords()
        assert "CPU-BAD" not in result
        assert "CPU-OK" in result

    def test_empty_keywords_list_is_excluded(self, tmp_path: Path) -> None:
        rules = tmp_path / "rules.json"
        rules.write_text(json.dumps({"CPU-EMPTY": [], "CPU-OK": ["TERRAPLENAGEM"]}), encoding="utf-8")
        with patch(f"{_MAPPER_MODULE}._rules_file", return_value=rules):
            result = _load_mapping_keywords()
        assert "CPU-EMPTY" not in result
        assert "CPU-OK" in result


class TestMapDesc:
    def _patch_mappings(self, mappings: dict):
        return patch(f"{_MAPPER_MODULE}._load_mapping_keywords", return_value=mappings)

    def test_no_mappings_returns_none(self) -> None:
        with self._patch_mappings({}):
            assert map_desc("qualquer descricao") is None

    def test_all_keywords_match_returns_code(self) -> None:
        mappings = {"CPU-001": ["ATERRO", "COMPACTACAO"]}
        with self._patch_mappings(mappings):
            result = map_desc("Aterro e Compactacao do solo")
        assert result == "CPU-001"

    def test_partial_keyword_match_returns_code(self) -> None:
        mappings = {"CPU-002": ["ESCAVACAO", "CARGA"]}
        with self._patch_mappings(mappings):
            # Only "ESCAVACAO" matches → partial match path
            result = map_desc("servico de escavacao mecanica")
        assert result == "CPU-002"

    def test_cerca_anti_false_positive_skips_when_not_in_keywords(self) -> None:
        # "CERCA" in description, partial match on a non-CERCA keyword → should skip.
        # Use TWO keywords so the all() pass fails (only one matches), forcing the
        # partial path where the CERCA guard fires and the code is skipped.
        mappings = {"CPU-003": ["ESCAVACAO", "COMPACTACAO"]}
        with self._patch_mappings(mappings):
            # "ESCAVACAO" matches (partial), "COMPACTACAO" does not → partial path
            # "CERCA" is in description but not in keyword list → CERCA guard skips
            result = map_desc("instalacao de cerca e escavacao")
        assert result is None

    def test_cerca_in_keywords_allows_match(self) -> None:
        mappings = {"CPU-CERCA": ["CERCA", "INSTALACAO"]}
        with self._patch_mappings(mappings):
            result = map_desc("instalacao de cerca")
        assert result == "CPU-CERCA"

    def test_case_insensitive_match(self) -> None:
        mappings = {"CPU-004": ["PAVIMENTACAO"]}
        with self._patch_mappings(mappings):
            result = map_desc("servico de pavimentacao asfaltica")
        assert result == "CPU-004"

    def test_no_match_returns_none(self) -> None:
        mappings = {"CPU-005": ["DRENAGEM"]}
        with self._patch_mappings(mappings):
            result = map_desc("servico de pintura")
        assert result is None


class TestApplyCpuMappings:
    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        result = apply_cpu_mappings(tmp_path)
        assert result == []

    def test_project_without_referencia_json_is_skipped(self, tmp_path: Path) -> None:
        proj = tmp_path / "PROJ-001"
        proj.mkdir()
        result = apply_cpu_mappings(tmp_path)
        assert result == []

    def test_referencia_with_missing_cpu_id_gets_mapped_and_logged(self, tmp_path: Path) -> None:
        proj = tmp_path / "PROJ-001"
        proj.mkdir()
        referencia = {
            "eap": [
                {"descricao": "Aterro Compactado", "cpu_id": None},
            ]
        }
        (proj / "referencia.json").write_text(json.dumps(referencia), encoding="utf-8")
        mappings = {"CPU-ATERRO": ["ATERRO"]}
        with patch(f"{_MAPPER_MODULE}._load_mapping_keywords", return_value=mappings):
            result = apply_cpu_mappings(tmp_path)

        assert len(result) == 1
        assert "PROJ-001" in result[0]
        # Verify the file was actually updated
        updated = json.loads((proj / "referencia.json").read_text(encoding="utf-8"))
        assert updated["eap"][0]["cpu_id"] == "CPU-ATERRO"

    def test_referencia_with_all_cpu_ids_set_no_update(self, tmp_path: Path) -> None:
        proj = tmp_path / "PROJ-002"
        proj.mkdir()
        referencia = {
            "eap": [
                {"descricao": "Aterro Compactado", "cpu_id": "CPU-EXISTING"},
            ]
        }
        (proj / "referencia.json").write_text(json.dumps(referencia), encoding="utf-8")
        mappings = {"CPU-ATERRO": ["ATERRO"]}
        with patch(f"{_MAPPER_MODULE}._load_mapping_keywords", return_value=mappings):
            result = apply_cpu_mappings(tmp_path)

        assert result == []

    def test_file_in_root_not_a_directory_is_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "some_file.txt").write_text("hello")
        result = apply_cpu_mappings(tmp_path)
        assert result == []

    def test_referencia_with_missing_cpu_id_and_no_keyword_match_not_updated(self, tmp_path: Path) -> None:
        """When map_desc() can't find a matching keyword (code is None/falsy),
        the item is left untouched and no update/log is produced — exercises
        the false branch of `if code:` in apply_cpu_mappings."""
        proj = tmp_path / "PROJ-003"
        proj.mkdir()
        referencia = {
            "eap": [
                {"descricao": "Descricao sem correspondencia nenhuma", "cpu_id": None},
            ]
        }
        (proj / "referencia.json").write_text(json.dumps(referencia), encoding="utf-8")
        mappings = {"CPU-ATERRO": ["ATERRO"]}
        with patch(f"{_MAPPER_MODULE}._load_mapping_keywords", return_value=mappings):
            result = apply_cpu_mappings(tmp_path)

        assert result == []
        updated = json.loads((proj / "referencia.json").read_text(encoding="utf-8"))
        assert updated["eap"][0]["cpu_id"] is None


# ---------------------------------------------------------------------------

