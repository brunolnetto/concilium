"""Tests for Tier-2 cloud storage adapters.

Covers:
  - CloudBlobStorageAdapter  (cloud_blob_storage.py)
  - GoogleDriveBlobStorage   (gdrive_blob_storage.py)
  - S3BlobStorage            (s3_blob_storage.py)
"""

from __future__ import annotations

import asyncio
import builtins
import importlib
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_aioboto3_mock():
    """Return a minimal aioboto3 mock whose Session().client() is an async ctx manager."""
    client_mock = MagicMock()
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    session_mock = MagicMock()
    session_mock.client.return_value = client_mock

    aioboto3_mod = MagicMock()
    aioboto3_mod.Session.return_value = session_mock
    return aioboto3_mod, session_mock, client_mock


def _make_botocore_mock():
    """Return a minimal botocore mock."""
    config_instance = MagicMock()
    config_cls = MagicMock(return_value=config_instance)
    botocore_mod = MagicMock()
    botocore_mod.config.Config = config_cls
    return botocore_mod, config_cls, config_instance


# ---------------------------------------------------------------------------
# 1. CloudBlobStorageAdapter
# ---------------------------------------------------------------------------

class TestCloudBlobStorageAdapter:
    def _cls(self):
        from concilium.infrastructure.adapters.blob_storage.cloud import CloudBlobStorageAdapter
        return CloudBlobStorageAdapter

    def test_init_default_provider(self):
        cls = self._cls()
        adapter = cls()
        assert adapter.provider == "AWS_S3"

    def test_init_custom_provider(self):
        cls = self._cls()
        adapter = cls(provider="GDRIVE")
        assert adapter.provider == "GDRIVE"

    def test_ler_blob_raises_not_implemented(self):
        cls = self._cls()
        adapter = cls()
        with pytest.raises(NotImplementedError):
            adapter.ler_blob("some/path.bin")

    def test_gravar_blob_is_noop(self):
        cls = self._cls()
        adapter = cls()
        result = adapter.gravar_blob("some/path.bin", b"data")
        assert result is None

    def test_listar_blobs_returns_empty_list(self):
        cls = self._cls()
        adapter = cls()
        result = adapter.listar_blobs("prefix/")
        assert result == []

    def test_blob_existe_returns_false(self):
        cls = self._cls()
        adapter = cls()
        result = adapter.blob_existe("any/path")
        assert result is False


# ---------------------------------------------------------------------------
# 2. GoogleDriveBlobStorage
# ---------------------------------------------------------------------------

