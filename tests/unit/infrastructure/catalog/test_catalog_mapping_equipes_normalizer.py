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

# 3. equipes_normalizer
# ---------------------------------------------------------------------------
from concilium.infrastructure.catalog.mapping.equipes_normalizer import (  # noqa: E402
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

