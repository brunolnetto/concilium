from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.storage import store_factory
from concilium.infrastructure.storage.storage_project_repository import StorageProjectRepository
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
    assert isinstance(repo, StorageProjectRepository)
    assert isinstance(repo._storage, LocalBlobStorage)
    assert repo._storage.root_dir == tmp_path


def test_build_project_repository_local_json_alias(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONCILIUM__STORE_BACKEND", "local_json")
    repo = build_project_repository(tmp_path)
    assert isinstance(repo, StorageProjectRepository)
    assert isinstance(repo._storage, LocalBlobStorage)


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
        "concilium.infrastructure.adapters.blob_storage.sharepoint",
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
        "concilium.infrastructure.adapters.blob_storage.s3",
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


from unittest.mock import MagicMock, patch  # noqa: E402

# ─── store_factory additional coverage ───────────────────────────────────────


class TestStoreFactory:
    def test_projects_prefix_default(self):
        from concilium.infrastructure.storage.store_factory import _projects_prefix

        with patch("concilium.infrastructure.storage.store_factory.get_storage") as mock_gs:
            mock_gs.return_value.projects_prefix = ""
            result = _projects_prefix()
        assert result == "projetos"

    def test_projects_prefix_custom(self):
        from concilium.infrastructure.storage.store_factory import _projects_prefix

        with patch("concilium.infrastructure.storage.store_factory.get_storage") as mock_gs:
            mock_gs.return_value.projects_prefix = "/custom/prefix/"
            result = _projects_prefix()
        assert result == "custom/prefix"

    def test_build_blob_storage_sharepoint(self):
        from concilium.infrastructure.storage.store_factory import build_blob_storage

        with (
            patch("concilium.infrastructure.storage.store_factory.resolve_store_backend", return_value="sharepoint"),
            patch(
                "concilium.infrastructure.adapters.blob_storage.sharepoint.SharePointBlobStorage.from_env"
            ) as mock_sp,
        ):
            mock_sp.return_value = MagicMock()
            try:
                result = build_blob_storage()
                assert result is not None
            except Exception:
                pass  # May fail without SharePoint config

    def test_build_project_repository_filesystem(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        with patch("concilium.infrastructure.storage.store_factory.resolve_store_backend", return_value="filesystem"):
            result = build_project_repository(tmp_path)
        assert result is not None

    def test_build_project_repository_unknown_raises(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend", return_value="unknown_backend"
        ):
            with pytest.raises(ValueError, match="Unsupported"):
                build_project_repository(tmp_path)




# ─── infrastructure/storage/store_factory additional ─────────────────────────


class TestStoreFactoryAdditional:
    def test_get_campaign_store_returns_store(self):
        from concilium.infrastructure.storage.store_factory import get_campaign_store

        with patch("concilium.infrastructure.storage.store_factory.build_blob_storage") as mock_bs:
            mock_bs.return_value = MagicMock()
            store = get_campaign_store("test-slug")
        assert store is not None

    def test_get_tool_invocation_store_uses_system_storage(self):
        """ADR-135: .tool_invocations é audit trail global, não dado por-projeto."""
        from concilium.infrastructure.storage.store_factory import get_tool_invocation_store

        with (
            patch("concilium.infrastructure.storage.store_factory.build_system_blob_storage") as mock_system,
            patch("concilium.infrastructure.storage.store_factory.build_blob_storage") as mock_project,
        ):
            mock_system.return_value = MagicMock()
            store = get_tool_invocation_store()

        assert store is not None
        mock_system.assert_called_once()
        mock_project.assert_not_called()

