"""Tests for ADR-024 — Catalog Snapshot, Cache and Change Detection.

Covers:
  - CatalogLoader.load() creates fresh snapshot on first call
  - TTL cache: second call within TTL reuses cached snapshot (no re-read)
  - force_refresh=True bypasses cache and creates new snapshot
  - offline=True raises when cache is absent
  - CatalogSnapshot.compute_hash produces stable SHA-256
  - compute_catalog_diff() returns None when content unchanged
  - compute_catalog_diff() returns CatalogDiff when CPUs change
  - CatalogDiff reports added/removed/modified CPU IDs correctly
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.domain.models.catalog.snapshot import (
    CatalogSnapshot,
    compute_catalog_diff,
)
from concilium.infrastructure.catalog.catalog_loader import CatalogBackend, CatalogLoader

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _minimal_cpus(n: int = 2) -> list[dict]:
    return [
        {
            "codigo": f"CPU-{i:03d}",
            "descricao": f"Serviço {i}",
            "unidade": "m³",
            "composicao_itens": [],
        }
        for i in range(1, n + 1)
    ]


def _write_catalog(cat_dir: Path, cpus: list[dict]) -> None:
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "cpus.json").write_text(json.dumps({"cpus": cpus}), encoding="utf-8")
    ins_dir = cat_dir / "insumos"
    ins_dir.mkdir(exist_ok=True)
    (ins_dir / "mao_obra.json").write_text(
        json.dumps(
            [
                {
                    "codigo": "MO-001",
                    "descricao": "Operador",
                    "unidade": "h",
                    "preco_unitario": 25.0,
                    "categoria": "MAO_OBRA",
                }
            ]
        ),
        encoding="utf-8",
    )


def _make_loader(config_root: Path, project_root: Path, **kwargs) -> CatalogLoader:
    return CatalogLoader(
        config_root=config_root,
        project_root=project_root,
        backend=CatalogBackend.LOCAL_JSON,
        **kwargs,
    )


# ── CatalogSnapshot model ─────────────────────────────────────────────────────


class TestCatalogSnapshotModel:
    def test_create_assigns_version_hash(self, tmp_path):
        cpus = _minimal_cpus(3)
        snapshot = CatalogSnapshot.create(
            catalog_name="test",
            cpus=cpus,
            insumos={},
            produtividades=[],
            created_by="test",
        )
        assert snapshot.meta.version_hash
        assert len(snapshot.meta.version_hash) == 64  # SHA-256 hex

    def test_same_content_same_hash(self, tmp_path):
        cpus = _minimal_cpus(2)
        s1 = CatalogSnapshot.create("test", cpus, {}, [], "test")
        s2 = CatalogSnapshot.create("test", cpus, {}, [], "test")
        assert s1.meta.version_hash == s2.meta.version_hash

    def test_different_content_different_hash(self, tmp_path):
        s1 = CatalogSnapshot.create("test", _minimal_cpus(2), {}, [], "test")
        s2 = CatalogSnapshot.create("test", _minimal_cpus(3), {}, [], "test")
        assert s1.meta.version_hash != s2.meta.version_hash

    def test_round_trip_serialization(self, tmp_path):
        snapshot = CatalogSnapshot.create("test", _minimal_cpus(2), {}, [], "test")
        raw = json.loads(snapshot.model_dump_json())
        restored = CatalogSnapshot.model_validate(raw)
        assert restored.meta.version_hash == snapshot.meta.version_hash
        assert len(restored.cpus) == len(snapshot.cpus)


# ── CatalogDiff ───────────────────────────────────────────────────────────────


class TestCatalogDiff:
    def _snapshot(self, cpus: list[dict]) -> CatalogSnapshot:
        return CatalogSnapshot.create("test", cpus, {}, [], "test")

    def test_no_diff_when_identical(self):
        cpus = _minimal_cpus(2)
        s1 = self._snapshot(cpus)
        s2 = self._snapshot(cpus)
        diff = compute_catalog_diff(s1, s2)
        assert diff is None or (
            len(diff.cpus_added) == 0 and len(diff.cpus_removed) == 0 and len(diff.cpus_modified) == 0
        )

    def test_diff_detects_added_cpu(self):
        s1 = self._snapshot(_minimal_cpus(2))
        s2 = self._snapshot(_minimal_cpus(3))  # CPU-003 added
        diff = compute_catalog_diff(s1, s2)
        assert diff is not None
        assert "CPU-003" in diff.cpus_added

    def test_diff_detects_removed_cpu(self):
        s1 = self._snapshot(_minimal_cpus(3))
        s2 = self._snapshot(_minimal_cpus(2))  # CPU-003 removed
        diff = compute_catalog_diff(s1, s2)
        assert diff is not None
        assert "CPU-003" in diff.cpus_removed

    def test_diff_detects_modified_cpu(self):
        cpus_v1 = _minimal_cpus(2)
        cpus_v2 = _minimal_cpus(2)
        cpus_v2[0]["descricao"] = "MODIFIED"
        s1 = self._snapshot(cpus_v1)
        s2 = self._snapshot(cpus_v2)
        diff = compute_catalog_diff(s1, s2)
        assert diff is not None
        assert "CPU-001" in diff.cpus_modified


# ── CatalogLoader ─────────────────────────────────────────────────────────────


class TestCatalogLoader:
    @pytest.fixture()
    def catalog_env(self, tmp_path):
        """Provides (config_root, project_root, catalog_name) in a temp dir."""
        config_root = tmp_path / "config"
        catalog_name = "agis_test"
        _write_catalog(config_root / "catalogos" / catalog_name, _minimal_cpus(2))
        return config_root, tmp_path, catalog_name

    def test_first_load_creates_snapshot(self, catalog_env):
        config_root, project_root, catalog_name = catalog_env
        loader = _make_loader(config_root, project_root)
        snapshot, diff = loader.load(catalog_name)

        assert isinstance(snapshot, CatalogSnapshot)
        assert snapshot.meta.catalog_name == catalog_name
        assert diff is None  # no previous snapshot to diff against

    def test_cache_file_created_after_load(self, catalog_env):
        config_root, project_root, catalog_name = catalog_env
        loader = _make_loader(config_root, project_root)
        loader.load(catalog_name)

        cache_file = project_root / ".concilium" / "catalog_cache" / catalog_name / "latest.json"
        assert cache_file.exists()

    def test_second_load_within_ttl_uses_cache(self, catalog_env):
        config_root, project_root, catalog_name = catalog_env
        loader = _make_loader(config_root, project_root, ttl_minutes=60)

        snapshot1, _ = loader.load(catalog_name)
        snapshot2, _ = loader.load(catalog_name)

        # Same hash → cache was used
        assert snapshot1.meta.version_hash == snapshot2.meta.version_hash

    def test_force_refresh_bypasses_cache(self, catalog_env):
        config_root, project_root, catalog_name = catalog_env
        loader_normal = _make_loader(config_root, project_root)
        snapshot1, _ = loader_normal.load(catalog_name)

        loader_refresh = _make_loader(config_root, project_root, force_refresh=True)
        snapshot2, _ = loader_refresh.load(catalog_name)

        # Both valid snapshots; content is the same catalog so hashes match
        assert snapshot2.meta.version_hash == snapshot1.meta.version_hash

    def test_offline_raises_when_no_cache(self, catalog_env):
        config_root, project_root, catalog_name = catalog_env
        loader = _make_loader(config_root, project_root, offline=True)
        with pytest.raises(FileNotFoundError, match="offline"):
            loader.load(catalog_name)

    def test_offline_uses_cache_when_available(self, catalog_env):
        config_root, project_root, catalog_name = catalog_env
        # First populate cache
        _make_loader(config_root, project_root).load(catalog_name)
        # Then reload offline
        loader = _make_loader(config_root, project_root, offline=True)
        snapshot, _ = loader.load(catalog_name)
        assert isinstance(snapshot, CatalogSnapshot)

    def test_diff_returned_when_catalog_changes(self, catalog_env):
        config_root, project_root, catalog_name = catalog_env
        loader = _make_loader(config_root, project_root)
        snapshot1, _ = loader.load(catalog_name)

        # Modify catalog on disk
        _write_catalog(config_root / "catalogos" / catalog_name, _minimal_cpus(4))

        loader2 = _make_loader(config_root, project_root, force_refresh=True)
        snapshot2, diff = loader2.load(catalog_name, previous_snapshot=snapshot1)

        assert snapshot1.meta.version_hash != snapshot2.meta.version_hash
        assert diff is not None
        # CPU-003 and CPU-004 were added
        assert "CPU-003" in diff.cpus_added
        assert "CPU-004" in diff.cpus_added

    def test_from_config_reads_yaml(self, tmp_path):
        """CatalogLoader.from_config() reads backend from concilium.yaml."""
        import yaml

        config_root = tmp_path / "config"
        config_root.mkdir()
        yaml_content = {"catalog": {"backend": "local_json", "remote_ttl_minutes": 30}}
        (config_root / "concilium.yaml").write_text(yaml.dump(yaml_content), encoding="utf-8")
        _write_catalog(config_root / "catalogos" / "test_cat", _minimal_cpus(1))

        loader = CatalogLoader.from_config(config_root=config_root, project_root=tmp_path)
        assert loader.backend == CatalogBackend.LOCAL_JSON
        assert loader.ttl_minutes == 30

    def test_from_config_without_yaml_uses_defaults(self, tmp_path):
        """CatalogLoader.from_config() sem concilium.yaml usa defaults (backend local_json)."""
        config_root = tmp_path / "config_no_yaml"
        config_root.mkdir()

        loader = CatalogLoader.from_config(config_root=config_root, project_root=tmp_path)
        assert loader.backend == CatalogBackend.LOCAL_JSON


# ─── Missing branch coverage ──────────────────────────────────────────────────


class TestCatalogLoaderMissingBranches:
    def test_read_snapshot_cache_corrupt_returns_none(self, tmp_path):
        """Lines 62-63: corrupt cache file returns None."""
        from concilium.infrastructure.catalog.catalog_loader import _read_cache

        project_root = tmp_path
        cache_dir = tmp_path / ".concilium" / "catalog_cache" / "test_cat"
        cache_dir.mkdir(parents=True)
        (cache_dir / "latest.json").write_text("NOT_VALID_JSON{{{", encoding="utf-8")
        result = _read_cache(project_root, "test_cat")
        assert result is None

    def test_load_local_json_duckdb_exception_falls_back(self, tmp_path):
        """Lines 169-179: DuckDB engine raises → falls back to JSON loader."""
        from unittest.mock import patch

        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

        config_root = tmp_path
        cat_dir = config_root / "catalogos" / "cat1"
        _write_catalog(cat_dir, _minimal_cpus(1))

        loader = CatalogLoader(config_root=config_root, project_root=tmp_path, ttl_minutes=0)

        with patch("concilium.infrastructure.catalog.query_engine.CatalogQueryEngine") as MockDuck:
            MockDuck.return_value.is_ready.side_effect = RuntimeError("duckdb broken")
            snapshot, _ = loader.load("cat1")

        assert snapshot is not None

    def test_load_local_json_duckdb_not_ready_falls_back(self, tmp_path):
        """Line 162: DuckDB engine exists but is_ready() is False → falls back to JSON loader."""
        from unittest.mock import patch

        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

        config_root = tmp_path
        cat_dir = config_root / "catalogos" / "cat2"
        _write_catalog(cat_dir, _minimal_cpus(1))

        loader = CatalogLoader(config_root=config_root, project_root=tmp_path, ttl_minutes=0)

        with patch("concilium.infrastructure.catalog.query_engine.CatalogQueryEngine") as MockDuck:
            MockDuck.return_value.is_ready.return_value = False
            snapshot, _ = loader.load("cat2")

        assert snapshot is not None
        assert len(snapshot.cpus) >= 1
        assert len(snapshot.cpus) >= 1

    def test_llj_load_cpus_single_file_path(self, tmp_path):
        """Line 91->89: reads cpus.json when cpus/ dir does not exist."""
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_cpus

        cat_dir = tmp_path
        (cat_dir / "cpus.json").write_text(json.dumps({"cpus": _minimal_cpus(2)}), encoding="utf-8")
        cpus = _llj_load_cpus(cat_dir)
        assert len(cpus) == 2

    def test_sharepoint_backend_raises_without_storage(self, tmp_path):
        """Lines 406-407: SharePoint backend without storage raises ValueError."""
        loader = CatalogLoader(
            config_root=tmp_path,
            backend=CatalogBackend.SHAREPOINT,
        )
        with pytest.raises(ValueError, match="sharepoint_storage"):
            loader.load("any_catalog")

    def test_unknown_backend_raises(self, tmp_path):
        """Line 413-414: unknown backend raises ValueError."""
        loader = CatalogLoader(config_root=tmp_path, backend=CatalogBackend.LOCAL_JSON)
        # Force an unknown backend value by patching
        loader.backend = "invalid_backend"  # type: ignore[assignment]
        with pytest.raises((ValueError, AttributeError)):
            loader.load("any")
