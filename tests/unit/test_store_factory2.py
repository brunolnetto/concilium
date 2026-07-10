"""Tests for infrastructure/storage/store_factory.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestResolveStoreBackend:
    # resolve_store_backend() re-imports get_storage locally — patch at source module
    _patch = "concilium.infrastructure.settings.get_storage"

    def test_filesystem_aliases(self):
        from concilium.infrastructure.storage.store_factory import resolve_store_backend

        for alias in ("filesystem", "local", "local_json", "local-json"):
            storage_mock = MagicMock()
            storage_mock.backend = alias
            with patch(self._patch, return_value=storage_mock):
                assert resolve_store_backend() == "filesystem"

    def test_sharepoint_alias(self):
        from concilium.infrastructure.storage.store_factory import resolve_store_backend

        storage_mock = MagicMock()
        storage_mock.backend = "sharepoint"
        with patch(self._patch, return_value=storage_mock):
            assert resolve_store_backend() == "sharepoint"

    def test_azure_alias(self):
        from concilium.infrastructure.storage.store_factory import resolve_store_backend

        storage_mock = MagicMock()
        storage_mock.backend = "azure_blob"
        with patch(self._patch, return_value=storage_mock):
            assert resolve_store_backend() == "azure"

    def test_empty_backend_defaults_to_filesystem(self):
        from concilium.infrastructure.storage.store_factory import resolve_store_backend

        storage_mock = MagicMock()
        storage_mock.backend = ""
        with patch(self._patch, return_value=storage_mock):
            assert resolve_store_backend() == "filesystem"


class TestBuildBlobStorage:
    def test_filesystem_backend(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_blob_storage

        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="filesystem",
        ):
            result = build_blob_storage(root_override=tmp_path)
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        assert isinstance(result, LocalBlobStorage)

    def test_unknown_backend_raises(self):
        from concilium.infrastructure.storage.store_factory import build_blob_storage

        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="unknown-backend",
        ):
            with pytest.raises(ValueError, match="não suportado"):
                build_blob_storage()


class TestBuildProjectRepository:
    def test_filesystem_backend(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
        from concilium.infrastructure.storage.store_factory import build_project_repository

        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="filesystem",
        ):
            repo = build_project_repository(tmp_path)
        assert isinstance(repo, FileProjectRepository)

    def test_unknown_backend_raises(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="unsupported",
        ):
            with pytest.raises(ValueError, match="Unsupported"):
                build_project_repository(tmp_path)

    def test_sharepoint_backend(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        storage_mock = MagicMock()
        storage_mock.sharepoint.cache_dir = ""
        repo_mock = MagicMock()
        with (
            patch("concilium.infrastructure.storage.store_factory.resolve_store_backend", return_value="sharepoint"),
            patch(
                "concilium.infrastructure.storage.store_factory._build_sharepoint_repository", return_value=repo_mock
            ),
        ):
            result = build_project_repository(tmp_path)
        assert result is repo_mock

    def test_s3_backend(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        repo_mock = MagicMock()
        with (
            patch("concilium.infrastructure.storage.store_factory.resolve_store_backend", return_value="s3"),
            patch("concilium.infrastructure.storage.store_factory._build_s3_repository", return_value=repo_mock),
        ):
            result = build_project_repository(tmp_path)
        assert result is repo_mock

    def test_azure_backend(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        repo_mock = MagicMock()
        with (
            patch("concilium.infrastructure.storage.store_factory.resolve_store_backend", return_value="azure"),
            patch("concilium.infrastructure.storage.store_factory._build_azure_repository", return_value=repo_mock),
        ):
            result = build_project_repository(tmp_path)
        assert result is repo_mock

    def test_gdrive_backend(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        repo_mock = MagicMock()
        with (
            patch("concilium.infrastructure.storage.store_factory.resolve_store_backend", return_value="gdrive"),
            patch("concilium.infrastructure.storage.store_factory._build_gdrive_repository", return_value=repo_mock),
        ):
            result = build_project_repository(tmp_path)
        assert result is repo_mock


class TestGetCampaignStore:
    def test_returns_campaign_store(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import get_campaign_store

        local_mock = MagicMock()
        with patch("concilium.infrastructure.storage.store_factory.build_blob_storage", return_value=local_mock):
            store = get_campaign_store("my-project")
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore

        assert isinstance(store, CampaignRunStore)


class TestProjectsPrefix:
    def test_projects_prefix_default(self):
        from concilium.infrastructure.storage.store_factory import _projects_prefix

        storage_mock = MagicMock()
        storage_mock.projects_prefix = ""
        with patch("concilium.infrastructure.storage.store_factory.get_storage", return_value=storage_mock):
            result = _projects_prefix()
        assert result == "projetos"

    def test_projects_prefix_custom(self):
        from concilium.infrastructure.storage.store_factory import _projects_prefix

        storage_mock = MagicMock()
        storage_mock.projects_prefix = "/my-prefix/"
        with patch("concilium.infrastructure.storage.store_factory.get_storage", return_value=storage_mock):
            result = _projects_prefix()
        assert result == "my-prefix"


class TestBuildAzureRepository:
    def test_wires_azure_storage_and_prefix(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        calls: dict = {}

        class DummyAzureBlobStorage:
            @classmethod
            def from_env(cls):
                calls["from_env"] = True
                return "azure-storage"

        class DummyStorageProjectRepository:
            def __init__(self, storage, projects_prefix):
                calls["storage"] = storage
                calls["projects_prefix"] = projects_prefix

        monkeypatch.setenv("CONCILIUM__STORE_PROJECTS_PREFIX", "azure-projects")
        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.azure",
            types.SimpleNamespace(AzureBlobStorage=DummyAzureBlobStorage),
        )
        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.storage.storage_project_repository",
            types.SimpleNamespace(StorageProjectRepository=DummyStorageProjectRepository),
        )

        repo = store_factory._build_azure_repository()
        assert isinstance(repo, DummyStorageProjectRepository)
        assert calls["from_env"] is True
        assert calls["storage"] == "azure-storage"
        assert calls["projects_prefix"] == "azure-projects"


class TestBuildGdriveRepository:
    def test_wires_gdrive_storage_and_prefix(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        calls: dict = {}

        class DummyGoogleDriveBlobStorage:
            @classmethod
            def from_env(cls):
                calls["from_env"] = True
                return "gdrive-storage"

        class DummyStorageProjectRepository:
            def __init__(self, storage, projects_prefix):
                calls["storage"] = storage
                calls["projects_prefix"] = projects_prefix

        monkeypatch.setenv("CONCILIUM__STORE_PROJECTS_PREFIX", "gdrive-projects")
        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.gdrive",
            types.SimpleNamespace(GoogleDriveBlobStorage=DummyGoogleDriveBlobStorage),
        )
        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.storage.storage_project_repository",
            types.SimpleNamespace(StorageProjectRepository=DummyStorageProjectRepository),
        )

        repo = store_factory._build_gdrive_repository()
        assert isinstance(repo, DummyStorageProjectRepository)
        assert calls["from_env"] is True
        assert calls["storage"] == "gdrive-storage"
        assert calls["projects_prefix"] == "gdrive-projects"


class TestBuildBlobStorageCloudBackends:
    """Covers build_blob_storage() branches for sharepoint, s3, azure, gdrive."""

    def test_sharepoint_backend_calls_from_env(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()

        class DummySP:
            @classmethod
            def from_env(cls):
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.sharepoint",
            types.SimpleNamespace(SharePointBlobStorage=DummySP),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="sharepoint",
        ):
            result = store_factory.build_blob_storage()
        assert result is sentinel

    def test_s3_backend_calls_from_env(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()

        class DummyS3:
            @classmethod
            def from_env(cls):
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.s3",
            types.SimpleNamespace(S3BlobStorage=DummyS3),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="s3",
        ):
            result = store_factory.build_blob_storage()
        assert result is sentinel

    def test_azure_backend_calls_from_env(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()

        class DummyAzure:
            @classmethod
            def from_env(cls):
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.azure",
            types.SimpleNamespace(AzureBlobStorage=DummyAzure),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="azure",
        ):
            result = store_factory.build_blob_storage()
        assert result is sentinel

    def test_gdrive_backend_calls_from_env(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()

        class DummyGDrive:
            @classmethod
            def from_env(cls):
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.gdrive",
            types.SimpleNamespace(GoogleDriveBlobStorage=DummyGDrive),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="gdrive",
        ):
            result = store_factory.build_blob_storage()
        assert result is sentinel


class TestBuildSystemBlobStorageCloudBackends:
    """Covers build_system_blob_storage() branches for sharepoint, s3, azure, gdrive.

    Cada backend cloud deve delegar para o respectivo adapter com
    `from_env(system=True)` — não para o storage de projetos — e filesystem
    deve continuar delegando para build_blob_storage() com root_override.
    """

    def test_sharepoint_backend_calls_from_env_with_system_true(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()
        calls = {}

        class DummySP:
            @classmethod
            def from_env(cls, *, system=False):
                calls["system"] = system
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.sharepoint",
            types.SimpleNamespace(SharePointBlobStorage=DummySP),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="sharepoint",
        ):
            result = store_factory.build_system_blob_storage()
        assert result is sentinel
        assert calls["system"] is True

    def test_s3_backend_calls_from_env_with_system_true(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()
        calls = {}

        class DummyS3:
            @classmethod
            def from_env(cls, *, system=False):
                calls["system"] = system
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.s3",
            types.SimpleNamespace(S3BlobStorage=DummyS3),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="s3",
        ):
            result = store_factory.build_system_blob_storage()
        assert result is sentinel
        assert calls["system"] is True

    def test_azure_backend_calls_from_env_with_system_true(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()
        calls = {}

        class DummyAzure:
            @classmethod
            def from_env(cls, *, system=False):
                calls["system"] = system
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.azure",
            types.SimpleNamespace(AzureBlobStorage=DummyAzure),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="azure",
        ):
            result = store_factory.build_system_blob_storage()
        assert result is sentinel
        assert calls["system"] is True

    def test_gdrive_backend_calls_from_env_with_system_true(self, monkeypatch):
        import sys
        import types

        from concilium.infrastructure.storage import store_factory

        sentinel = object()
        calls = {}

        class DummyGDrive:
            @classmethod
            def from_env(cls, *, system=False):
                calls["system"] = system
                return sentinel

        monkeypatch.setitem(
            sys.modules,
            "concilium.infrastructure.adapters.blob_storage.gdrive",
            types.SimpleNamespace(GoogleDriveBlobStorage=DummyGDrive),
        )
        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="gdrive",
        ):
            result = store_factory.build_system_blob_storage()
        assert result is sentinel
        assert calls["system"] is True

    def test_filesystem_backend_delegates_to_build_blob_storage(self, tmp_path):
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
        from concilium.infrastructure.storage import store_factory

        with patch(
            "concilium.infrastructure.storage.store_factory.resolve_store_backend",
            return_value="filesystem",
        ):
            result = store_factory.build_system_blob_storage(root_override=tmp_path)
        assert isinstance(result, LocalBlobStorage)
        assert result.root_dir == tmp_path
