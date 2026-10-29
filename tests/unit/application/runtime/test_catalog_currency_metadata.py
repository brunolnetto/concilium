"""Explicit catalog currency metadata survives filesystem and storage loading."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from concilium.application.runtime.mixins import _catalog_storage as cs
from concilium.application.runtime.mixins.catalog import CatalogMixin
from concilium.application.runtime.exceptions import RuntimeDomainError
from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _mixin(config_root: Path) -> CatalogMixin:
    mixin = CatalogMixin.__new__(CatalogMixin)
    mixin.config_root = config_root
    mixin._config_cache = {}
    return mixin


def _metadata(currency: str = "BRL") -> dict[str, str]:
    return {
        "schema": "concilium.catalog-metadata.v1",
        "currency": currency,
        "currency_basis": "catalog-wide denomination declared for this dataset; no FX conversion implied",
    }


def _empty_bundle() -> dict[str, object]:
    return {
        "cpus": [],
        "insumos": [],
        "templates": {},
        "estruturas_indiretas": [],
        "produtividades": [],
        "producoes": [],
    }


def test_filesystem_loader_attaches_currency_on_valid_bundle(tmp_path: Path, monkeypatch) -> None:
    cat_dir = tmp_path / "catalogos" / "cat1"
    cat_dir.mkdir(parents=True)
    _write_json(cat_dir / ".catalog_bundle.json", _empty_bundle())
    _write_json(cat_dir / "catalog_metadata.json", _metadata())
    mixin = _mixin(tmp_path)
    monkeypatch.setattr(mixin, "_catalog_bundle_valid", lambda *_args: True)

    loaded = mixin._load_catalogo_from_disk("cat1")

    assert loaded["currency"] == "BRL"
    assert loaded["currency_source"] == "catalog_metadata.json"


def test_filesystem_loader_preserves_currency_when_rebuilding_bundle(tmp_path: Path) -> None:
    cat_dir = tmp_path / "catalogos" / "cat1"
    cat_dir.mkdir(parents=True)
    _write_json(cat_dir / "catalog_metadata.json", _metadata())

    loaded = _mixin(tmp_path)._load_catalogo_from_disk("cat1")
    rebuilt = json.loads((cat_dir / ".catalog_bundle.json").read_text(encoding="utf-8"))

    assert loaded["currency"] == "BRL"
    assert loaded["currency_source"] == "catalog_metadata.json"
    assert rebuilt["currency"] == "BRL"


def test_filesystem_loader_rejects_invalid_currency_metadata(tmp_path: Path) -> None:
    cat_dir = tmp_path / "catalogos" / "cat1"
    cat_dir.mkdir(parents=True)
    _write_json(cat_dir / "catalog_metadata.json", _metadata("brl"))

    with pytest.raises(RuntimeDomainError, match="Moeda do catálogo ausente ou inválida"):
        _mixin(tmp_path)._load_catalogo_from_disk("cat1")


def test_remote_storage_loader_attaches_currency(tmp_path: Path) -> None:
    cat_dir = tmp_path / "config" / "catalogos" / "cat1"
    cat_dir.mkdir(parents=True)
    _write_json(cat_dir / "catalog_metadata.json", _metadata())
    storage = LocalBlobStorage(tmp_path)

    with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
        with patch.object(cs, "build_blob_storage", return_value=storage):
            loaded = cs.load_catalogo_via_storage(tmp_path, "cat1", force_refresh=True)

    assert loaded["currency"] == "BRL"
    assert loaded["currency_source"] == "catalog_metadata.json"


def test_remote_storage_loader_keeps_missing_metadata_unverified(tmp_path: Path) -> None:
    cat_dir = tmp_path / "config" / "catalogos" / "cat1"
    cat_dir.mkdir(parents=True)
    storage = LocalBlobStorage(tmp_path)

    with patch.object(cs, "catalog_storage_backend", return_value="sharepoint"):
        with patch.object(cs, "build_blob_storage", return_value=storage):
            loaded = cs.load_catalogo_via_storage(tmp_path, "cat1", force_refresh=True)

    assert "currency" not in loaded