class TestGoogleDriveBlobStorage:
    """Tests for gdrive_blob_storage.GoogleDriveBlobStorage."""

    def _cls(self):
        from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage
        return GoogleDriveBlobStorage

    def _make(self, **kwargs):
        defaults = {"root_folder_id": "root-id-123"}
        defaults.update(kwargs)
        return self._cls()(**defaults)

    # -- __init__ -----------------------------------------------------------

    def test_init_sets_attributes(self):
        gdrive = self._make(root_folder_id="ROOT", service_account_json="/sa.json", ttl_dias_link=14)
        assert gdrive._root_folder_id == "ROOT"
        assert gdrive._sa_json == "/sa.json"
        assert gdrive._ttl_dias_link == 14
        assert gdrive._svc is None
        assert gdrive._folder_cache == {"": "ROOT"}

    def test_init_defaults(self):
        gdrive = self._make()
        assert gdrive._sa_json is None
        assert gdrive._ttl_dias_link == 7

    # -- from_env -----------------------------------------------------------

    def test_from_env_success(self):
        cls = self._cls()
        gdrive_cfg = MagicMock()
        gdrive_cfg.root_folder_id = "  folder-abc  "
        gdrive_cfg.service_account_json = "  /creds.json  "
        storage_mock = MagicMock()
        storage_mock.gdrive = gdrive_cfg
        with patch(
            "concilium.infrastructure.adapters.blob_storage.gdrive.get_storage",
            return_value=storage_mock,
        ):
            obj = cls.from_env()
        assert obj._root_folder_id == "folder-abc"
        assert obj._sa_json == "/creds.json"

    def test_from_env_empty_root_raises_os_error(self):
        cls = self._cls()
        gdrive_cfg = MagicMock()
        gdrive_cfg.root_folder_id = "   "
        gdrive_cfg.service_account_json = ""
        storage_mock = MagicMock()
        storage_mock.gdrive = gdrive_cfg
        with patch(
            "concilium.infrastructure.adapters.blob_storage.gdrive.get_storage",
            return_value=storage_mock,
        ):
            with pytest.raises(OSError, match="CONCILIUM__GDRIVE_ROOT_FOLDER_ID"):
                cls.from_env()

    # -- _split -------------------------------------------------------------

    def test_split_normal_path(self):
        cls = self._cls()
        folders, name = cls._split("a/b/file.json")
        assert folders == ["a", "b"]
        assert name == "file.json"

    def test_split_single_segment(self):
        cls = self._cls()
        folders, name = cls._split("file.json")
        assert folders == []
        assert name == "file.json"

    def test_split_empty_path_raises(self):
        cls = self._cls()
        # A path that reduces to zero non-empty segments after stripping
        with pytest.raises(ValueError, match="vazio"):
            cls._split("/")
        with pytest.raises(ValueError, match="vazio"):
            cls._split("")

    def test_split_leading_trailing_slashes(self):
        cls = self._cls()
        folders, name = cls._split("/a/b/c.txt/")
        assert folders == ["a", "b"]
        assert name == "c.txt"

    # -- _service -----------------------------------------------------------

    def test_service_raises_import_error_when_google_missing(self):
        gdrive = self._make()
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("google"):
                raise ImportError("No module named 'google'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="google-api-python-client"):
                gdrive._service()

    def test_service_with_service_account_json(self):
        gdrive = self._make(service_account_json="/path/sa.json")
        creds_mock = MagicMock()
        svc_mock = MagicMock()

        sa_mod = MagicMock()
        sa_mod.Credentials.from_service_account_file.return_value = creds_mock

        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.oauth2": MagicMock(),
                "google.oauth2.service_account": sa_mod,
                "googleapiclient": MagicMock(),
                "googleapiclient.discovery": MagicMock(build=MagicMock(return_value=svc_mock)),
            },
        ):
            # Re-enter _service with cleared cache
            gdrive._svc = None
            # patch the two names that _service imports inside the function body
            with patch(
                "concilium.infrastructure.adapters.blob_storage.gdrive.GoogleDriveBlobStorage._service"
            ) as svc_patch:
                svc_patch.return_value = svc_mock
                result = gdrive._service()
        assert result is svc_mock

    def test_service_with_sa_json_real_path(self):
        """Test _service() branch: _sa_json set, Credentials.from_service_account_file called."""
        gdrive = self._make(service_account_json="/fake/sa.json")
        gdrive._svc = None

        creds_mock = MagicMock()
        svc_mock = MagicMock()
        build_mock = MagicMock(return_value=svc_mock)

        sa_module = MagicMock()
        sa_module.Credentials.from_service_account_file.return_value = creds_mock

        # _service() does `from google.oauth2 import service_account`, so Python
        # resolves `service_account` as an attribute on the google.oauth2 module object.
        google_oauth2_mock = MagicMock()
        google_oauth2_mock.service_account = sa_module

        discovery_module = MagicMock()
        discovery_module.build = build_mock

        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.oauth2": google_oauth2_mock,
                "google.oauth2.service_account": sa_module,
                "googleapiclient": MagicMock(),
                "googleapiclient.discovery": discovery_module,
                "google.auth": MagicMock(),
            },
        ):
            svc = gdrive._service()

        assert svc is svc_mock
        assert gdrive._svc is svc_mock
        sa_module.Credentials.from_service_account_file.assert_called_once()

    def test_service_cached_returns_same_object(self):
        gdrive = self._make()
        sentinel = object()
        gdrive._svc = sentinel
        assert gdrive._service() is sentinel

    def test_service_default_auth_branch(self):
        """_service() without _sa_json uses google.auth.default."""
        gdrive = self._make(service_account_json=None)
        gdrive._svc = None

        creds_mock = MagicMock()
        svc_mock = MagicMock()
        build_mock = MagicMock(return_value=svc_mock)
        google_auth_mod = MagicMock()
        google_auth_mod.default.return_value = (creds_mock, "project")
        sa_module = MagicMock()  # needed for the import at top of _service
        discovery_module = MagicMock()
        discovery_module.build = build_mock

        with patch.dict(
            "sys.modules",
            {
                "google": MagicMock(),
                "google.oauth2": MagicMock(),
                "google.oauth2.service_account": sa_module,
                "googleapiclient": MagicMock(),
                "googleapiclient.discovery": discovery_module,
                "google.auth": google_auth_mod,
            },
        ):
            result = gdrive._service()

        assert result is svc_mock
        build_mock.assert_called_once()

    # -- _find_child --------------------------------------------------------

    def test_find_child_found(self):
        gdrive = self._make()
        files_mock = MagicMock()
        files_mock.list.return_value.execute.return_value = {"files": [{"id": "abc", "name": "file.json"}]}
        gdrive._files = MagicMock(return_value=files_mock)
        result = gdrive._find_child("parent-id", "file.json", folder=False)
        assert result == "abc"

    def test_find_child_not_found(self):
        gdrive = self._make()
        files_mock = MagicMock()
        files_mock.list.return_value.execute.return_value = {"files": []}
        gdrive._files = MagicMock(return_value=files_mock)
        result = gdrive._find_child("parent-id", "missing.json", folder=False)
        assert result is None

    # -- ler_blob -----------------------------------------------------------

    def test_ler_blob_file_not_found(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(return_value=None)
        # ler_blob does `from googleapiclient.http import MediaIoBaseDownload` at entry
        http_mock = MagicMock()
        http_mock.MediaIoBaseDownload = MagicMock()
        with patch.dict(
            "sys.modules",
            {"googleapiclient": MagicMock(), "googleapiclient.http": http_mock},
        ):
            with pytest.raises(FileNotFoundError, match="não encontrado"):
                gdrive.ler_blob("folder/missing.bin")

    def test_ler_blob_success(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(return_value="file-id-xyz")

        files_mock = MagicMock()
        files_mock.get_media.return_value = MagicMock()
        gdrive._files = MagicMock(return_value=files_mock)

        downloader_mock = MagicMock()
        downloader_mock.next_chunk.return_value = (None, True)

        import io as _io

        def fake_download_ctor(buf, request):
            buf.write(b"file-content")
            buf.seek(0)
            return downloader_mock

        http_mock = MagicMock()
        http_mock.MediaIoBaseDownload = fake_download_ctor
        http_mock.MediaIoBaseUpload = MagicMock()

        with patch.dict(
            "sys.modules",
            {"googleapiclient": MagicMock(), "googleapiclient.http": http_mock},
        ):
            result = gdrive.ler_blob("folder/file.bin")

        assert result == b"file-content"

    # -- gravar_blob --------------------------------------------------------

    def test_gravar_blob_existing_file_update(self):
        gdrive = self._make()
        folder_id = "folder-id"
        file_id = "existing-file-id"

        gdrive._resolve_folder = MagicMock(return_value=folder_id)
        gdrive._find_child = MagicMock(return_value=file_id)
        files_mock = MagicMock()
        gdrive._files = MagicMock(return_value=files_mock)

        media_mock = MagicMock()
        with patch.dict(
            "sys.modules",
            {"googleapiclient.http": MagicMock(MediaIoBaseUpload=MagicMock(return_value=media_mock))},
        ):
            gdrive.gravar_blob("dir/file.json", b"data")

        files_mock.update.assert_called_once()
        files_mock.update.return_value.execute.assert_called_once()

    def test_gravar_blob_new_file_create(self):
        gdrive = self._make()
        folder_id = "folder-id"

        gdrive._resolve_folder = MagicMock(return_value=folder_id)
        gdrive._find_child = MagicMock(return_value=None)
        files_mock = MagicMock()
        gdrive._files = MagicMock(return_value=files_mock)

        media_mock = MagicMock()
        with patch.dict(
            "sys.modules",
            {"googleapiclient.http": MagicMock(MediaIoBaseUpload=MagicMock(return_value=media_mock))},
        ):
            gdrive.gravar_blob("dir/new_file.json", b"new-data")

        files_mock.create.assert_called_once()
        files_mock.create.return_value.execute.assert_called_once()

    # -- listar_blobs -------------------------------------------------------

    def test_listar_blobs_folder_not_found(self):
        gdrive = self._make()
        gdrive._resolve_folder = MagicMock(return_value=None)
        result = gdrive.listar_blobs("missing/prefix")
        assert result == []

    def test_listar_blobs_returns_walk_results(self):
        gdrive = self._make()
        gdrive._resolve_folder = MagicMock(return_value="folder-id")
        expected = ["prefix/a.json", "prefix/sub/b.json"]

        def fake_walk(folder_id, prefix, out):
            out.extend(expected)

        gdrive._walk = fake_walk
        result = gdrive.listar_blobs("prefix")
        assert result == expected

    # -- _walk --------------------------------------------------------------

    def test_walk_with_folder_and_file_entries(self):
        gdrive = self._make()
        files_mock = MagicMock()
        files_mock.list.return_value.execute.side_effect = [
            # first call: contains a sub-folder and a file
            {
                "files": [
                    {"id": "sub-id", "name": "subdir", "mimeType": "application/vnd.google-apps.folder"},
                    {"id": "f1-id", "name": "file1.json", "mimeType": "application/json"},
                ]
            },
            # second call (recursive into subdir)
            {
                "files": [
                    {"id": "f2-id", "name": "file2.json", "mimeType": "application/json"},
                ]
            },
        ]
        gdrive._files = MagicMock(return_value=files_mock)
        out = []
        gdrive._walk("parent-id", "root", out)
        assert "root/file1.json" in out
        assert "root/subdir/file2.json" in out

    # -- blob_existe --------------------------------------------------------

    def test_blob_existe_true_when_file_id_returns_id(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(return_value="some-id")
        assert gdrive.blob_existe("dir/file.json") is True

    def test_blob_existe_false_when_file_id_raises(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(side_effect=Exception("network error"))
        assert gdrive.blob_existe("dir/file.json") is False

    def test_blob_existe_false_when_file_id_returns_none(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(return_value=None)
        assert gdrive.blob_existe("dir/file.json") is False

    # -- gerar_url_temporaria -----------------------------------------------

    def test_gerar_url_temporaria_file_not_found_returns_none(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(return_value=None)
        result = gdrive.gerar_url_temporaria("missing/file.bin")
        assert result is None

    def test_gerar_url_temporaria_returns_web_content_link(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(return_value="fid-123")

        perms_mock = MagicMock()
        perms_mock.create.return_value.execute.return_value = {}
        gdrive._permissions = MagicMock(return_value=perms_mock)

        files_mock = MagicMock()
        files_mock.get.return_value.execute.return_value = {
            "webContentLink": "https://drive.google.com/uc?id=fid-123",
            "webViewLink": "https://drive.google.com/file/d/fid-123/view",
        }
        gdrive._files = MagicMock(return_value=files_mock)

        result = gdrive.gerar_url_temporaria("some/file.bin", ttl_segundos=3600)
        assert result == "https://drive.google.com/uc?id=fid-123"

    def test_gerar_url_temporaria_exception_returns_none(self):
        gdrive = self._make()
        gdrive._file_id = MagicMock(side_effect=RuntimeError("unexpected"))
        result = gdrive.gerar_url_temporaria("some/file.bin")
        assert result is None


# ---------------------------------------------------------------------------
# 3. S3BlobStorage
# ---------------------------------------------------------------------------

def _make_s3_instance(**override):
    """Instantiate S3BlobStorage with aioboto3 and botocore mocked."""
    aioboto3_mock, _, _ = _make_aioboto3_mock()
    botocore_mock, _, _ = _make_botocore_mock()

    with patch.dict(
        "sys.modules",
        {
            "aioboto3": aioboto3_mock,
            "botocore": botocore_mock,
            "botocore.config": botocore_mock.config,
        },
    ):
        from concilium.infrastructure.adapters.blob_storage import s3 as s3_blob_storage
        importlib.reload(s3_blob_storage)
        from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

        params = {"bucket": "test-bucket"}
        params.update(override)
        instance = S3BlobStorage(**params)
    return instance, aioboto3_mock, botocore_mock


class TestS3BlobStorage:
    """Tests for s3_blob_storage.S3BlobStorage."""

    # -- _build_session -----------------------------------------------------

    def test_build_session_raises_import_error_when_aioboto3_missing(self):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "aioboto3":
                raise ImportError("No module named 'aioboto3'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            # force fresh module
            if "concilium.infrastructure.adapters.blob_storage.s3" in sys.modules:
                del sys.modules["concilium.infrastructure.adapters.blob_storage.s3"]
            from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

            with pytest.raises(ImportError, match="aioboto3"):
                S3BlobStorage._build_session()

    # -- _build_client_kwargs -----------------------------------------------

    def test_build_client_kwargs_without_addressing_style(self):
        botocore_config_mock = MagicMock()
        botocore_mod = MagicMock()
        botocore_mod.config.Config = botocore_config_mock

        with patch.dict("sys.modules", {"botocore": botocore_mod, "botocore.config": botocore_mod.config}):
            from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

            result = S3BlobStorage._build_client_kwargs(
                region="us-east-1",
                endpoint_url=None,
                addressing_style=None,
                aws_access_key_id="AK",
                aws_secret_access_key="SK",
                aws_session_token=None,
            )

        assert result["region_name"] == "us-east-1"
        assert result["config"] is None
        botocore_config_mock.assert_not_called()

    def test_build_client_kwargs_with_addressing_style(self):
        config_instance = MagicMock()
        botocore_config_mock = MagicMock(return_value=config_instance)
        botocore_mod = MagicMock()
        botocore_mod.config.Config = botocore_config_mock

        with patch.dict("sys.modules", {"botocore": botocore_mod, "botocore.config": botocore_mod.config}):
            from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

            result = S3BlobStorage._build_client_kwargs(
                region=None,
                endpoint_url="http://localhost:9000",
                addressing_style="path",
                aws_access_key_id=None,
                aws_secret_access_key=None,
                aws_session_token=None,
            )

        assert result["config"] is config_instance
        botocore_config_mock.assert_called_once_with(s3={"addressing_style": "path"})

    # -- _full_key ----------------------------------------------------------

    def test_full_key_no_prefix(self):
        instance, _, _ = _make_s3_instance()
        assert instance._full_key("a/b/c.json") == "a/b/c.json"

    def test_full_key_with_prefix(self):
        instance, _, _ = _make_s3_instance(root_prefix="my-prefix")
        assert instance._full_key("a/b/c.json") == "my-prefix/a/b/c.json"

    def test_full_key_empty_safe_with_prefix(self):
        instance, _, _ = _make_s3_instance(root_prefix="my-prefix")
        assert instance._full_key("") == "my-prefix"

    def test_full_key_empty_safe_no_prefix(self):
        instance, _, _ = _make_s3_instance()
        assert instance._full_key("") == ""

    # -- _to_logical_key ----------------------------------------------------

    def test_to_logical_key_no_prefix(self):
        instance, _, _ = _make_s3_instance()
        assert instance._to_logical_key("a/b.json") == "a/b.json"

    def test_to_logical_key_strips_prefix(self):
        instance, _, _ = _make_s3_instance(root_prefix="pfx")
        assert instance._to_logical_key("pfx/sub/file.json") == "sub/file.json"

    def test_to_logical_key_key_equals_prefix(self):
        instance, _, _ = _make_s3_instance(root_prefix="pfx")
        assert instance._to_logical_key("pfx") == ""

    # -- aprovar_versao -----------------------------------------------------

    def test_aprovar_versao_returns_none(self):
        instance, _, _ = _make_s3_instance()
        result = instance.aprovar_versao("any/path")
        assert result is None

    # -- from_env -----------------------------------------------------------

    def test_from_env_success(self):
        aioboto3_mock, _, _ = _make_aioboto3_mock()
        botocore_mock, _, _ = _make_botocore_mock()

        s3_cfg = MagicMock()
        s3_cfg.bucket = "  my-bucket  "
        s3_cfg.region = "us-west-2"
        s3_cfg.root_prefix = ""
        s3_cfg.endpoint_url = ""
        s3_cfg.addressing_style = ""
        s3_cfg.access_key_id = ""
        s3_cfg.secret_access_key = ""
        s3_cfg.session_token = ""
        s3_cfg.server_side_encryption = ""

        storage_mock = MagicMock()
        storage_mock.s3 = s3_cfg

        with patch.dict(
            "sys.modules",
            {"aioboto3": aioboto3_mock, "botocore": botocore_mock, "botocore.config": botocore_mock.config},
        ):
            from concilium.infrastructure.adapters.blob_storage import s3 as s3_blob_storage
            importlib.reload(s3_blob_storage)
            from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

            with patch(
                "concilium.infrastructure.adapters.blob_storage.s3.get_storage",
                return_value=storage_mock,
            ):
                obj = S3BlobStorage.from_env()

        assert obj._bucket == "my-bucket"

    def test_from_env_empty_bucket_raises_os_error(self):
        aioboto3_mock, _, _ = _make_aioboto3_mock()
        botocore_mock, _, _ = _make_botocore_mock()

        s3_cfg = MagicMock()
        s3_cfg.bucket = "   "

        storage_mock = MagicMock()
        storage_mock.s3 = s3_cfg

        with patch.dict(
            "sys.modules",
            {"aioboto3": aioboto3_mock, "botocore": botocore_mock, "botocore.config": botocore_mock.config},
        ):
            from concilium.infrastructure.adapters.blob_storage import s3 as s3_blob_storage
            importlib.reload(s3_blob_storage)
            from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

            with patch(
                "concilium.infrastructure.adapters.blob_storage.s3.get_storage",
                return_value=storage_mock,
            ):
                with pytest.raises(OSError, match="CONCILIUM__S3_BUCKET"):
                    S3BlobStorage.from_env()

    # -- ler_blob -----------------------------------------------------------

    def test_ler_blob_success(self):
        instance, _, _ = _make_s3_instance()
        instance._get_object = MagicMock()
        instance._run = MagicMock(return_value=b"blob-content")
        result = instance.ler_blob("dir/file.bin")
        assert result == b"blob-content"

    def test_ler_blob_no_such_key_raises_file_not_found(self):
        instance, _, _ = _make_s3_instance()
        exc = Exception("NoSuchKey")
        exc.response = {"Error": {"Code": "NoSuchKey"}}
        instance._get_object = MagicMock()
        instance._run = MagicMock(side_effect=exc)
        with pytest.raises(FileNotFoundError, match="não encontrado"):
            instance.ler_blob("dir/missing.bin")

    def test_ler_blob_other_exception_reraises(self):
        instance, _, _ = _make_s3_instance()
        exc = RuntimeError("connection refused")
        instance._get_object = MagicMock()
        instance._run = MagicMock(side_effect=exc)
        with pytest.raises(RuntimeError, match="connection refused"):
            instance.ler_blob("dir/file.bin")

    # -- gravar_blob --------------------------------------------------------

    def test_gravar_blob_calls_run(self):
        instance, _, _ = _make_s3_instance()
        instance._put_object = MagicMock()
        instance._run = MagicMock(return_value=None)
        instance.gravar_blob("dir/file.json", b"payload")
        instance._run.assert_called_once()

    # -- listar_blobs -------------------------------------------------------

    def test_listar_blobs_returns_list(self):
        instance, _, _ = _make_s3_instance()
        expected = ["dir/a.json", "dir/b.json"]
        instance._list_objects = MagicMock()
        instance._run = MagicMock(return_value=expected)
        result = instance.listar_blobs("dir/")
        assert result == expected

    # -- blob_existe --------------------------------------------------------

    def test_blob_existe_true_on_success(self):
        instance, _, _ = _make_s3_instance()
        instance._head_object = MagicMock()
        instance._run = MagicMock(return_value=None)
        assert instance.blob_existe("dir/file.json") is True

    def test_blob_existe_false_on_404(self):
        instance, _, _ = _make_s3_instance()
        exc = Exception("Not found")
        exc.response = {"Error": {"Code": "404"}}
        instance._head_object = MagicMock()
        instance._run = MagicMock(side_effect=exc)
        assert instance.blob_existe("dir/missing.json") is False

    def test_blob_existe_false_on_no_such_key(self):
        instance, _, _ = _make_s3_instance()
        exc = Exception("NoSuchKey")
        exc.response = {"Error": {"Code": "NoSuchKey"}}
        instance._head_object = MagicMock()
        instance._run = MagicMock(side_effect=exc)
        assert instance.blob_existe("dir/missing.json") is False

    def test_blob_existe_reraises_other_exception(self):
        instance, _, _ = _make_s3_instance()
        exc = RuntimeError("server error")
        exc.response = {"Error": {"Code": "500"}}
        instance._head_object = MagicMock()
        instance._run = MagicMock(side_effect=exc)
        with pytest.raises(RuntimeError):
            instance.blob_existe("dir/file.json")

    # -- gerar_url_temporaria -----------------------------------------------

    def test_gerar_url_temporaria_success(self):
        instance, _, _ = _make_s3_instance()
        url = "https://s3.amazonaws.com/test-bucket/dir/file.bin?X-Amz-Signature=..."
        instance._presign = MagicMock()
        instance._run = MagicMock(return_value=url)
        result = instance.gerar_url_temporaria("dir/file.bin", ttl_segundos=600)
        assert result == url

    def test_gerar_url_temporaria_exception_returns_none(self):
        instance, _, _ = _make_s3_instance()
        instance._presign = MagicMock()
        instance._run = MagicMock(side_effect=Exception("presign failed"))
        result = instance.gerar_url_temporaria("dir/file.bin")
        assert result is None

    # -- _run ---------------------------------------------------------------
    # Usa MagicMock() como argumento em vez de async def para não criar
    # corrotinas reais que não seriam aguardadas (RuntimeWarning).

    def test_run_without_running_loop_uses_asyncio_run(self):
        instance, _, _ = _make_s3_instance()
        fake_coro = MagicMock()

        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            with patch("asyncio.run", return_value=42) as asyncio_run_mock:
                result = instance._run(fake_coro)

        asyncio_run_mock.assert_called_once_with(fake_coro)
        assert result == 42

    def test_run_with_running_loop_uses_thread_executor(self):
        instance, _, _ = _make_s3_instance()
        fake_coro = MagicMock()

        loop_mock = MagicMock()
        future_mock = MagicMock()
        future_mock.result.return_value = 99
        executor_mock = MagicMock()
        executor_mock.__enter__ = MagicMock(return_value=executor_mock)
        executor_mock.__exit__ = MagicMock(return_value=False)
        executor_mock.submit.return_value = future_mock

        with patch("asyncio.get_running_loop", return_value=loop_mock):
            with patch(
                "concilium.infrastructure.adapters.blob_storage.s3.ThreadPoolExecutor",
                return_value=executor_mock,
            ):
                with patch("asyncio.run", return_value=99):
                    result = instance._run(fake_coro)

        assert result == 99
        executor_mock.submit.assert_called_once()
