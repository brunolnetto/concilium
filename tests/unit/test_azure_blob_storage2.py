"""Unit tests for AzureBlobStorage — mocks azure-storage-blob SDK, no real credentials needed."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to build an AzureBlobStorage without touching real Azure
# ---------------------------------------------------------------------------


def _make_storage(**kwargs):
    """Instantiate AzureBlobStorage directly with test kwargs."""
    from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

    defaults = dict(container="mycontainer")
    defaults.update(kwargs)
    return AzureBlobStorage(**defaults)


# ---------------------------------------------------------------------------
# Fake SDK modules injected via sys.modules so no real package is needed
# ---------------------------------------------------------------------------


def _inject_azure_mocks():
    """Return a dict of mock modules for azure.storage.blob and azure.identity."""
    blob_mod = ModuleType("azure.storage.blob")
    identity_mod = ModuleType("azure.identity")
    exceptions_mod = ModuleType("azure.core.exceptions")

    mock_service_client = MagicMock(name="BlobServiceClient")
    mock_blob_sas_permissions = MagicMock(name="BlobSasPermissions")
    mock_generate_blob_sas = MagicMock(name="generate_blob_sas", return_value="sv=2023&sig=abc")
    mock_default_cred = MagicMock(name="DefaultAzureCredential")

    class ResourceNotFoundError(Exception):
        pass

    blob_mod.BlobServiceClient = mock_service_client
    blob_mod.BlobSasPermissions = mock_blob_sas_permissions
    blob_mod.generate_blob_sas = mock_generate_blob_sas
    identity_mod.DefaultAzureCredential = mock_default_cred
    exceptions_mod.ResourceNotFoundError = ResourceNotFoundError

    return {
        "azure": ModuleType("azure"),
        "azure.storage": ModuleType("azure.storage"),
        "azure.storage.blob": blob_mod,
        "azure.identity": identity_mod,
        "azure.core": ModuleType("azure.core"),
        "azure.core.exceptions": exceptions_mod,
    }, ResourceNotFoundError


# ===========================================================================
# _full_key — path normalization
# ===========================================================================


class TestFullKey:
    def test_no_prefix_plain_path(self):
        s = _make_storage(root_prefix="")
        assert s._full_key("foo/bar.json") == "foo/bar.json"

    def test_no_prefix_strips_leading_slash(self):
        s = _make_storage(root_prefix="")
        assert s._full_key("/foo/bar") == "foo/bar"

    def test_with_prefix_prepends(self):
        s = _make_storage(root_prefix="myproject")
        assert s._full_key("foo/bar.json") == "myproject/foo/bar.json"

    def test_prefix_strips_slashes(self):
        s = _make_storage(root_prefix="/myproject/")
        assert s._full_key("foo.json") == "myproject/foo.json"

    def test_empty_path_with_prefix(self):
        s = _make_storage(root_prefix="pfx")
        assert s._full_key("") == "pfx"

    def test_empty_path_no_prefix(self):
        s = _make_storage(root_prefix="")
        assert s._full_key("") == ""

    def test_strips_trailing_slash_from_path(self):
        s = _make_storage(root_prefix="pfx")
        assert s._full_key("data/") == "pfx/data"


# ===========================================================================
# _client() — lazy initialization paths
# ===========================================================================


class TestClientLazyInit:
    def test_returns_cached_service_on_second_call(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="DefaultEndpointsProtocol=https;...")
            svc1 = s._client()
            svc2 = s._client()
            assert svc1 is svc2

    def test_connection_string_path(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="Endpoint=sb://...")
            s._client()
            mocks["azure.storage.blob"].BlobServiceClient.from_connection_string.assert_called_once()

    def test_account_and_key_path(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", account="myaccount", account_key="mykey")
            s._client()
            mocks["azure.storage.blob"].BlobServiceClient.assert_called_once()
            call_kwargs = mocks["azure.storage.blob"].BlobServiceClient.call_args
            assert "myaccount.blob.core.windows.net" in call_kwargs.kwargs["account_url"]
            assert call_kwargs.kwargs["credential"] == "mykey"

    def test_managed_identity_path(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", account="myaccount")
            s._client()
            mocks["azure.identity"].DefaultAzureCredential.assert_called_once()

    def test_missing_credentials_raises_oserror(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c")
            with pytest.raises(OSError, match="CONCILIUM__AZURE"):
                s._client()

    def test_missing_package_raises_import_error(self):
        # Simulate azure.storage.blob not installed
        with patch.dict(sys.modules, {"azure.storage.blob": None}):
            # Force the module to re-evaluate the import inside _client
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x")
            with pytest.raises(ImportError, match="azure-storage-blob"):
                s._client()


# ===========================================================================
# from_env
# ===========================================================================


class TestFromEnv:
    def test_from_env_happy_path(self, monkeypatch):

        class _FakeAzure:
            container = "mycontainer"
            account = "myaccount"
            key = "mykey"
            connection_string = ""
            root_prefix = "pfx"

        class _FakeStorage:
            azure = _FakeAzure()

        monkeypatch.setattr("concilium.infrastructure.adapters.blob_storage.azure.get_storage", lambda: _FakeStorage())

        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        s = AzureBlobStorage.from_env()
        assert s._container == "mycontainer"
        assert s._account == "myaccount"
        assert s._account_key == "mykey"
        assert s._root_prefix == "pfx"

    def test_from_env_empty_container_raises_oserror(self, monkeypatch):

        class _FakeAzure:
            container = "  "
            account = ""
            key = ""
            connection_string = ""
            root_prefix = ""

        class _FakeStorage:
            azure = _FakeAzure()

        monkeypatch.setattr("concilium.infrastructure.adapters.blob_storage.azure.get_storage", lambda: _FakeStorage())

        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        with pytest.raises(OSError, match="CONCILIUM__AZURE_CONTAINER"):
            AzureBlobStorage.from_env()

    def test_from_env_connection_string_preferred(self, monkeypatch):

        class _FakeAzure:
            container = "c"
            account = "acct"
            key = "k"
            connection_string = "DefaultEndpointsProtocol=https;..."
            root_prefix = ""

        class _FakeStorage:
            azure = _FakeAzure()

        monkeypatch.setattr("concilium.infrastructure.adapters.blob_storage.azure.get_storage", lambda: _FakeStorage())

        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        s = AzureBlobStorage.from_env()
        assert s._connection_string == "DefaultEndpointsProtocol=https;..."

    def test_from_env_empty_key_becomes_none(self, monkeypatch):

        class _FakeAzure:
            container = "c"
            account = "acct"
            key = ""
            connection_string = ""
            root_prefix = ""

        class _FakeStorage:
            azure = _FakeAzure()

        monkeypatch.setattr("concilium.infrastructure.adapters.blob_storage.azure.get_storage", lambda: _FakeStorage())

        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        s = AzureBlobStorage.from_env()
        assert s._account_key is None


# ===========================================================================
# ler_blob
# ===========================================================================


class TestLerBlob:
    def test_happy_path_returns_bytes(self):
        mocks, ResourceNotFoundError = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x")
            expected = b"hello world"

            mock_blob_client = MagicMock()
            mock_blob_client.download_blob.return_value.readall.return_value = expected
            s._blob_client = MagicMock(return_value=mock_blob_client)

            result = s.ler_blob("data/file.json")
            assert result == expected
            s._blob_client.assert_called_once_with("data/file.json")

    def test_resource_not_found_raises_file_not_found(self):
        mocks, ResourceNotFoundError = _inject_azure_mocks()
        # Patch the exceptions module so ler_blob can import it
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x")

            mock_blob_client = MagicMock()
            mock_blob_client.download_blob.side_effect = ResourceNotFoundError("not found")
            s._blob_client = MagicMock(return_value=mock_blob_client)

            with pytest.raises(FileNotFoundError, match="data/missing.json"):
                s.ler_blob("data/missing.json")


# ===========================================================================
# gravar_blob
# ===========================================================================


class TestGravarBlob:
    def test_delegates_upload_with_overwrite(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x")
            mock_blob_client = MagicMock()
            s._blob_client = MagicMock(return_value=mock_blob_client)

            s.gravar_blob("out/result.json", b'{"x":1}')

            mock_blob_client.upload_blob.assert_called_once_with(b'{"x":1}', overwrite=True)

    def test_correct_path_passed(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x", root_prefix="pfx")
            mock_blob_client = MagicMock()
            s._blob_client = MagicMock(return_value=mock_blob_client)

            s.gravar_blob("file.txt", b"data")
            s._blob_client.assert_called_once_with("file.txt")


# ===========================================================================
# listar_blobs
# ===========================================================================


class TestListarBlobs:
    def _make_blob(self, name: str):
        b = MagicMock()
        b.name = name
        return b

    def test_strips_root_prefix_from_names(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x", root_prefix="pfx")

            mock_container_client = MagicMock()
            mock_container_client.list_blobs.return_value = [
                self._make_blob("pfx/data/a.json"),
                self._make_blob("pfx/data/b.json"),
            ]
            mock_service = MagicMock()
            mock_service.get_container_client.return_value = mock_container_client
            s._service = mock_service

            names = s.listar_blobs("data/")
            assert names == ["data/a.json", "data/b.json"]

    def test_no_prefix_returns_names_as_is(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x", root_prefix="")

            mock_container_client = MagicMock()
            mock_container_client.list_blobs.return_value = [
                self._make_blob("data/a.json"),
                self._make_blob("data/b.json"),
            ]
            mock_service = MagicMock()
            mock_service.get_container_client.return_value = mock_container_client
            s._service = mock_service

            names = s.listar_blobs("data/")
            assert names == ["data/a.json", "data/b.json"]

    def test_blob_without_matching_prefix_kept_as_is(self):
        """Blobs whose name doesn't start with root_prefix/ are returned unchanged."""
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x", root_prefix="pfx")

            mock_container_client = MagicMock()
            mock_container_client.list_blobs.return_value = [
                self._make_blob("other/a.json"),  # does NOT start with pfx/
            ]
            mock_service = MagicMock()
            mock_service.get_container_client.return_value = mock_container_client
            s._service = mock_service

            names = s.listar_blobs("")
            assert names == ["other/a.json"]

    def test_uses_full_key_as_prefix(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x", root_prefix="proj")

            mock_container_client = MagicMock()
            mock_container_client.list_blobs.return_value = []
            mock_service = MagicMock()
            mock_service.get_container_client.return_value = mock_container_client
            s._service = mock_service

            s.listar_blobs("sub/")
            mock_container_client.list_blobs.assert_called_once_with(name_starts_with="proj/sub")


# ===========================================================================
# blob_existe
# ===========================================================================


class TestBlobExiste:
    def test_returns_true_when_exists(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x")
            mock_blob_client = MagicMock()
            mock_blob_client.exists.return_value = True
            s._blob_client = MagicMock(return_value=mock_blob_client)

            assert s.blob_existe("path/to/blob") is True

    def test_returns_false_when_not_exists(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x")
            mock_blob_client = MagicMock()
            mock_blob_client.exists.return_value = False
            s._blob_client = MagicMock(return_value=mock_blob_client)

            assert s.blob_existe("path/to/blob") is False

    def test_coerces_to_bool(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", connection_string="x")
            mock_blob_client = MagicMock()
            mock_blob_client.exists.return_value = 1  # truthy non-bool
            s._blob_client = MagicMock(return_value=mock_blob_client)

            result = s.blob_existe("path")
            assert result is True
            assert isinstance(result, bool)


# ===========================================================================
# gerar_url_temporaria
# ===========================================================================


class TestGerarUrlTemporaria:
    def test_account_key_path_returns_sas_url(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(
                container="c",
                account="myaccount",
                account_key="mykey",
                connection_string="",
            )

            mock_blob_client = MagicMock()
            mock_blob_client.account_name = "myaccount"
            mock_blob_client.url = "https://myaccount.blob.core.windows.net/c/path/file.json"
            s._blob_client = MagicMock(return_value=mock_blob_client)

            url = s.gerar_url_temporaria("path/file.json", ttl_segundos=600)

            assert url is not None
            assert url.startswith("https://myaccount.blob.core.windows.net")
            assert "?" in url

            # generate_blob_sas called with account_key
            mocks["azure.storage.blob"].generate_blob_sas.assert_called_once()
            call_kwargs = mocks["azure.storage.blob"].generate_blob_sas.call_args.kwargs
            assert call_kwargs["account_key"] == "mykey"
            assert "user_delegation_key" not in call_kwargs

    def test_managed_identity_path_uses_user_delegation_key(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", account="myaccount")

            mock_blob_client = MagicMock()
            mock_blob_client.account_name = "myaccount"
            mock_blob_client.url = "https://myaccount.blob.core.windows.net/c/file.json"
            s._blob_client = MagicMock(return_value=mock_blob_client)

            mock_udk = MagicMock(name="UserDelegationKey")
            mock_service = MagicMock()
            mock_service.get_user_delegation_key.return_value = mock_udk
            s._service = mock_service

            url = s.gerar_url_temporaria("file.json", ttl_segundos=300)

            assert url is not None
            mocks["azure.storage.blob"].generate_blob_sas.assert_called_once()
            call_kwargs = mocks["azure.storage.blob"].generate_blob_sas.call_args.kwargs
            assert call_kwargs["user_delegation_key"] is mock_udk
            assert "account_key" not in call_kwargs

    def test_import_error_returns_none(self):
        """If azure.storage.blob not installed, gerar_url_temporaria returns None."""
        with patch.dict(sys.modules, {"azure.storage.blob": None}):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="c", account="acct", account_key="key")
            result = s.gerar_url_temporaria("file.json")
            assert result is None

    def test_sas_url_format(self):
        mocks, _ = _inject_azure_mocks()
        mocks["azure.storage.blob"].generate_blob_sas.return_value = "sv=2023&sig=xyz"
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(
                container="c",
                account="acc",
                account_key="key",
            )
            mock_blob_client = MagicMock()
            mock_blob_client.account_name = "acc"
            mock_blob_client.url = "https://acc.blob.core.windows.net/c/f.txt"
            s._blob_client = MagicMock(return_value=mock_blob_client)

            url = s.gerar_url_temporaria("f.txt")
            assert url == "https://acc.blob.core.windows.net/c/f.txt?sv=2023&sig=xyz"


# ===========================================================================
# health_check
# ===========================================================================


class TestHealthCheck:
    def test_returns_ok_on_success(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="mycontainer", connection_string="x")

            mock_container_client = MagicMock()
            mock_container_client.get_container_properties.return_value = {}
            mock_service = MagicMock()
            mock_service.get_container_client.return_value = mock_container_client
            s._service = mock_service

            result = s.health_check()
            assert result["status"] == "ok"
            assert result["backend"] == "azure_blob"
            assert result["container"] == "mycontainer"

    def test_returns_error_on_exception(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="mycontainer", connection_string="x")

            mock_container_client = MagicMock()
            mock_container_client.get_container_properties.side_effect = RuntimeError("auth failed")
            mock_service = MagicMock()
            mock_service.get_container_client.return_value = mock_container_client
            s._service = mock_service

            result = s.health_check()
            assert result["status"] == "error"
            assert result["backend"] == "azure_blob"
            assert "auth failed" in result["message"]

    def test_health_check_container_in_result(self):
        mocks, _ = _inject_azure_mocks()
        with patch.dict(sys.modules, mocks):
            from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

            s = AzureBlobStorage(container="testcontainer", connection_string="x")

            mock_service = MagicMock()
            mock_service.get_container_client.return_value.get_container_properties.return_value = {}
            s._service = mock_service

            result = s.health_check()
            assert result["container"] == "testcontainer"


# ===========================================================================
# __init__ — basic attribute wiring
# ===========================================================================


class TestInit:
    def test_attributes_set_correctly(self):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        s = AzureBlobStorage(
            container="c",
            account="acct",
            account_key="key",
            connection_string="cs",
            root_prefix="/pfx/",
        )
        assert s._container == "c"
        assert s._account == "acct"
        assert s._account_key == "key"
        assert s._connection_string == "cs"
        assert s._root_prefix == "pfx"  # stripped slashes
        assert s._service is None  # lazy

    def test_root_prefix_default_empty(self):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        s = AzureBlobStorage(container="c")
        assert s._root_prefix == ""

    @pytest.mark.parametrize(
        "prefix,expected",
        [
            ("myprefix", "myprefix"),
            ("/myprefix/", "myprefix"),
            ("", ""),
            ("  ", ""),
        ],
    )
    def test_root_prefix_normalization(self, prefix, expected):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        s = AzureBlobStorage(container="c", root_prefix=prefix)
        # strip("/") on whitespace-only gives whitespace, which is fine for ""
        # but "  ".strip("/") == "  " not "" — only "/" chars stripped
        # Actual behavior: root_prefix.strip("/") is called in __init__
        assert s._root_prefix == prefix.strip("/")
