"""Tests for ADR-047: SharePoint BlobStorage adapter and StorageProjectRepository.

All tests use mocks — no real SharePoint credentials required.

Covers:
- SharePointCredential.from_env() validation
- SharePointBlobStorage read/write/list/exists via mocked httpx
- Cache hit/miss with ETag
- Offline mode fallback
- StorageConcurrencyError on HTTP 412
- aprovar_versao() checkin call
- health_check() response parsing
- CatalogLoader SHAREPOINT backend with mock storage
- StorageProjectHandle: all ProjectHandle operations via BlobStoragePort
- StorageProjectRepository: create/get/list projects
- BlobStoragePort.aprovar_versao() default noop
- LocalBlobStorage.aprovar_versao() chmod
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.storage.storage_project_repository import (
    StorageProjectHandle,
    StorageProjectRepository,
)

# ---------------------------------------------------------------------------
# BlobStoragePort — default aprovar_versao is noop
# ---------------------------------------------------------------------------


class TestBlobStoragePortAprovacao:
    def test_default_aprovar_versao_is_noop(self):
        """Base port provides a default noop aprovar_versao."""
        storage = LocalBlobStorage(Path(tempfile.mkdtemp()))
        storage.gravar_blob("test.json", b'{"ok": true}')
        storage.aprovar_versao("test.json")  # Should not raise


# ---------------------------------------------------------------------------
# LocalBlobStorage.aprovar_versao
# ---------------------------------------------------------------------------


class TestLocalBlobStorageAprovacao:
    def test_aprovar_makes_readonly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalBlobStorage(Path(tmpdir))
            storage.gravar_blob("canonical.json", b"data")
            storage.aprovar_versao("canonical.json")
            p = Path(tmpdir) / "canonical.json"
            import stat

            assert not bool(p.stat().st_mode & stat.S_IWUSR)

    def test_aprovar_nonexistent_is_noop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalBlobStorage(Path(tmpdir))
            storage.aprovar_versao("nonexistent.json")  # should not raise


# ---------------------------------------------------------------------------
# SharePointCredential
# ---------------------------------------------------------------------------


class TestSharePointCredential:
    def test_from_env_missing_raises(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointCredential

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(EnvironmentError):
                SharePointCredential.from_env()

    def test_from_env_success(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointCredential

        env = {
            "CONCILIUM__SP_TENANT_ID": "t-id",
            "CONCILIUM__SP_CLIENT_ID": "c-id",
            "CONCILIUM__SP_CLIENT_SECRET": "secret",
        }
        with patch.dict(os.environ, env):
            cred = SharePointCredential.from_env()
            assert cred.tenant_id == "t-id"
            assert cred.client_secret == "secret"

    def test_no_secret_no_cert_raises(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointCredential

        with pytest.raises(ValueError):
            SharePointCredential(tenant_id="t", client_id="c")

    def test_acquire_token_msal_missing_raises(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointCredential

        cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
        with patch.dict("sys.modules", {"msal": None}):
            with pytest.raises(ImportError, match="msal"):
                cred.acquire_token()

    def test_acquire_token_success(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointCredential

        cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {"access_token": "tok123"}
        mock_msal = MagicMock()
        mock_msal.ConfidentialClientApplication.return_value = mock_app
        with patch.dict("sys.modules", {"msal": mock_msal}):
            token = cred.acquire_token()
        assert token == "tok123"

    def test_acquire_token_auth_failure_raises(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointCredential

        cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {"error": "invalid_client", "error_description": "bad cred"}
        mock_msal = MagicMock()
        mock_msal.ConfidentialClientApplication.return_value = mock_app
        with patch.dict("sys.modules", {"msal": mock_msal}):
            with pytest.raises(PermissionError, match="bad cred"):
                cred.acquire_token()


# ---------------------------------------------------------------------------
# SharePointBlobStorage — mock httpx
# ---------------------------------------------------------------------------


def _make_storage(tmp_cache: Path | None = None):
    from concilium.infrastructure.adapters.blob_storage.sharepoint import (
        SharePointBlobStorage,
        SharePointCredential,
    )

    cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
    cred._app = MagicMock()
    cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
    return SharePointBlobStorage(
        drive_id="drive-1",
        root_path="Concilium/test",
        credential=cred,
        cache_dir=tmp_cache,
        cache_ttl_minutes=60,
    )


class TestSharePointBlobStorage:
    def _mock_httpx(
        self, status: int, content: bytes = b"", json_data: dict | None = None, headers: dict | None = None
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.content = content
        mock_resp.headers = headers or {}
        if json_data is not None:
            mock_resp.json.return_value = json_data
        mock_resp.raise_for_status = MagicMock()
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        mock_httpx.put.return_value = mock_resp
        mock_httpx.post.return_value = mock_resp
        return mock_httpx

    def test_ler_blob_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200, content=b"hello world")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("config/cpus.json")
            assert result == b"hello world"

    def test_ler_blob_404_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(404)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(FileNotFoundError):
                    storage.ler_blob("missing.json")

    def test_ler_blob_fills_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            storage = _make_storage(cache_dir)
            mock_httpx = self._mock_httpx(
                200, content=b"cached", headers={"ETag": "abc123", "Last-Modified": "Mon, 1 Jan 2026"}
            )
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.ler_blob("test.json")
            # Cache file should exist
            assert any(cache_dir.glob("*.blob"))

    def test_ler_blob_uses_cache_on_304(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            # Pre-populate cache
            storage._cache.put("test.json", b"from_cache", "etag-1", "Mon")
            # Simulate 304 Not Modified
            mock_304 = MagicMock()
            mock_304.status_code = 304
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = mock_304
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("test.json")
            assert result == b"from_cache"

    def test_gravar_blob_small_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.gravar_blob("out.json", b"content")
            mock_httpx.put.assert_called_once()

    def test_gravar_blob_412_raises_concurrency_error(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import StorageConcurrencyError

        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(412)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(StorageConcurrencyError):
                    storage.gravar_blob("conflict.json", b"data")

    def test_gravar_blob_read_only_raises(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import (
            SharePointBlobStorage,
            SharePointCredential,
        )

        cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
        cred._app = MagicMock()
        cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
        storage = SharePointBlobStorage("d", "root", cred, read_only=True)
        with pytest.raises(PermissionError):
            storage.gravar_blob("file.json", b"x")

    def test_blob_existe_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                assert storage.blob_existe("exists.json") is True

    def test_blob_existe_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(404)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                assert storage.blob_existe("missing.json") is False

    def test_listar_blobs_paginated(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            # First page has 2 files + nextLink; second page has 1 file
            resp1 = MagicMock()
            resp1.status_code = 200
            resp1.json.return_value = {
                "value": [
                    {"name": "a.json", "file": {}},
                    {"name": "b.json", "file": {}},
                ],
                "@odata.nextLink": "https://graph.microsoft.com/page2",
            }
            resp1.raise_for_status = MagicMock()
            resp2 = MagicMock()
            resp2.status_code = 200
            resp2.json.return_value = {"value": [{"name": "c.json", "file": {}}]}
            resp2.raise_for_status = MagicMock()

            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = [resp1, resp2]
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                blobs = storage.listar_blobs("config/cpus")
            assert len(blobs) == 3

    def test_aprovar_versao_sends_checkin(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.aprovar_versao("v1/canonical.json")
            # Verify POST was called with checkin endpoint
            call_args = mock_httpx.post.call_args
            assert "checkin" in str(call_args)

    def test_health_check_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200, json_data={"name": "Concilium", "driveType": "documentLibrary"})
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.health_check()
            assert result["status"] == "ok"
            assert result["backend"] == "sharepoint"

    def test_health_check_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = Exception("timeout")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.health_check()
            assert result["status"] == "error"

    def test_client_raises_when_httpx_not_installed(self):
        """Lines 75-76: _client() raises ImportError when httpx is missing."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            with patch.dict("sys.modules", {"httpx": None}):
                with pytest.raises(ImportError, match="httpx"):
                    storage._client()

    def test_ler_blob_cached_reraises_when_not_offline(self):
        """Line 135: exception in cached fetch re-raises when offline=False."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._cache.put("file.json", b"cached", "etag-1", "Mon")
            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = OSError("connection reset")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(OSError):
                    storage.ler_blob("file.json")

    def test_deletar_blob_success(self):
        """Lines 277-284: deletar_blob sends DELETE and invalidates cache."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._cache.put("del.json", b"data", "e", "m")
            mock_resp = MagicMock()
            mock_resp.status_code = 204
            mock_resp.raise_for_status = MagicMock()
            mock_httpx = MagicMock()
            mock_httpx.delete.return_value = mock_resp
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.deletar_blob("del.json")
            mock_httpx.delete.assert_called_once()
            assert storage._cache.get("del.json") is None

    def test_deletar_blob_404_raises_file_not_found(self):
        """Lines 279-280: 404 on DELETE raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_httpx = MagicMock()
            mock_httpx.delete.return_value = mock_resp
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(FileNotFoundError):
                    storage.deletar_blob("missing.json")

    def test_deletar_blob_without_cache(self):
        """deletar_blob without cache_dir (self._cache is None) does not crash."""
        from concilium.infrastructure.adapters.blob_storage.sharepoint import (
            SharePointBlobStorage,
            SharePointCredential,
        )

        cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
        cred._app = MagicMock()
        cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
        storage = SharePointBlobStorage("drive-1", "Concilium/test", cred)
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.raise_for_status = MagicMock()
        mock_httpx = MagicMock()
        mock_httpx.delete.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            storage.deletar_blob("some.json")

    def test_ensure_root_path_idempotent(self):
        """Lines 328-331: ensure_root_path is a no-op on second call."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200, json_data={"name": "root"})
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.ensure_root_path()
                storage.ensure_root_path()  # second call does nothing
            assert mock_httpx.get.call_count == 1

    def test_ensure_root_path_empty_root_path_is_noop(self):
        """Lines 335-337: _ensure_root_path early returns when root_path is empty."""
        from concilium.infrastructure.adapters.blob_storage.sharepoint import (
            SharePointBlobStorage,
            SharePointCredential,
        )

        cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
        cred._app = MagicMock()
        cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
        storage = SharePointBlobStorage("drive-1", "", cred)
        mock_httpx = MagicMock()
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            storage._ensure_root_path(mock_httpx)
        mock_httpx.get.assert_not_called()

    def test_ensure_root_path_creates_when_not_exists(self):
        """Lines 342-362: _ensure_root_path creates folder segments when 404."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            # First GET → 404 (root doesn't exist), then POST for each segment
            get_resp = MagicMock()
            get_resp.status_code = 404
            post_resp = MagicMock()
            post_resp.status_code = 201
            post_resp.raise_for_status = MagicMock()
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = get_resp
            mock_httpx.post.return_value = post_resp
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.ensure_root_path()
            # "Concilium/test" has 2 segments → 2 POST calls
            assert mock_httpx.post.call_count == 2

    def test_ensure_root_path_already_exists_returns_early(self):
        """Lines 342-343: _ensure_root_path returns early when root already exists (200)."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200, json_data={"name": "root"})
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage._ensure_root_path(mock_httpx)
            mock_httpx.post.assert_not_called()

    def test_deletar_blob_non_404_non_204_calls_raise_for_status(self):
        """Line 282: deletar_blob with unexpected status calls r.raise_for_status()."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.raise_for_status = MagicMock(side_effect=Exception("server error"))
            mock_httpx = MagicMock()
            mock_httpx.delete.return_value = mock_resp
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(Exception, match="server error"):
                    storage.deletar_blob("bad.json")

    def test_aprovar_versao_404_raises_file_not_found(self):
        """Line 300: aprovar_versao with 404 raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(404)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(FileNotFoundError, match="não encontrado"):
                    storage.aprovar_versao("v1/canonical.json")

    def test_ensure_root_path_get_non_200_non_404_raises(self):
        """Line 345: _ensure_root_path raises when GET returns unexpected status."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            get_resp = MagicMock()
            get_resp.status_code = 500
            get_resp.raise_for_status = MagicMock(side_effect=Exception("internal server error"))
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = get_resp
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(Exception, match="internal server error"):
                    storage.ensure_root_path()

    def test_ensure_root_path_post_failure_calls_raise_for_status(self):
        """Line 360: _ensure_root_path raises when POST returns unexpected status."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            get_resp = MagicMock()
            get_resp.status_code = 404
            post_resp = MagicMock()
            post_resp.status_code = 500
            post_resp.raise_for_status = MagicMock(side_effect=Exception("folder create failed"))
            mock_httpx = MagicMock()
            mock_httpx.get.return_value = get_resp
            mock_httpx.post.return_value = post_resp
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(Exception, match="folder create failed"):
                    storage.ensure_root_path()

    def test_offline_mode_uses_stale_cache(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import (
            SharePointBlobStorage,
            SharePointCredential,
        )

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
            cred._app = MagicMock()
            cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
            storage = SharePointBlobStorage("d", "root", cred, cache_dir=cache_dir, offline=True)
            # Put stale cache (TTL would normally expire it)
            storage._cache.put("file.json", b"stale_data", "old-etag", "old-lm")
            # Force TTL expiry

            storage._cache._ttl = __import__("datetime").timedelta(seconds=0)
            # Normal get would return None (expired), stale should work in offline
            result = storage._cache.get_stale("file.json")
            assert result is not None and result[0] == b"stale_data"


# ---------------------------------------------------------------------------
# CatalogLoader with SHAREPOINT backend
# ---------------------------------------------------------------------------


class TestCatalogLoaderSharePoint:
    def test_sharepoint_backend_without_storage_raises(self):
        from concilium.infrastructure.catalog.catalog_loader import CatalogBackend, CatalogLoader

        loader = CatalogLoader(config_root=".", backend=CatalogBackend.SHAREPOINT)
        with pytest.raises(ValueError, match="sharepoint_storage"):
            loader._fetch_fresh("mendeslobo", None)

    def test_sharepoint_backend_with_mock_storage(self):
        from concilium.infrastructure.catalog.catalog_loader import CatalogBackend, CatalogLoader

        mock_storage = MagicMock()
        mock_storage.listar_blobs.return_value = []
        mock_storage.ler_blob.side_effect = FileNotFoundError
        with tempfile.TemporaryDirectory() as tmp:
            loader = CatalogLoader(
                config_root=tmp,
                project_root=tmp,
                backend=CatalogBackend.SHAREPOINT,
                sharepoint_storage=mock_storage,
            )
            snapshot, diff = loader.load("mendeslobo")
        assert snapshot is not None
        assert snapshot.meta.catalog_name == "mendeslobo"

    def test_sharepoint_enum_value(self):
        from concilium.infrastructure.catalog.catalog_loader import CatalogBackend

        assert CatalogBackend.SHAREPOINT.value == "sharepoint"
        assert CatalogBackend("sharepoint") == CatalogBackend.SHAREPOINT


# ---------------------------------------------------------------------------
# StorageProjectHandle
# ---------------------------------------------------------------------------


class TestStorageProjectHandle:
    def _make_handle(self, tmpdir: str) -> StorageProjectHandle:
        storage = LocalBlobStorage(Path(tmpdir))
        return StorageProjectHandle(storage, "proj-001")

    def test_write_and_read_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"id": "proj-001", "nome": "Test"})
            result = h.read_json("meta.json", {})
            assert result["nome"] == "Test"

    def test_read_json_missing_returns_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            result = h.read_json("nonexistent.json", {"default": True})
            assert result == {"default": True}

    def test_append_jsonl_and_read_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.append_jsonl("log.jsonl", {"event": "start"})
            h.append_jsonl("log.jsonl", {"event": "done"})
            lines = h.read_lines("log.jsonl")
            assert len(lines) == 2
            assert json.loads(lines[0])["event"] == "start"

    def test_new_version_creates_and_updates_meta(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"id": "proj-001", "current_version": None})
            v = h.new_version()
            assert v == "v1"
            assert h.current_version() == "v1"

    def test_new_version_increments(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"id": "proj-001", "current_version": None})
            v1 = h.new_version()
            v2 = h.new_version()
            assert v1 == "v1"
            assert v2 == "v2"

    def test_list_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"id": "proj-001", "current_version": None})
            h.new_version()
            h.new_version()
            versions = h.list_versions()
            assert "v1" in versions and "v2" in versions

    def test_exists_true_and_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("exists.json", {})
            assert h.exists("exists.json") is True
            assert h.exists("missing.json") is False

    def test_extend_and_resolve_cpu(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("overrides/cpus_override.json", {})
            h.extend_cpu("CPU-001", {"producao_horaria": 500.0})
            cpu = h.resolve_cpu("CPU-001")
            assert cpu["producao_horaria"] == 500.0

    def test_save_and_load_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            from concilium.application.skills import run_escopo_e_eap

            h = self._make_handle(tmp)
            h.write_json("meta.json", {"id": "proj-001", "current_version": None})
            h.new_version()
            # Create a minimal canonical via run_escopo_e_eap
            inputs = {
                "nome": "Test Storage",
                "tipo_obra": "terraplenagem",
                "localizacao": "BR",
                "coordenadas": {"lat": 0.0, "lng": 0.0},
                "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
                "data_inicio": "2026-06-01",
                "data_termino": "2027-06-01",
                "eap": [
                    {
                        "item_id": "eap-01",
                        "ordem": 1,
                        "cpu_id": "CPU-01",
                        "descricao": "Test",
                        "unidade": "m3",
                        "quantitativo": 100.0,
                    }
                ],
                "contexto_id": "test",
                "snapshot_catalogo_id": "snap",
                "snapshot_perfil_id": "snap",
            }
            canonical = run_escopo_e_eap(None, inputs).canonical
            h.save_canonical(canonical)
            loaded = h.load_canonical()
            assert loaded is not None
            assert loaded.projeto.nome == "Test Storage"

    def test_approve_marks_readonly(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"id": "proj-001", "current_version": None})
            h.new_version()
            h.write_json("v1/canonical.json", {"dummy": True})
            h.approve("v1")
            import stat

            p = Path(tmp) / "proj-001" / "v1" / "canonical.json"
            assert not bool(p.stat().st_mode & stat.S_IWUSR)


