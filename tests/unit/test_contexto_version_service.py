"""Coverage tests for contexto_version_service.py — targets all 15 missing lines."""

from __future__ import annotations

import json
from pathlib import Path

from concilium.application.services.catalog.contexto_version_service import (
    ConfigVersionService,
    TemaVersionService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _svc(tmp_path: Path, subdir: str = "contextos", include_flat: bool = False) -> ConfigVersionService:
    return ConfigVersionService(tmp_path, subdir, include_flat_files=include_flat)


# ---------------------------------------------------------------------------
# Line 99: flat-file entity_id already in seen_ids → skip
# ---------------------------------------------------------------------------


class TestListEntitiesSkipDuplicateFlatFile:
    def test_flat_file_entity_already_in_seen_ids_skipped(self, tmp_path):
        """Line 99: flat file with same id as a versioned dir → deduplicated."""
        svc = _svc(tmp_path, include_flat=True)
        root = tmp_path / "contextos"
        root.mkdir()

        # Versioned entity dir with id "ctx-001"
        entity_dir = root / "ctx-001"
        (entity_dir / "versions").mkdir(parents=True)
        meta = {"id": "ctx-001", "nome": "Contexto A"}
        (entity_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        # Flat file with same id — should be skipped
        flat = root / "ctx-001.json"
        flat.write_text(json.dumps({"id": "ctx-001", "nome": "Flat Dup"}), encoding="utf-8")

        result = svc.list_entities()
        names = [e["id"] for e in result]
        assert names.count("ctx-001") == 1


# ---------------------------------------------------------------------------
# Lines 131-132: list_versions with corrupt flat JSON → payload = {}
# ---------------------------------------------------------------------------


class TestListVersionsFlatCorruptJson:
    def test_corrupt_flat_file_returns_empty_payload(self, tmp_path):
        """Lines 131-132: flat file exists but has invalid JSON → payload = {}."""
        svc = _svc(tmp_path)
        root = tmp_path / "contextos"
        root.mkdir()

        flat = root / "bad-entity.json"
        flat.write_text("not json at all", encoding="utf-8")

        result = svc.list_versions("bad-entity")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["version"] == "v1"


# ---------------------------------------------------------------------------
# Lines 163-164: create_version with non-numeric version stem → ValueError ignored
# ---------------------------------------------------------------------------


class TestCreateVersionNonNumericStem:
    def test_non_numeric_version_stem_skipped(self, tmp_path):
        """Lines 163-164: existing version file named 'vABC.json' → ValueError in int() → pass."""
        svc = _svc(tmp_path)
        root = tmp_path / "contextos"
        entity_dir = root / "ent1"
        versions_dir = entity_dir / "versions"
        versions_dir.mkdir(parents=True)

        # Create a bad version filename that will cause ValueError
        bad_v = versions_dir / "vABC.json"
        bad_v.write_text(json.dumps({"version": "vABC", "nome": "test"}), encoding="utf-8")

        result = svc.create_version("ent1", fields={"nome": "Updated"}, author="tester", motivo="test")
        # Should continue and create v1 (last_n stays 0 due to ValueError)
        assert result["version"] == "v1"


# ---------------------------------------------------------------------------
# Lines 177-178: create_version with corrupt flat file → base = {}
# ---------------------------------------------------------------------------


class TestCreateVersionCorruptFlatFile:
    def test_corrupt_flat_base_defaults_to_empty(self, tmp_path):
        """Lines 177-178: flat file for base has invalid JSON → base = {}."""
        svc = _svc(tmp_path)
        root = tmp_path / "contextos"
        entity_dir = root / "ent2"
        versions_dir = entity_dir / "versions"
        versions_dir.mkdir(parents=True)

        # Flat file exists but is corrupt
        flat = root / "ent2.json"
        flat.write_text("corrupted!!", encoding="utf-8")

        result = svc.create_version("ent2", fields={"nome": "New"}, author="a", motivo="m")
        assert result["version"] == "v1"
        assert result["nome"] == "New"


# ---------------------------------------------------------------------------
# Lines 249-251: _read_meta with corrupt meta file → return {"id": entity_dir.name}
# ---------------------------------------------------------------------------


class TestReadMetaCorruptFile:
    def test_corrupt_meta_falls_back_to_dir_name(self, tmp_path):
        """Lines 249-251: meta file exists but invalid JSON → return id from dir name."""
        svc = _svc(tmp_path)
        root = tmp_path / "contextos"
        entity_dir = root / "ent-corrupt"
        entity_dir.mkdir(parents=True)

        bad_meta = entity_dir / "meta.json"
        bad_meta.write_text("not json", encoding="utf-8")

        meta = svc._read_meta(entity_dir)
        assert meta == {"id": "ent-corrupt"}


# ---------------------------------------------------------------------------
# Line 269: _list_versions when versions dir does not exist → return []
# ---------------------------------------------------------------------------


class TestListVersionsNoVersionsDir:
    def test_no_versions_dir_returns_empty(self, tmp_path):
        """Line 269: versions_dir does not exist → return []."""
        entity_dir = tmp_path / "some-entity"
        entity_dir.mkdir()

        result = ConfigVersionService._list_versions(entity_dir)
        assert result == []


# ---------------------------------------------------------------------------
# Lines 285-286: _list_versions with corrupt version file → exception silenced
# ---------------------------------------------------------------------------


class TestListVersionsCorruptVersionFile:
    def test_corrupt_version_file_skipped(self, tmp_path):
        """Lines 285-286: version file has invalid JSON → except Exception: pass."""
        entity_dir = tmp_path / "ent"
        versions_dir = entity_dir / "versions"
        versions_dir.mkdir(parents=True)

        (versions_dir / "v1.json").write_text("valid JSON? No!", encoding="utf-8")
        (versions_dir / "v2.json").write_text(json.dumps({"version": "v2", "nome": "ok"}), encoding="utf-8")

        result = ConfigVersionService._list_versions(entity_dir)
        assert len(result) == 1
        assert result[0]["version"] == "v2"


# ---------------------------------------------------------------------------
# Lines 317, 320: TemaVersionService __init__ and list_temas
# ---------------------------------------------------------------------------


class TestTemaVersionService:
    def test_init_and_list_temas(self, tmp_path):
        """Lines 317, 320: TemaVersionService instantiation and list_temas()."""
        svc = TemaVersionService(tmp_path)
        root = tmp_path / "temas"
        root.mkdir()

        entity_dir = root / "tema1"
        entity_dir.mkdir()
        (entity_dir / "meta.json").write_text(json.dumps({"id": "tema1", "nome": "Tema 1"}), encoding="utf-8")

        temas = svc.list_temas()
        assert any(t["id"] == "tema1" for t in temas)
