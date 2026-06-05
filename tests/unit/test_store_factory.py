from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
from concilium.infrastructure.storage import store_factory
from concilium.infrastructure.storage.store_factory import build_project_repository, resolve_store_backend


def test_resolve_store_backend_defaults_to_filesystem(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM__STORE_BACKEND", raising=False)
    assert resolve_store_backend() == "filesystem"


def test_resolve_store_backend_normalizes(monkeypatch) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "  Filesystem ")
    assert resolve_store_backend() == "filesystem"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("local_json", "filesystem"),
        ("local-json", "filesystem"),
        ("local", "filesystem"),
        ("sharepoint", "sharepoint"),
        ("S3", "s3"),
    ],
)
def test_resolve_store_backend_aliases(monkeypatch, raw: str, expected: str) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", raw)
    assert resolve_store_backend() == expected


def test_projects_prefix_defaults_and_normalizes(monkeypatch) -> None:
    monkeypatch.delenv("CONCILIUM__STORE_PROJECTS_PREFIX", raising=False)
    assert store_factory._projects_prefix() == "projetos"

    monkeypatch.setenv("CONCILIUM__STORE_PROJECTS_PREFIX", " /corp/projetos/ ")
    assert store_factory._projects_prefix() == "corp/projetos"

    monkeypatch.setenv("CONCILIUM__STORE_PROJECTS_PREFIX", "   ")
    assert store_factory._projects_prefix() == "projetos"


def test_build_project_repository_filesystem(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "filesystem")
    repo = build_project_repository(tmp_path)
    assert isinstance(repo, FileProjectRepository)


def test_build_project_repository_local_json_alias(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "local_json")
    repo = build_project_repository(tmp_path)
    assert isinstance(repo, FileProjectRepository)


def test_build_project_repository_sharepoint_dispatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "sharepoint")
    sentinel = object()
    monkeypatch.setattr(store_factory, "_build_sharepoint_repository", lambda: sentinel)
    assert build_project_repository(tmp_path) is sentinel


def test_build_project_repository_s3_dispatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "s3")
    sentinel = object()
    monkeypatch.setattr(store_factory, "_build_s3_repository", lambda: sentinel)
    assert build_project_repository(tmp_path) is sentinel


def test_build_project_repository_rejects_unknown_backend(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "unknown")
    with pytest.raises(ValueError, match="Unsupported CONCILIUM__STORE_BACKEND"):
        build_project_repository(tmp_path)


def test_build_sharepoint_repository_wires_cache_and_prefix(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    class DummySharePointBlobStorage:
        @classmethod
        def from_env(cls, *, cache_dir=None):
            calls["cache_dir"] = cache_dir
            return "sp-storage"

    class DummyStorageProjectRepository:
        def __init__(self, storage, projects_prefix):
            calls["storage"] = storage
            calls["projects_prefix"] = projects_prefix

    monkeypatch.setenv("CONCILIUM__SP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CONCILIUM__STORE_PROJECTS_PREFIX", " /enterprise/projects/ ")

    monkeypatch.setitem(
        sys.modules,
        "concilium.infrastructure.adapters.sharepoint_blob_storage",
        types.SimpleNamespace(SharePointBlobStorage=DummySharePointBlobStorage),
    )
    monkeypatch.setitem(
        sys.modules,
        "concilium.infrastructure.storage.storage_project_repository",
        types.SimpleNamespace(StorageProjectRepository=DummyStorageProjectRepository),
    )

    repo = store_factory._build_sharepoint_repository()
    assert isinstance(repo, DummyStorageProjectRepository)
    assert calls["storage"] == "sp-storage"
    assert calls["projects_prefix"] == "enterprise/projects"
    assert calls["cache_dir"] == (tmp_path / "cache")


def test_build_s3_repository_wires_prefix(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class DummyS3BlobStorage:
        @classmethod
        def from_env(cls):
            calls["from_env"] = True
            return "s3-storage"

    class DummyStorageProjectRepository:
        def __init__(self, storage, projects_prefix):
            calls["storage"] = storage
            calls["projects_prefix"] = projects_prefix

    monkeypatch.setenv("CONCILIUM__STORE_PROJECTS_PREFIX", "projects")
    monkeypatch.setitem(
        sys.modules,
        "concilium.infrastructure.adapters.s3_blob_storage",
        types.SimpleNamespace(S3BlobStorage=DummyS3BlobStorage),
    )
    monkeypatch.setitem(
        sys.modules,
        "concilium.infrastructure.storage.storage_project_repository",
        types.SimpleNamespace(StorageProjectRepository=DummyStorageProjectRepository),
    )

    repo = store_factory._build_s3_repository()
    assert isinstance(repo, DummyStorageProjectRepository)
    assert calls["from_env"] is True
    assert calls["storage"] == "s3-storage"
    assert calls["projects_prefix"] == "projects"
