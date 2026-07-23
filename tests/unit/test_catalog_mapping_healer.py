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

# 4. healer
# ---------------------------------------------------------------------------
from concilium.infrastructure.catalog.mapping.healer import heal_catalog  # noqa: E402


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

    def test_producao_without_equipe_is_left_unchanged(self, tmp_path: Path) -> None:
        """Line 18 false branch: producao with neither composicao_padrao_equipe
        nor equipe keys skips the remap block entirely."""
        cat = _setup_catalog(tmp_path)
        prod_data = {"id": "PROD-002", "descricao": "Sem equipe"}
        (cat / "producoes" / "PROD-002.json").write_text(json.dumps(prod_data), encoding="utf-8")

        heal_catalog(cat)

        healed = json.loads((cat / "producoes" / "PROD-002.json").read_text(encoding="utf-8"))
        assert "equipe" not in healed
        assert healed["id"] == "PROD-002"

    def test_missing_insumo_subfolder_is_skipped(self, tmp_path: Path) -> None:
        """Line 57 false branch: an insumos/{folder} directory that doesn't exist
        is skipped without populating id_map for that prefix."""
        cat = tmp_path / "catalog"
        # Only create mao_obra — equipamento and material dirs are absent.
        (cat / "insumos" / "mao_obra").mkdir(parents=True)
        (cat / "producoes").mkdir(parents=True)
        (cat / "cpus").mkdir(parents=True)

        result = heal_catalog(cat)
        assert "Cura concluída" in result

