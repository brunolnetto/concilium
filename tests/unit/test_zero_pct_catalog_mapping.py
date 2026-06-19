"""Tests for catalog mapping modules at 0% coverage.

Covers:
- cpu_fixer.fix_referencia_mappings
- cpu_mapper (private helpers + public API)
- equipes_normalizer (all helpers + public API)
- healer.heal_catalog
- updater.CatalogUpdater
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. cpu_fixer
# ---------------------------------------------------------------------------
from concilium.infrastructure.catalog.mapping.cpu_fixer import fix_referencia_mappings


class TestFixReferenciaMappings:
    def test_returns_empty_list_for_existing_path(self, tmp_path: Path) -> None:
        result = fix_referencia_mappings(tmp_path)
        assert result == []

    def test_returns_empty_list_for_nonexistent_path(self, tmp_path: Path) -> None:
        result = fix_referencia_mappings(tmp_path / "does_not_exist")
        assert result == []

    def test_returns_list_type(self, tmp_path: Path) -> None:
        result = fix_referencia_mappings(tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 2. cpu_mapper
# ---------------------------------------------------------------------------

from concilium.infrastructure.catalog.mapping.cpu_mapper import (
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


# ---------------------------------------------------------------------------
# 3. equipes_normalizer
# ---------------------------------------------------------------------------

from concilium.infrastructure.catalog.mapping.equipes_normalizer import (
    AuditRow,
    _classify_cpu,
    _extract_prod_team,
    _has_local_team,
    _load_producoes_index,
    _process_cpu_file,
    normalize_equipes_from_producoes,
)


class TestHasLocalTeam:
    def test_empty_dict_returns_false(self) -> None:
        assert _has_local_team({}) is False

    def test_equipe_with_funcoes_returns_true(self) -> None:
        cpu = {"equipe": {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []}}
        assert _has_local_team(cpu) is True

    def test_equipe_with_equipamentos_returns_true(self) -> None:
        cpu = {"equipe": {"funcoes": [], "equipamentos": [{"equip_id": "EQ-001"}]}}
        assert _has_local_team(cpu) is True

    def test_equipe_empty_funcoes_and_equipamentos_returns_false(self) -> None:
        cpu = {"equipe": {"funcoes": [], "equipamentos": []}}
        assert _has_local_team(cpu) is False

    def test_composicao_padrao_equipe_with_funcoes_returns_true(self) -> None:
        cpu = {
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "MO-002"}],
                "equipamentos": [],
            }
        }
        assert _has_local_team(cpu) is True

    def test_composicao_padrao_equipe_empty_returns_false(self) -> None:
        cpu = {"composicao_padrao_equipe": {"funcoes": [], "equipamentos": []}}
        assert _has_local_team(cpu) is False

    def test_no_equipe_key_returns_false(self) -> None:
        assert _has_local_team({"codigo": "CPU-001", "producao_id": "PROD-001"}) is False


class TestExtractProdTeam:
    def test_no_equipe_key_returns_none(self) -> None:
        assert _extract_prod_team({}) is None

    def test_equipe_with_funcoes_returns_comp(self) -> None:
        equipe = {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []}
        prod = {"equipe": equipe}
        result = _extract_prod_team(prod)
        assert result == equipe

    def test_equipe_with_equipamentos_returns_comp(self) -> None:
        equipe = {"funcoes": [], "equipamentos": [{"equip_id": "EQ-001"}]}
        prod = {"equipe": equipe}
        result = _extract_prod_team(prod)
        assert result == equipe

    def test_equipe_empty_funcoes_and_equipamentos_returns_none(self) -> None:
        prod = {"equipe": {"funcoes": [], "equipamentos": []}}
        assert _extract_prod_team(prod) is None

    def test_equipe_not_dict_returns_none(self) -> None:
        prod = {"equipe": "not_a_dict"}
        assert _extract_prod_team(prod) is None

    def test_composicao_padrao_equipe_with_funcoes_returns_comp(self) -> None:
        equipe = {"funcoes": [{"funcao_id": "MO-003"}], "equipamentos": []}
        prod = {"composicao_padrao_equipe": equipe}
        result = _extract_prod_team(prod)
        assert result == equipe


class TestLoadProducoesIndex:
    def test_empty_dir_returns_empty_dict(self, tmp_path: Path) -> None:
        result = _load_producoes_index(tmp_path)
        assert result == {}

    def test_valid_prod_files_indexed_by_id(self, tmp_path: Path) -> None:
        prod1 = {"id": "PROD-001", "descricao": "Escavação"}
        prod2 = {"id": "PROD-002", "descricao": "Aterro"}
        (tmp_path / "PROD-001.json").write_text(json.dumps(prod1), encoding="utf-8")
        (tmp_path / "PROD-002.json").write_text(json.dumps(prod2), encoding="utf-8")

        result = _load_producoes_index(tmp_path)
        assert "PROD-001" in result
        assert "PROD-002" in result
        assert result["PROD-001"]["descricao"] == "Escavação"

    def test_prod_without_id_field_not_indexed(self, tmp_path: Path) -> None:
        prod = {"descricao": "sem id"}
        (tmp_path / "NOID.json").write_text(json.dumps(prod), encoding="utf-8")
        result = _load_producoes_index(tmp_path)
        assert result == {}

    def test_prod_with_non_string_id_not_indexed(self, tmp_path: Path) -> None:
        prod = {"id": 42, "descricao": "id numerico"}
        (tmp_path / "NUM.json").write_text(json.dumps(prod), encoding="utf-8")
        result = _load_producoes_index(tmp_path)
        assert result == {}


class TestProcessCpuFile:
    def _write_cpu(self, path: Path, data: dict) -> Path:
        cpu_file = path / "CPU-TEST.json"
        cpu_file.write_text(json.dumps(data), encoding="utf-8")
        return cpu_file

    def test_cpu_without_codigo_returns_none(self, tmp_path: Path) -> None:
        cpu_file = self._write_cpu(tmp_path, {"producao_id": "PROD-001"})
        result = _process_cpu_file(cpu_file, {}, None, False)
        assert result is None

    def test_cpu_with_filter_not_matching_returns_none(self, tmp_path: Path) -> None:
        cpu_file = self._write_cpu(tmp_path, {"codigo": "CPU-001", "producao_id": "PROD-001"})
        result = _process_cpu_file(cpu_file, {}, "CPU-999", False)
        assert result is None

    def test_cpu_without_producao_id_returns_none(self, tmp_path: Path) -> None:
        cpu_file = self._write_cpu(tmp_path, {"codigo": "CPU-001"})
        result = _process_cpu_file(cpu_file, {}, None, False)
        assert result is None

    def test_cpu_with_producao_id_dispatches_to_classify(self, tmp_path: Path) -> None:
        cpu_file = self._write_cpu(tmp_path, {"codigo": "CPU-001", "producao_id": "PROD-001"})
        # Empty producoes → erro status
        result = _process_cpu_file(cpu_file, {}, None, False)
        assert result is not None
        assert isinstance(result, AuditRow)
        assert result.status == "erro"

    def test_cpu_with_matching_filter_dispatches(self, tmp_path: Path) -> None:
        cpu_file = self._write_cpu(tmp_path, {"codigo": "CPU-001", "producao_id": "PROD-001"})
        result = _process_cpu_file(cpu_file, {}, "CPU-001", False)
        assert result is not None


class TestClassifyCpu:
    def _make_cpu_file(self, tmp_path: Path, data: dict) -> Path:
        f = tmp_path / "cpu.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        return f

    def test_cpu_has_local_team_returns_ok(self, tmp_path: Path) -> None:
        cpu = {
            "codigo": "CPU-001",
            "producao_id": "PROD-001",
            "equipe": {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []},
        }
        cpu_file = self._make_cpu_file(tmp_path, cpu)
        result = _classify_cpu(cpu_file, cpu, "CPU-001", "PROD-001", {}, False)
        assert result.status == "ok"
        assert result.detalhe == "cpu_ja_tem_equipe"

    def test_producao_not_found_returns_erro(self, tmp_path: Path) -> None:
        cpu = {"codigo": "CPU-001", "producao_id": "PROD-999"}
        cpu_file = self._make_cpu_file(tmp_path, cpu)
        result = _classify_cpu(cpu_file, cpu, "CPU-001", "PROD-999", {}, False)
        assert result.status == "erro"
        assert result.detalhe == "producao_id_inexistente"

    def test_producao_without_team_returns_erro(self, tmp_path: Path) -> None:
        cpu = {"codigo": "CPU-001", "producao_id": "PROD-001"}
        prod = {"id": "PROD-001", "equipe": {"funcoes": [], "equipamentos": []}}
        cpu_file = self._make_cpu_file(tmp_path, cpu)
        result = _classify_cpu(cpu_file, cpu, "CPU-001", "PROD-001", {"PROD-001": prod}, False)
        assert result.status == "erro"
        assert result.detalhe == "producao_sem_equipe"

    def test_apply_false_returns_normalizar_no_file_written(self, tmp_path: Path) -> None:
        cpu = {"codigo": "CPU-001", "producao_id": "PROD-001"}
        prod = {
            "id": "PROD-001",
            "equipe": {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []},
        }
        cpu_file = self._make_cpu_file(tmp_path, cpu)
        result = _classify_cpu(cpu_file, cpu, "CPU-001", "PROD-001", {"PROD-001": prod}, False)
        assert result.status == "normalizar"
        # File should not have been updated (no equipe key written)
        persisted = json.loads(cpu_file.read_text(encoding="utf-8"))
        assert "equipe" not in persisted

    def test_apply_true_writes_equipe_to_cpu_file(self, tmp_path: Path) -> None:
        cpu = {"codigo": "CPU-001", "producao_id": "PROD-001"}
        equipe = {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []}
        prod = {"id": "PROD-001", "equipe": equipe}
        cpu_file = self._make_cpu_file(tmp_path, cpu)
        result = _classify_cpu(cpu_file, cpu, "CPU-001", "PROD-001", {"PROD-001": prod}, True)
        assert result.status == "normalizar"
        persisted = json.loads(cpu_file.read_text(encoding="utf-8"))
        assert persisted["equipe"] == equipe


class TestNormalizeEquipesFromProducoes:
    def test_empty_cpus_dir_returns_empty_list(self, tmp_path: Path) -> None:
        (tmp_path / "cpus").mkdir()
        (tmp_path / "producoes").mkdir()
        result = normalize_equipes_from_producoes(tmp_path)
        assert result == []

    def test_cpu_with_producao_id_matching_producao_returns_audit_row(self, tmp_path: Path) -> None:
        cpus_dir = tmp_path / "cpus"
        prods_dir = tmp_path / "producoes"
        cpus_dir.mkdir()
        prods_dir.mkdir()

        equipe = {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []}
        prod = {"id": "PROD-001", "equipe": equipe}
        (prods_dir / "PROD-001.json").write_text(json.dumps(prod), encoding="utf-8")

        cpu = {"codigo": "CPU-001", "producao_id": "PROD-001"}
        (cpus_dir / "CPU-001.json").write_text(json.dumps(cpu), encoding="utf-8")

        result = normalize_equipes_from_producoes(tmp_path)
        assert len(result) == 1
        assert result[0].cpu == "CPU-001"
        assert result[0].producao_id == "PROD-001"
        assert result[0].status == "normalizar"

    def test_cpu_filter_excludes_non_matching(self, tmp_path: Path) -> None:
        cpus_dir = tmp_path / "cpus"
        prods_dir = tmp_path / "producoes"
        cpus_dir.mkdir()
        prods_dir.mkdir()

        cpu = {"codigo": "CPU-001", "producao_id": "PROD-001"}
        (cpus_dir / "CPU-001.json").write_text(json.dumps(cpu), encoding="utf-8")

        result = normalize_equipes_from_producoes(tmp_path, cpu_filter="CPU-999")
        assert result == []


# ---------------------------------------------------------------------------
# 4. healer
# ---------------------------------------------------------------------------

from concilium.infrastructure.catalog.mapping.healer import heal_catalog


def _setup_catalog(tmp_path: Path) -> Path:
    """Build a minimal catalog structure in tmp_path."""
    cat = tmp_path / "catalog"
    (cat / "insumos" / "mao_obra").mkdir(parents=True)
    (cat / "insumos" / "equipamento").mkdir(parents=True)
    (cat / "insumos" / "material").mkdir(parents=True)
    (cat / "producoes").mkdir(parents=True)
    (cat / "cpus").mkdir(parents=True)
    return cat


class TestHealCatalog:
    def test_empty_catalog_completes_without_error(self, tmp_path: Path) -> None:
        cat = _setup_catalog(tmp_path)
        result = heal_catalog(cat)
        assert "Cura concluída" in result

    def test_returns_completion_message_string(self, tmp_path: Path) -> None:
        cat = _setup_catalog(tmp_path)
        result = heal_catalog(cat)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_producao_composicao_padrao_equipe_renamed_to_equipe(self, tmp_path: Path) -> None:
        cat = _setup_catalog(tmp_path)
        prod_data = {
            "id": "PROD-001",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "MO-001"}],
                "equipamentos": [],
            },
        }
        (cat / "producoes" / "PROD-001.json").write_text(json.dumps(prod_data), encoding="utf-8")

        heal_catalog(cat)

        healed = json.loads((cat / "producoes" / "PROD-001.json").read_text(encoding="utf-8"))
        assert "composicao_padrao_equipe" not in healed
        assert "equipe" in healed

    def test_cpu_composicao_itens_insumo_ids_remapped_to_prefixed(self, tmp_path: Path) -> None:
        cat = _setup_catalog(tmp_path)
        # Create an insumo file so the id_map is populated
        mo_data = {"codigo": "MO-001", "descricao": "Servente"}
        (cat / "insumos" / "mao_obra" / "MO-001.json").write_text(json.dumps(mo_data), encoding="utf-8")

        cpu_data = {
            "codigo": "CPU-001",
            "composicao_itens": [
                {"insumo_id": "001", "quantidade": 1.0},
            ],
        }
        (cat / "cpus" / "CPU-001.json").write_text(json.dumps(cpu_data), encoding="utf-8")

        heal_catalog(cat)

        healed = json.loads((cat / "cpus" / "CPU-001.json").read_text(encoding="utf-8"))
        # "001" should be remapped: id_map["001"] = "MO-001" (via MA-001 fallback path too)
        # The healer tries id_map.get("001") or id_map.get("MA-001", "001")
        # Since "001" maps to "MO-001" via clean_id -> stem logic: stem="MO-001", clean_id="001"
        assert healed["composicao_itens"][0]["insumo_id"] == "MO-001"

    def test_cpu_with_producao_id_equipe_removed(self, tmp_path: Path) -> None:
        cat = _setup_catalog(tmp_path)
        cpu_data = {
            "codigo": "CPU-001",
            "producao_id": "PROD-001",
            "equipe": {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []},
        }
        (cat / "cpus" / "CPU-001.json").write_text(json.dumps(cpu_data), encoding="utf-8")

        heal_catalog(cat)

        healed = json.loads((cat / "cpus" / "CPU-001.json").read_text(encoding="utf-8"))
        assert "equipe" not in healed

    def test_cpu_without_producao_id_equipe_preserved(self, tmp_path: Path) -> None:
        cat = _setup_catalog(tmp_path)
        equipe = {"funcoes": [{"funcao_id": "MO-001"}], "equipamentos": []}
        cpu_data = {
            "codigo": "CPU-001",
            "equipe": equipe,
        }
        (cat / "cpus" / "CPU-001.json").write_text(json.dumps(cpu_data), encoding="utf-8")

        heal_catalog(cat)

        healed = json.loads((cat / "cpus" / "CPU-001.json").read_text(encoding="utf-8"))
        assert "equipe" in healed

    def test_cpu_composicao_padrao_equipe_renamed_to_equipe(self, tmp_path: Path) -> None:
        cat = _setup_catalog(tmp_path)
        cpu_data = {
            "codigo": "CPU-002",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "MO-001"}],
                "equipamentos": [],
            },
        }
        (cat / "cpus" / "CPU-002.json").write_text(json.dumps(cpu_data), encoding="utf-8")

        heal_catalog(cat)

        healed = json.loads((cat / "cpus" / "CPU-002.json").read_text(encoding="utf-8"))
        assert "composicao_padrao_equipe" not in healed
        # equipe is preserved because no producao_id
        assert "equipe" in healed


# ---------------------------------------------------------------------------
# 5. updater.CatalogUpdater
# ---------------------------------------------------------------------------

from concilium.domain.models.project.observacao import PropostaAtualizacao
from concilium.infrastructure.catalog.updater import CatalogUpdater

_UPDATER_MODULE = "concilium.infrastructure.catalog.updater"

_NOW = datetime(2025, 1, 15, 12, 0, 0)


def _make_proposta(**kwargs) -> PropostaAtualizacao:
    defaults = dict(
        proposta_id="PROP-001",
        tipo_artefato="insumo",
        artefato_id="MO-001",
        observacoes=["OBS-001"],
        n_obras_suporte=3,
        delta_medio_pct=5.0,
        confianca_estimada=0.9,
        campo="preco_unitario",
        valor_atual=100.0,
        valor_proposto=110.0,
        justificativa="Reajuste salarial 2025",
        fonte="reajuste_mercado",
        status="APROVADA",
        criado_em=_NOW,
        criado_por="engenheiro@empresa.com",
    )
    defaults.update(kwargs)
    return PropostaAtualizacao(**defaults)


def _make_updater(tmp_path: Path) -> CatalogUpdater:
    insumos_dir = tmp_path / "insumos"
    insumos_dir.mkdir(exist_ok=True)
    prods_dir = tmp_path / "producoes"
    prods_dir.mkdir(exist_ok=True)
    with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
        updater = CatalogUpdater(prods_dir, insumos_dir)
    return updater


class TestCatalogUpdaterApplyUpdate:
    def test_non_aprovada_proposta_raises_value_error(self, tmp_path: Path) -> None:
        proposta = _make_proposta(status="PENDENTE")
        updater = _make_updater(tmp_path)
        with pytest.raises(ValueError, match="não está APROVADA"):
            updater.apply_update(proposta, "aprovador@co.com")

    def test_unsupported_tipo_artefato_raises_value_error(self, tmp_path: Path) -> None:
        proposta = _make_proposta(tipo_artefato="cpu")
        updater = _make_updater(tmp_path)
        with pytest.raises(ValueError, match="não suportado"):
            updater.apply_update(proposta, "aprovador@co.com")

    def test_rejeitada_proposta_raises_value_error(self, tmp_path: Path) -> None:
        proposta = _make_proposta(status="REJEITADA")
        updater = _make_updater(tmp_path)
        with pytest.raises(ValueError, match="não está APROVADA"):
            updater.apply_update(proposta, "aprovador@co.com")


class TestCatalogUpdaterUpdateProducao:
    def test_update_producao_creates_new_version(self, tmp_path: Path) -> None:
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()

        # Build a mock Producao object
        mock_producao = MagicMock()
        mock_producao.id = "ESCO-CARGA-1CAT-PROD-001"
        mock_producao.qualidade.intervalo_confianca = (0.8, 1.2)
        mock_producao.qualidade.desvio_padrao = 0.05
        mock_producao.auditoria.criado_por = "user@co.com"
        mock_producao.auditoria.data_criacao = _NOW
        mock_producao.observacoes = ["OBS-001"]
        # model_copy returns a new mock with updated id
        new_prod = MagicMock()
        new_prod.id = "ESCO-CARGA-1CAT-PROD-002"
        new_prod.auditoria.versao = "2.0"
        mock_producao.model_copy.return_value = new_prod

        mock_repo = MagicMock()
        mock_repo.obter_ou_erro.return_value = mock_producao

        proposta = _make_proposta(
            tipo_artefato="producao",
            artefato_id="ESCO-CARGA-1CAT-PROD-001",
            campo="valor_horario",
            valor_atual=100.0,
            valor_proposto=120.0,
        )

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao", return_value=mock_repo):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            result = updater.apply_update(proposta, "aprovador@co.com")

        mock_repo.salvar.assert_called_once_with(new_prod)
        assert result.sucesso is True
        assert result.novo_artefato_id == "ESCO-CARGA-1CAT-PROD-002"
        assert result.versao_anterior == "ESCO-CARGA-1CAT-PROD-001"


class TestCatalogUpdaterUpdateInsumo:
    def test_insumo_not_found_returns_sucesso_false(self, tmp_path: Path) -> None:
        proposta = _make_proposta(artefato_id="MO-INEXISTENTE")
        updater = _make_updater(tmp_path)
        result = updater.apply_update(proposta, "aprovador@co.com")
        assert result.sucesso is False
        assert result.novo_artefato_id is None

    def test_update_preco_unitario_updates_file_and_audit_trail(self, tmp_path: Path) -> None:
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()

        insumo = {"codigo": "MO-001", "descricao": "Servente", "preco_unitario": 100.0}
        insumo_file = insumos_dir / "mao_obra.json"
        insumo_file.write_text(json.dumps([insumo]), encoding="utf-8")

        proposta = _make_proposta(
            artefato_id="MO-001",
            campo="preco_unitario",
            valor_atual=100.0,
            valor_proposto=110.0,
        )

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            result = updater.apply_update(proposta, "aprovador@co.com")

        assert result.sucesso is True
        assert result.novo_artefato_id == "MO-001"

        updated_data = json.loads(insumo_file.read_text(encoding="utf-8"))
        updated_insumo = next(i for i in updated_data if i["codigo"] == "MO-001")
        assert updated_insumo["preco_unitario"] == 110.0
        assert len(updated_insumo["auditoria_custo"]) == 1
        assert updated_insumo["auditoria_custo"][0]["custo_anterior"] == 100.0
        assert updated_insumo["auditoria_custo"][0]["custo_novo"] == 110.0

    def test_update_capacidade_cobertura_updates_classe_compartilhamento(self, tmp_path: Path) -> None:
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()

        insumo = {"codigo": "EQ-001", "descricao": "Escavadeira"}
        insumo_file = insumos_dir / "equipamentos.json"
        insumo_file.write_text(json.dumps([insumo]), encoding="utf-8")

        proposta = _make_proposta(
            artefato_id="EQ-001",
            tipo_artefato="cobertura",
            campo="capacidade_cobertura",
            valor_atual=2,
            valor_proposto=4,
        )

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            result = updater.apply_update(proposta, "aprovador@co.com")

        assert result.sucesso is True
        updated_data = json.loads(insumo_file.read_text(encoding="utf-8"))
        updated_insumo = next(i for i in updated_data if i["codigo"] == "EQ-001")
        assert updated_insumo["classe_compartilhamento"]["capacidade_cobertura"] == 4

    def test_update_other_campo_updates_directly(self, tmp_path: Path) -> None:
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()

        insumo = {"codigo": "MA-001", "descricao": "Cimento", "unidade": "kg"}
        insumo_file = insumos_dir / "materiais.json"
        insumo_file.write_text(json.dumps([insumo]), encoding="utf-8")

        proposta = _make_proposta(
            artefato_id="MA-001",
            campo="unidade",
            valor_atual="kg",
            valor_proposto="saco 50kg",
        )

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            result = updater.apply_update(proposta, "aprovador@co.com")

        assert result.sucesso is True
        updated_data = json.loads(insumo_file.read_text(encoding="utf-8"))
        updated_insumo = next(i for i in updated_data if i["codigo"] == "MA-001")
        assert updated_insumo["unidade"] == "saco 50kg"

    def test_insumo_file_as_dict_with_insumos_key(self, tmp_path: Path) -> None:
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()

        insumo = {"codigo": "MO-002", "descricao": "Pedreiro", "preco_unitario": 200.0}
        insumo_file = insumos_dir / "bundle.json"
        insumo_file.write_text(json.dumps({"insumos": [insumo], "versao": "1.0"}), encoding="utf-8")

        proposta = _make_proposta(
            artefato_id="MO-002",
            campo="preco_unitario",
            valor_atual=200.0,
            valor_proposto=220.0,
        )

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            result = updater.apply_update(proposta, "aprovador@co.com")

        assert result.sucesso is True
        updated_data = json.loads(insumo_file.read_text(encoding="utf-8"))
        updated_insumo = next(i for i in updated_data["insumos"] if i["codigo"] == "MO-002")
        assert updated_insumo["preco_unitario"] == 220.0


class TestCatalogUpdaterFindInsumo:
    def test_no_files_returns_none_none(self, tmp_path: Path) -> None:
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            item, path = updater._find_insumo("MO-999")

        assert item is None
        assert path is None

    def test_file_with_matching_codigo_returns_item_and_path(self, tmp_path: Path) -> None:
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()

        insumo = {"codigo": "MO-001", "descricao": "Servente"}
        insumo_file = insumos_dir / "mao_obra.json"
        insumo_file.write_text(json.dumps([insumo]), encoding="utf-8")

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            item, path = updater._find_insumo("MO-001")

        assert item is not None
        assert item["codigo"] == "MO-001"
        assert path == insumo_file

    def test_file_without_matching_codigo_returns_none(self, tmp_path: Path) -> None:
        insumos_dir = tmp_path / "insumos"
        insumos_dir.mkdir()
        prods_dir = tmp_path / "producoes"
        prods_dir.mkdir()

        insumo = {"codigo": "MO-002", "descricao": "Pedreiro"}
        insumo_file = insumos_dir / "mao_obra.json"
        insumo_file.write_text(json.dumps([insumo]), encoding="utf-8")

        with patch(f"{_UPDATER_MODULE}.RepositorioProducao"):
            updater = CatalogUpdater(prods_dir, insumos_dir)
            item, path = updater._find_insumo("MO-001")

        assert item is None
        assert path is None