# ---------------------------------------------------------------------------
# StorageProjectRepository
# ---------------------------------------------------------------------------


class TestStorageProjectRepository:
    def test_create_and_get_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            repo = StorageProjectRepository(storage)
            h = repo.create_project("Obra Nova", "mendeslobo", catalogo_base="mendeslobo")
            assert h.meta.get("nome") == "Obra Nova"
            # Get it back
            pid = h.meta["id"]
            h2 = repo.get_project(pid)
            assert h2.meta["nome"] == "Obra Nova"

    def test_list_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            repo = StorageProjectRepository(storage)
            repo.create_project("P1", "ctx")
            repo.create_project("P2", "ctx")
            projects = repo.list_projects()
            assert len(projects) == 2

    def test_get_nonexistent_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            repo = StorageProjectRepository(storage)
            with pytest.raises(FileNotFoundError):
                repo.get_project("no-such-id")

    def test_create_initializes_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalBlobStorage(Path(tmp))
            repo = StorageProjectRepository(storage)
            h = repo.create_project("Test", "ctx")
            assert h.read_json("overrides/cpus_override.json", None) == {}
            assert h.read_json("overrides/bdi_override.json", None) == {}


# ---------------------------------------------------------------------------
# SharePointBlobStorage — from_env
# ---------------------------------------------------------------------------


