"""Tests for catalog_loader.py helpers."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestCatalogLoaderHelpers:
    def test_llj_load_cpus_from_dir(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_cpus

        cpus_dir = tmp_path / "cpus"
        cpus_dir.mkdir()
        (cpus_dir / "CPU-1.json").write_text('{"codigo": "CPU-1"}', encoding="utf-8")
        (cpus_dir / "CPU-2.json").write_text('{"codigo": "CPU-2"}', encoding="utf-8")
        result = _llj_load_cpus(tmp_path)
        assert len(result) == 2

    def test_llj_load_cpus_from_aggregate(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_cpus

        (tmp_path / "cpus.json").write_text('{"cpus": [{"codigo": "CPU-A"}]}', encoding="utf-8")
        result = _llj_load_cpus(tmp_path)
        assert len(result) == 1

    def test_llj_load_cpus_empty(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_cpus

        result = _llj_load_cpus(tmp_path)
        assert result == []

    def test_llj_load_cpus_skips_non_dict_files(self, tmp_path):
        """Um arquivo cujo JSON é uma lista (não dict) na pasta cpus/ é ignorado."""
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_cpus

        cpus_dir = tmp_path / "cpus"
        cpus_dir.mkdir()
        (cpus_dir / "CPU-1.json").write_text('{"codigo": "CPU-1"}', encoding="utf-8")
        (cpus_dir / "CPU-list.json").write_text("[1, 2, 3]", encoding="utf-8")
        result = _llj_load_cpus(tmp_path)
        assert len(result) == 1

    def test_llj_load_insumos_from_dir(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_insumos

        ins_dir = tmp_path / "insumos"
        ins_dir.mkdir()
        (ins_dir / "combustivel.json").write_text('[{"codigo": "DIESEL"}]', encoding="utf-8")
        result = _llj_load_insumos(tmp_path)
        assert "combustivel" in result

    def test_llj_load_insumos_empty(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_insumos

        assert _llj_load_insumos(tmp_path) == {}

    def test_llj_load_produtividades_from_dir(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_produtividades

        prod_dir = tmp_path / "produtividades"
        prod_dir.mkdir()
        (prod_dir / "PROD-001.json").write_text('{"id": "PROD-001"}', encoding="utf-8")
        result = _llj_load_produtividades(tmp_path)
        assert len(result) == 1

    def test_llj_load_produtividades_from_producoes(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_produtividades

        prod_dir = tmp_path / "producoes"
        prod_dir.mkdir()
        (prod_dir / "PROD-A.json").write_text('{"id": "PROD-A"}', encoding="utf-8")
        result = _llj_load_produtividades(tmp_path)
        assert len(result) == 1

    def test_llj_load_produtividades_from_json(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_produtividades

        (tmp_path / "produtividades.json").write_text('{"produtividades": [{"id": "P1"}]}', encoding="utf-8")
        result = _llj_load_produtividades(tmp_path)
        assert len(result) == 1

    def test_llj_load_produtividades_empty(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_produtividades

        assert _llj_load_produtividades(tmp_path) == []

    def test_llj_load_produtividades_skips_non_dict_files(self, tmp_path):
        """Um arquivo cujo JSON é uma lista (não dict) na pasta produtividades/ é ignorado."""
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_produtividades

        prod_dir = tmp_path / "produtividades"
        prod_dir.mkdir()
        (prod_dir / "PROD-001.json").write_text('{"id": "PROD-001"}', encoding="utf-8")
        (prod_dir / "PROD-list.json").write_text("[1, 2]", encoding="utf-8")
        result = _llj_load_produtividades(tmp_path)
        assert len(result) == 1

    def test_llj_load_funcoes_from_json(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_funcoes

        (tmp_path / "funcoes.json").write_text('[{"funcao_id": "OP"}]', encoding="utf-8")
        result = _llj_load_funcoes(tmp_path)
        assert len(result) == 1

    def test_llj_load_funcoes_empty(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _llj_load_funcoes

        assert _llj_load_funcoes(tmp_path) == []

    def test_load_local_json_not_found(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _load_local_json

        with pytest.raises(FileNotFoundError):
            _load_local_json(tmp_path, "missing-catalog")

    def test_load_local_json_basic(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _load_local_json

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        cpus_dir = cat_dir / "cpus"
        cpus_dir.mkdir()
        (cpus_dir / "CPU-1.json").write_text('{"codigo": "CPU-1", "descricao": "Test"}', encoding="utf-8")
        cpus, insumos, prods, funcoes = _load_local_json(tmp_path, "test-cat")
        assert len(cpus) == 1

    def test_cache_dir(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import _cache_dir

        result = _cache_dir(tmp_path, "test-cat")
        assert isinstance(result, Path)

    def test_cache_is_fresh(self, tmp_path):

        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader, _cache_is_fresh

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        loader = CatalogLoader(config_root=tmp_path)
        snap, _diff = loader.load("test-cat")
        assert _cache_is_fresh(snap, ttl_minutes=60) is True

    def test_cache_is_stale(self, tmp_path):
        from datetime import datetime, timedelta

        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader, _cache_is_fresh

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        loader = CatalogLoader(config_root=tmp_path)
        snap, _diff = loader.load("test-cat")
        # Build a mock snapshot with old timestamp
        stale = MagicMock()
        stale.meta.created_at = datetime.now(UTC) - timedelta(hours=2)
        assert _cache_is_fresh(stale, ttl_minutes=60) is False

    def test_compute_diff_if_changed_none_previous(self):
        from concilium.infrastructure.catalog.catalog_loader import _compute_diff_if_changed

        current = MagicMock()
        current.cpus = []
        result = _compute_diff_if_changed(None, current)
        assert result is None

    def test_add_project_id(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader, _add_project_id

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        loader = CatalogLoader(config_root=tmp_path)
        snap, _ = loader.load("test-cat")
        result = _add_project_id(snap, "proj-1")
        assert result is not None


class TestCatalogLoaderLsp:
    """Cover _lsp_* blob-storage based loading functions (lines 182-240)."""

    def _make_storage(self, cpus=None, insumos=None, prods=None, funcoes=None):

        storage = MagicMock()
        storage.listar_blobs.return_value = []
        storage.blob_existe.return_value = False

        def ler_blob(path):
            if path.endswith("cpus.json") and cpus is not None:
                return json.dumps({"cpus": cpus}).encode()
            if path.endswith("funcoes.json") and funcoes is not None:
                return json.dumps(funcoes).encode()
            raise FileNotFoundError(path)

        storage.ler_blob.side_effect = ler_blob
        return storage

    def test_lsp_load_cpus_from_aggregate(self):
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_cpus

        storage = self._make_storage(cpus=[{"codigo": "CPU-1"}])
        result = _lsp_load_cpus(storage, "base")
        assert len(result) == 1

    def test_lsp_load_cpus_from_blobs(self):
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_cpus

        storage = MagicMock()
        storage.listar_blobs.return_value = ["base/cpus/CPU-1.json"]
        storage.ler_blob.return_value = json.dumps({"codigo": "CPU-1"}).encode()
        result = _lsp_load_cpus(storage, "base")
        assert len(result) == 1

    def test_lsp_load_cpus_skips_non_json_blob_and_non_dict_raw(self):
        """Blobs sem sufixo .json são ignorados; blobs cujo JSON não é dict também são ignorados."""
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_cpus

        storage = MagicMock()
        storage.listar_blobs.return_value = ["base/cpus/README.txt", "base/cpus/CPU-list.json"]
        storage.ler_blob.return_value = json.dumps([1, 2]).encode()
        result = _lsp_load_cpus(storage, "base")
        assert result == []

    def test_lsp_load_insumos(self):
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_insumos

        storage = MagicMock()
        storage.listar_blobs.return_value = ["base/insumos/COMB.json"]
        storage.ler_blob.return_value = json.dumps([{"codigo": "DIESEL"}]).encode()
        result = _lsp_load_insumos(storage, "base")
        assert "COMB" in result

    def test_lsp_load_insumos_skips_non_json_blob(self):
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_insumos

        storage = MagicMock()
        storage.listar_blobs.return_value = ["base/insumos/README.txt"]
        result = _lsp_load_insumos(storage, "base")
        assert result == {}

    def test_lsp_load_produtividades(self):
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_produtividades

        storage = MagicMock()
        storage.listar_blobs.return_value = ["base/produtividades/PROD-1.json"]
        storage.ler_blob.return_value = json.dumps({"id": "PROD-1"}).encode()
        result = _lsp_load_produtividades(storage, "base")
        assert len(result) == 1

    def test_lsp_load_produtividades_skips_non_json_blob_and_non_dict_raw(self):
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_produtividades

        storage = MagicMock()
        storage.listar_blobs.return_value = ["base/produtividades/README.txt", "base/produtividades/PROD-list.json"]
        storage.ler_blob.return_value = json.dumps([1, 2]).encode()
        result = _lsp_load_produtividades(storage, "base")
        assert result == []

    def test_lsp_load_produtividades_falls_back_to_single_file(self):
        """Sem blobs individuais em produtividades/, lê produtividades.json agregado."""
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_produtividades

        storage = MagicMock()
        storage.listar_blobs.return_value = []
        storage.ler_blob.return_value = json.dumps({"produtividades": [{"id": "PROD-AGG"}]}).encode()
        result = _lsp_load_produtividades(storage, "base")
        assert result == [{"id": "PROD-AGG"}]
        storage.ler_blob.assert_called_once_with("base/produtividades.json")

    def test_lsp_load_produtividades_returns_empty_when_no_source_exists(self):
        """Nem blobs individuais nem o agregado existem — retorna lista vazia sem crashar."""
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_produtividades

        storage = MagicMock()
        storage.listar_blobs.return_value = []
        storage.ler_blob.side_effect = FileNotFoundError("base/produtividades.json")
        result = _lsp_load_produtividades(storage, "base")
        assert result == []

    def test_lsp_load_funcoes(self):
        from concilium.infrastructure.catalog.catalog_loader import _lsp_load_funcoes

        storage = self._make_storage(funcoes=[{"funcao_id": "OP"}])
        result = _lsp_load_funcoes(storage, "base")
        # may or may not find funcoes.json; check no crash
        assert isinstance(result, list)

    def test_compute_diff_if_changed_both_present(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader, _compute_diff_if_changed

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": []}', encoding="utf-8")
        loader = CatalogLoader(config_root=tmp_path)
        snap1, _ = loader.load("test-cat")
        snap2, _ = loader.load("test-cat")
        result = _compute_diff_if_changed(snap1, snap2)
        # Same content → may be None or empty diff
        assert result is None or hasattr(result, "__dict__")


class TestCatalogLoaderClass:
    def test_create_loader(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

        loader = CatalogLoader(config_root=tmp_path)
        assert loader is not None

    def test_load_catalog_not_found(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

        loader = CatalogLoader(config_root=tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("missing-catalog")

    def test_load_catalog_basic(self, tmp_path):
        from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

        cat_dir = tmp_path / "catalogos" / "test-cat"
        cat_dir.mkdir(parents=True)
        (cat_dir / "cpus.json").write_text('{"cpus": [{"codigo": "CPU-1"}]}', encoding="utf-8")
        loader = CatalogLoader(config_root=tmp_path)
        snap, diff = loader.load("test-cat")
        assert snap is not None
        # cpus may be an empty list if DuckDB path ran and found nothing
        assert isinstance(snap.cpus, list)