class TestSharePointFromEnv:
    def test_from_env_success(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import (
            SharePointBlobStorage,
            SharePointCredential,
        )

        mock_sp = MagicMock()
        mock_sp.drive_id = "drive-123"
        mock_sp.root_path = "Concilium/data"
        mock_storage_settings = MagicMock()
        mock_storage_settings.sharepoint = mock_sp
        mock_cred = MagicMock(spec=SharePointCredential)
        mock_cred._app = MagicMock()

        with patch(
            "concilium.infrastructure.adapters.blob_storage.sharepoint.get_storage", return_value=mock_storage_settings
        ):
            with patch.object(SharePointCredential, "from_env", return_value=mock_cred):
                storage = SharePointBlobStorage.from_env()

        assert storage._drive_id == "drive-123"
        assert storage._root_path == "Concilium/data"

    def test_from_env_missing_drive_id_raises(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

        mock_sp = MagicMock()
        mock_sp.drive_id = ""
        mock_storage_settings = MagicMock()
        mock_storage_settings.sharepoint = mock_sp

        with patch(
            "concilium.infrastructure.adapters.blob_storage.sharepoint.get_storage", return_value=mock_storage_settings
        ):
            with pytest.raises(OSError, match="CONCILIUM__SP_DRIVE_ID"):
                SharePointBlobStorage.from_env()


# ---------------------------------------------------------------------------
# SharePointBlobStorage — missing coverage paths
# ---------------------------------------------------------------------------


def _make_storage_no_cache():
    from concilium.infrastructure.adapters.blob_storage.sharepoint import (
        SharePointBlobStorage,
        SharePointCredential,
    )

    cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
    cred._app = MagicMock()
    cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
    return SharePointBlobStorage("drive-1", "Concilium/test", cred)


class TestSharePointLerBlobEdgeCases:
    def _mock_resp(self, status: int, content: bytes = b"", json_data=None, headers=None):
        r = MagicMock()
        r.status_code = status
        r.content = content
        r.headers = headers or {}
        if json_data is not None:
            r.json.return_value = json_data
        r.raise_for_status = MagicMock()
        return r

    def test_ler_blob_without_cache(self):
        """Line 100→104: no cache_dir → goes directly to _ler_blob_direct."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = self._mock_resp(200, content=b"direct_data")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blob("file.json")
        assert result == b"direct_data"

    def test_ler_blob_cached_etag_200_refetches(self):
        """Lines 118-128: ETag check returns 200 → re-fetch content from content_url."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._cache.put("file.json", b"old_content", "etag-old", "Mon")

            check_resp = self._mock_resp(200, headers={"ETag": "etag-new", "Last-Modified": "Tue"})
            content_resp = self._mock_resp(200, content=b"new_content")

            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = [check_resp, content_resp]
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("file.json")
            assert result == b"new_content"

    def test_ler_blob_cached_offline_exception_uses_stale(self):
        """Lines 131-134: exception during ETag check while offline → returns stale cache."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._offline = True
            storage._cache.put("file.json", b"stale_data", "etag-1", "Mon")

            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = OSError("connection refused")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("file.json")
            assert result == b"stale_data"

    def test_ler_blob_direct_offline_stale_returns_content(self):
        """Lines 140-143: offline mode + expired cache → _ler_blob_direct returns stale."""
        import datetime

        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._offline = True
            storage._cache.put("file.json", b"stale_content", "etag-1", "Mon")
            # Force TTL expiry so _ler_blob_cached returns None
            storage._cache._ttl = datetime.timedelta(seconds=0)

            mock_httpx = MagicMock()
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("file.json")
            assert result == b"stale_content"

    def test_ler_blob_direct_offline_no_cache_raises(self):
        """Line 144: offline mode, no stale cache → FileNotFoundError."""
        storage = _make_storage_no_cache()
        storage._offline = True
        mock_httpx = MagicMock()
        with pytest.raises(FileNotFoundError, match="Modo offline"):
            storage._ler_blob_direct("missing.json", mock_httpx)

    def test_ler_blob_direct_http_exception_wraps(self):
        """Lines 151-152: network exception → FileNotFoundError with original cause."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = OSError("connection timeout")
        with pytest.raises(FileNotFoundError, match="Erro ao acessar SharePoint"):
            storage._ler_blob_direct("file.json", mock_httpx)

    def test_ler_blob_direct_retries_on_transient_429_then_succeeds(self):
        """429 (throttling) seguido de 200 é absorvido pelo retry — sem propagar erro."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = [
            self._mock_resp(429),
            self._mock_resp(200, content=b"ok_after_retry"),
        ]
        with patch("concilium.infrastructure.adapters.blob_storage.sharepoint.time.sleep"):
            result = storage._ler_blob_direct("file.json", mock_httpx)
        assert result == b"ok_after_retry"
        assert mock_httpx.get.call_count == 2

    def test_ler_blob_direct_gives_up_after_persistent_5xx(self):
        """503 persistente esgota as tentativas e vira StorageUnavailableError (503 + Retry-After na API)."""
        from concilium.domain.repositories.blob_storage_port import StorageUnavailableError

        storage = _make_storage_no_cache()
        persistent_503 = self._mock_resp(503)
        persistent_503.raise_for_status.side_effect = RuntimeError("503 Service Unavailable")
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = persistent_503
        with (
            patch("concilium.infrastructure.adapters.blob_storage.sharepoint.time.sleep"),
            pytest.raises(StorageUnavailableError, match="503"),
        ):
            storage._ler_blob_direct("file.json", mock_httpx)
        assert mock_httpx.get.call_count == 4  # tentativa inicial + 3 retries

    def test_listar_blobs_persistent_error_raises_storage_unavailable(self):
        """listar_blobs com erro persistente (não-404) também vira StorageUnavailableError."""
        from concilium.domain.repositories.blob_storage_port import StorageUnavailableError

        storage = _make_storage_no_cache()
        forbidden = self._mock_resp(403)
        forbidden.raise_for_status.side_effect = RuntimeError("403 Forbidden")
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = forbidden
        with patch.dict("sys.modules", {"httpx": mock_httpx}), pytest.raises(StorageUnavailableError, match="403"):
            storage.listar_blobs("projetos")


class TestSharePointGravarBlobEdgeCases:
    def test_gravar_blob_without_cache(self):
        """Line 181→exit: gravar_blob without cache_dir skips cache invalidation."""
        storage = _make_storage_no_cache()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_httpx = MagicMock()
        mock_httpx.put.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            storage.gravar_blob("file.json", b"content")
        mock_httpx.put.assert_called_once()

    def test_gravar_large_file_uses_upload_session(self):
        """Lines 179, 200-222: content >= 4 MB triggers _gravar_upload_session."""
        storage = _make_storage_no_cache()

        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = {"uploadUrl": "https://upload.graph.microsoft.com/abc"}

        put_resp = MagicMock()
        put_resp.raise_for_status = MagicMock()

        mock_httpx = MagicMock()
        mock_httpx.post.return_value = post_resp
        mock_httpx.put.return_value = put_resp

        large_content = b"x" * (5 * 1024 * 1024)  # 5 MB > 4 MB threshold
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            storage.gravar_blob("large.bin", large_content)

        mock_httpx.post.assert_called_once()
        assert mock_httpx.put.called


class TestSharePointListarBlobsEdgeCases:
    def test_listar_blobs_offline_exception_returns_empty(self):
        """Lines 238-241: offline mode + exception → returns empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._offline = True
            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = OSError("network error")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.listar_blobs("config")
            assert result == []

    def test_listar_blobs_not_offline_exception_raises(self):
        """Line 242: NOT offline + exception → raises FileNotFoundError."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = OSError("network error")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            with pytest.raises(FileNotFoundError):
                storage.listar_blobs("config")

    def test_listar_blobs_404_returns_empty(self):
        """Line 245: GET returns 404 → returns empty list."""
        storage = _make_storage_no_cache()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.listar_blobs("missing")
        assert result == []

    def test_listar_blobs_with_subfolder_recursion(self):
        """Lines 253-254: folder item triggers recursive listar_blobs call."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))

            parent_resp = MagicMock()
            parent_resp.status_code = 200
            parent_resp.raise_for_status = MagicMock()
            parent_resp.json.return_value = {
                "value": [
                    {"name": "subdir", "folder": {}},
                    {"name": "root_file.json", "file": {}},
                ]
            }

            sub_resp = MagicMock()
            sub_resp.status_code = 200
            sub_resp.raise_for_status = MagicMock()
            sub_resp.json.return_value = {"value": [{"name": "inner.json", "file": {}}]}

            mock_httpx = MagicMock()
            mock_httpx.get.side_effect = [parent_resp, sub_resp]
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                blobs = storage.listar_blobs("root")

            assert len(blobs) == 2
            assert any("root_file.json" in b for b in blobs)
            assert any("inner.json" in b for b in blobs)


class TestSharePointBlobExisteEdgeCases:
    def test_blob_existe_exception_returns_false(self):
        """Lines 268-269: exception during GET → returns False."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = OSError("network failure")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.blob_existe("file.json")
        assert result is False


class TestSharePointGerarUrlTemporaria:
    def test_gerar_url_success(self):
        """Lines 310-321: createLink 200 → returns webUrl."""
        storage = _make_storage_no_cache()
        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {"link": {"webUrl": "https://share.example.com/abc"}}
        mock_httpx = MagicMock()
        mock_httpx.post.return_value = post_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            url = storage.gerar_url_temporaria("doc.pdf")
        assert url == "https://share.example.com/abc"

    def test_gerar_url_201(self):
        """Lines 320-321: createLink 201 also returns webUrl."""
        storage = _make_storage_no_cache()
        post_resp = MagicMock()
        post_resp.status_code = 201
        post_resp.json.return_value = {"link": {"webUrl": "https://share.example.com/xyz"}}
        mock_httpx = MagicMock()
        mock_httpx.post.return_value = post_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            url = storage.gerar_url_temporaria("doc.pdf")
        assert url == "https://share.example.com/xyz"

    def test_gerar_url_exception_returns_none(self):
        """Lines 322-323: exception during createLink → returns None."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.post.side_effect = OSError("forbidden")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            url = storage.gerar_url_temporaria("doc.pdf")
        assert url is None

    def test_gerar_url_non_2xx_returns_none(self):
        """Line 324: createLink returns 403 → returns None."""
        storage = _make_storage_no_cache()
        post_resp = MagicMock()
        post_resp.status_code = 403
        mock_httpx = MagicMock()
        mock_httpx.post.return_value = post_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            url = storage.gerar_url_temporaria("doc.pdf")
        assert url is None


class TestSharePointHealthCheckEdgeCases:
    def test_health_check_non_200_returns_error_code(self):
        """Line 381: GET returns non-200 → error dict with status code."""
        storage = _make_storage_no_cache()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.health_check()
        assert result["status"] == "error"
        assert result["code"] == 503
        assert result["backend"] == "sharepoint"
