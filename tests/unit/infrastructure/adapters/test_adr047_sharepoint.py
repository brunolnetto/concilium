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
from unittest.mock import ANY, MagicMock, patch

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
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.get.return_value = mock_resp
        mock_httpx.put.return_value = mock_resp
        mock_httpx.post.return_value = mock_resp
        # 2026-08-11 (pooling): `_client()` agora chama `httpx.Client(...)` uma vez
        # e reusa o resultado — o mock precisa devolver a si mesmo (que já tem
        # get/put/post configurados) quando "instanciado".
        mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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

    def test_aprovar_versao_checks_out_before_checkin(self):
        """Graph exige checkout antes do checkin quando a biblioteca tem
        'Require Check Out' habilitado — sem isso, checkin sempre 400 (bug
        real reproduzido em produção: gravar_blob nunca faz checkout)."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            mock_httpx = self._mock_httpx(200)
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.aprovar_versao("v1/canonical.json")
            urls_chamadas = [str(call.args[0]) for call in mock_httpx.post.call_args_list]
            assert any(u.endswith(":/checkout") for u in urls_chamadas), urls_chamadas
            assert any(u.endswith(":/checkin") for u in urls_chamadas), urls_chamadas
            # checkout precisa vir ANTES do checkin
            idx_checkout = next(i for i, u in enumerate(urls_chamadas) if u.endswith(":/checkout"))
            idx_checkin = next(i for i, u in enumerate(urls_chamadas) if u.endswith(":/checkin"))
            assert idx_checkout < idx_checkin

    def test_aprovar_versao_checkout_failure_does_not_block_checkin(self):
        """Checkout é best-effort: se a biblioteca não exige check-out (ou já está
        checked out), o checkout pode falhar sem impedir o checkin real."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            checkin_resp = MagicMock(status_code=200)
            checkin_resp.raise_for_status = MagicMock()
            mock_httpx = MagicMock()
            mock_httpx.Client.return_value = mock_httpx
            mock_httpx.post.side_effect = [RuntimeError("checkout not supported"), checkin_resp]
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.aprovar_versao("v1/canonical.json")  # não deve levantar
            assert mock_httpx.post.call_count == 2

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
            mock_httpx.Client.return_value = mock_httpx
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

    def test_client_not_created_until_first_use(self):
        """`_http` só é populado no primeiro uso — client é lazy, não eager."""
        storage = _make_storage()
        assert storage._http is None

    def test_client_reused_across_multiple_operations(self):
        """2026-08-11 (pooling): `_client()` cria o `httpx.Client` UMA vez e reusa
        em todas as chamadas seguintes desta mesma instância — antes, cada
        operação (`httpx.get/put/post/delete` de módulo) abria e fechava uma
        conexão nova. `Client()` deve ser chamado 1x mesmo com 3 operações."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            ok_resp = MagicMock(status_code=200, content=b"", headers={})
            del_resp = MagicMock(status_code=204)
            mock_client = MagicMock()
            mock_client.get.return_value = ok_resp
            mock_client.delete.return_value = del_resp
            mock_httpx = MagicMock()
            mock_httpx.Client.return_value = mock_client
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                storage.blob_existe("a.json")
                storage.blob_existe("b.json")
                storage.deletar_blob("c.json")
            assert mock_httpx.Client.call_count == 1
            assert mock_client.get.call_count == 2
            assert mock_client.delete.call_count == 1

    def test_close_releases_and_resets_client(self):
        """close() fecha o client do pool e permite que uma chamada seguinte
        crie um novo (ex.: depois de `load_catalogo_via_storage` terminar)."""
        storage = _make_storage()
        mock_client = MagicMock()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_client
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            storage._client()
            storage.close()
        mock_client.close.assert_called_once()
        assert storage._http is None

    def test_close_before_any_use_is_noop(self):
        storage = _make_storage()
        storage.close()  # não deve lançar
        assert storage._http is None

    def test_ler_blob_cached_reraises_when_not_offline(self):
        """Line 135: exception in cached fetch re-raises when offline=False."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._cache.put("file.json", b"cached", "etag-1", "Mon")
            mock_httpx = MagicMock()
            mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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

    def test_tipo_projeto_reads_from_meta(self):
        """StorageProjectHandle deve satisfazer o protocolo ProjectHandle (tipo_projeto),
        assim como FileProjectHandle — sem isso, get_pipeline_strategy() quebra com
        AttributeError para qualquer projeto no backend SharePoint/S3/Azure."""
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"tipo_projeto": "project"})
            assert h.tipo_projeto == "project"

    def test_tipo_projeto_defaults_to_hot_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            assert h.tipo_projeto == "hot_project"

    def test_status_eap_reads_from_meta(self):
        """Idem para status_eap — usado por ProjectStrategy.validate_preconditions()."""
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"status_eap": "RASCUNHO_PRONTO"})
            assert h.status_eap == "RASCUNHO_PRONTO"

    def test_status_eap_defaults_to_ativo(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            assert h.status_eap == "ATIVO"

    def test_save_and_load_intermediate_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.save_intermediate_file("data.bin", b"\x00\x01\x02", "v1")
            assert h.load_intermediate_file("data.bin", "v1") == b"\x00\x01\x02"

    def test_save_intermediate_file_accepts_str(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.save_intermediate_file("data.txt", "conteúdo", "v1")
            assert h.load_intermediate_file("data.txt", "v1") == "conteúdo".encode()

    def test_load_intermediate_file_uses_current_version_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("meta.json", {"current_version": "v2"})
            h.save_intermediate_file("data.bin", b"x", "v2")
            assert h.load_intermediate_file("data.bin") == b"x"

    def test_load_intermediate_file_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            assert h.load_intermediate_file("missing.bin", "v1") is None

    def test_load_intermediate_file_no_current_version_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            assert h.load_intermediate_file("data.bin") is None

    def test_set_overlay_persists_and_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.set_overlay("cpu", "CPU-01", {"custo": 100}, actor="tester", motivo="ajuste")
            overlay = h.read_json("overrides/cpus_overlay.json", {})
            assert overlay["CPU-01"] == {"custo": 100}
            audit_lines = h.read_lines("overrides/overlay_audit.jsonl")
            assert len(audit_lines) == 1
            entry = json.loads(audit_lines[0])
            assert entry["event"] == "set_overlay"
            assert entry["item_id"] == "CPU-01"
            assert entry["actor"] == "tester"

    def test_set_overlay_non_dict_overlay_is_replaced(self):
        """If the overlay file on disk isn't a dict (corrupt/legacy data),
        set_overlay must discard it and start a fresh dict instead of raising."""
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("overrides/cpus_overlay.json", ["not", "a", "dict"])
            h.set_overlay("cpu", "CPU-01", {"custo": 100}, actor="tester", motivo="ajuste")
            overlay = h.read_json("overrides/cpus_overlay.json", {})
            assert overlay == {"CPU-01": {"custo": 100}}

    def test_load_resolved_catalog_returns_persisted_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            h.write_json("v1/resolved_catalog.json", {"cpus": ["CPU-01"]})
            assert h.load_resolved_catalog("v1") == {"cpus": ["CPU-01"]}

    def test_load_resolved_catalog_missing_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            assert h.load_resolved_catalog("v1") is None

    def test_load_resolved_catalog_no_version_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = self._make_handle(tmp)
            assert h.load_resolved_catalog() is None

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
        mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
            mock_httpx.get.side_effect = OSError("connection refused")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("file.json")
            assert result == b"stale_data"

    def test_ler_blob_cached_offline_exception_no_stale_reraises(self):
        """Branch 171→174: exception during ETag check while offline, but
        get_stale() returns falsy (no cached blob) → exception is re-raised
        instead of returning stale content."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._offline = True
            storage._cache.put("file.json", b"cached_data", "etag-1", "Mon")
            storage._cache.get_stale = MagicMock(return_value=None)

            mock_httpx = MagicMock()
            mock_httpx.Client.return_value = mock_httpx
            mock_httpx.get.side_effect = OSError("connection refused")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                with pytest.raises(OSError):
                    storage.ler_blob("file.json")

    def test_ler_blob_cached_etag_check_non_200_non_304_falls_through(self):
        """Branch 157→175: check response is neither 304 nor 200 (e.g. 500) →
        falls through to `return None`, then ler_blob falls back to direct read."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._cache.put("file.json", b"old_content", "etag-old", "Mon")

            check_resp = self._mock_resp(500)
            direct_resp = self._mock_resp(200, content=b"direct_fallback")

            mock_httpx = MagicMock()
            mock_httpx.Client.return_value = mock_httpx
            mock_httpx.get.side_effect = [check_resp, direct_resp]
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("file.json")
            assert result == b"direct_fallback"

    def test_ler_blob_cached_content_refetch_non_200_falls_through(self):
        """Branch 165→175: ETag check returns 200 but the content re-fetch does
        not (e.g. 404) → falls through to `return None` without caching,
        then ler_blob falls back to direct read."""
        with tempfile.TemporaryDirectory() as tmp:
            storage = _make_storage(Path(tmp))
            storage._cache.put("file.json", b"old_content", "etag-old", "Mon")

            check_resp = self._mock_resp(200, headers={"ETag": "etag-new", "Last-Modified": "Tue"})
            content_resp_fail = self._mock_resp(404)
            direct_resp = self._mock_resp(200, content=b"direct_fallback")

            mock_httpx = MagicMock()
            mock_httpx.Client.return_value = mock_httpx
            mock_httpx.get.side_effect = [check_resp, content_resp_fail, direct_resp]
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("file.json")
            assert result == b"direct_fallback"

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
            mock_httpx.Client.return_value = mock_httpx
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blob("file.json")
            assert result == b"stale_content"

    def test_ler_blob_direct_offline_no_cache_raises(self):
        """Line 144: offline mode, no stale cache → FileNotFoundError."""
        storage = _make_storage_no_cache()
        storage._offline = True
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        with pytest.raises(FileNotFoundError, match="Modo offline"):
            storage._ler_blob_direct("missing.json", mock_httpx)

    def test_ler_blob_direct_http_exception_wraps(self):
        """Lines 151-152: network exception → FileNotFoundError with original cause."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.get.side_effect = OSError("connection timeout")
        with pytest.raises(FileNotFoundError, match="Erro ao acessar SharePoint"):
            storage._ler_blob_direct("file.json", mock_httpx)

    def test_ler_blob_direct_retries_on_transient_429_then_succeeds(self):
        """429 (throttling) seguido de 200 é absorvido pelo retry — sem propagar erro."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
            mock_httpx.get.side_effect = OSError("network error")
            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.listar_blobs("config")
            assert result == []

    def test_listar_blobs_not_offline_exception_raises(self):
        """Line 242: NOT offline + exception → raises FileNotFoundError."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
            mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.post.return_value = post_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            url = storage.gerar_url_temporaria("doc.pdf")
        assert url == "https://share.example.com/xyz"

    def test_gerar_url_exception_returns_none(self):
        """Lines 322-323: exception during createLink → returns None."""
        storage = _make_storage_no_cache()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
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
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.get.return_value = mock_resp
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.health_check()
        assert result["status"] == "error"
        assert result["code"] == 503
        assert result["backend"] == "sharepoint"


from types import SimpleNamespace  # noqa: E402

from concilium.infrastructure.adapters.blob_storage.sharepoint import (  # noqa: E402
    SharePointBlobStorage,
    SharePointCredential,
)

# ─── sharepoint adapter (greatest_gaps_batch1) ───────────────────────────────

# ---------------------------------------------------------------------------
# SharePoint adapter
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, status_code=200, content=b"", headers=None, data=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._data = data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code not in (404, 412):
            raise RuntimeError(f"http {self.status_code}")


@pytest.fixture
def sp_cred() -> SharePointCredential:
    cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
    cred._app = MagicMock()
    cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
    return cred


def test_sharepoint_from_env_missing_drive_id_raises(monkeypatch):
    class _SP:
        drive_id = None
        root_path = "root"

    class _Storage:
        sharepoint = _SP()

    monkeypatch.setattr("concilium.infrastructure.adapters.blob_storage.sharepoint.get_storage", lambda: _Storage())
    with pytest.raises(OSError):
        SharePointBlobStorage.from_env()


def test_sharepoint_cached_etag_refresh_path(tmp_path, monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred, cache_dir=tmp_path)
    storage._cache.put("a.json", b"old", "etag0", "lm0")

    # First GET (item metadata) returns 200; second GET (content) returns 200 with new payload.
    httpx = SimpleNamespace(
        get=MagicMock(
            side_effect=[
                _Resp(status_code=200, headers={"ETag": "etag1", "Last-Modified": "lm1"}),
                _Resp(status_code=200, content=b"new"),
            ]
        )
    )
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    data = storage.ler_blob("a.json")
    assert data == b"new"


def test_sharepoint_cached_exception_offline_returns_stale(tmp_path, monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred, cache_dir=tmp_path, offline=True)
    storage._cache.put("b.json", b"stale", "etag0", "lm0")
    httpx = SimpleNamespace(get=MagicMock(side_effect=RuntimeError("network down")))
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    assert storage.ler_blob("b.json") == b"stale"


def test_sharepoint_direct_offline_no_cache_raises(tmp_path, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred, cache_dir=tmp_path, offline=True)
    with pytest.raises(FileNotFoundError, match="offline"):
        storage._ler_blob_direct("missing.json", httpx=SimpleNamespace())


def test_sharepoint_direct_request_exception_wrapped(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)
    httpx = SimpleNamespace(get=MagicMock(side_effect=RuntimeError("boom")))
    with pytest.raises(FileNotFoundError, match="Erro ao acessar SharePoint"):
        storage._ler_blob_direct("x.json", httpx=httpx)


def test_sharepoint_gravar_blob_large_upload_and_cache_invalidate(tmp_path, monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred, cache_dir=tmp_path)
    storage._cache.put("big.bin", b"old", "e", "lm")

    called = {"upload": False, "invalidated": False}

    def _upload(_httpx, path, content):
        called["upload"] = path == "big.bin" and len(content) > 0

    def _invalidate(path):
        called["invalidated"] = path == "big.bin"

    monkeypatch.setattr(storage, "_gravar_upload_session", _upload)
    monkeypatch.setattr(storage._cache, "invalidate", _invalidate)
    monkeypatch.setattr(storage, "_client", lambda: SimpleNamespace())
    storage._root_ensured = True  # skip ensure_root_path — not under test here

    storage.gravar_blob("big.bin", b"x" * (4 * 1024 * 1024))
    assert called["upload"] is True
    assert called["invalidated"] is True


def test_sharepoint_upload_session_chunk_loop(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)
    post_resp = _Resp(status_code=200, data={"uploadUrl": "https://upload"})
    put_resp = _Resp(status_code=200)
    httpx = SimpleNamespace(post=MagicMock(return_value=post_resp), put=MagicMock(return_value=put_resp))

    data = b"y" * (5 * 1024 * 1024 + 10)
    storage._gravar_upload_session(httpx=httpx, path="file.bin", content=data)
    # 2 chunks expected: one full 5MB + remainder
    assert httpx.put.call_count == 2


def test_sharepoint_listar_blobs_offline_exception_returns_empty(tmp_path, monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred, cache_dir=tmp_path, offline=True)
    httpx = SimpleNamespace(get=MagicMock(side_effect=RuntimeError("offline")))
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    assert storage.listar_blobs("abc") == []


def test_sharepoint_listar_blobs_404_returns_empty(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)
    httpx = SimpleNamespace(get=MagicMock(return_value=_Resp(status_code=404)))
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    assert storage.listar_blobs("abc") == []


def test_sharepoint_listar_blobs_recurses_into_subfolder(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)
    r1 = _Resp(status_code=200, data={"value": [{"name": "sub", "folder": {}}, {"name": "f1.json", "file": {}}]})
    r2 = _Resp(status_code=200, data={"value": [{"name": "f2.json", "file": {}}]})
    httpx = SimpleNamespace(get=MagicMock(side_effect=[r1, r2]))
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    blobs = storage.listar_blobs("prefix")
    assert "prefix/f1.json" in blobs
    assert "prefix/sub/f2.json" in blobs


def test_sharepoint_blob_existe_exception_false(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)
    httpx = SimpleNamespace(get=MagicMock(side_effect=RuntimeError("x")))
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    assert storage.blob_existe("any") is False


def test_sharepoint_aprovar_versao_404_raises(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)
    httpx = SimpleNamespace(post=MagicMock(return_value=_Resp(status_code=404)))
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    with pytest.raises(FileNotFoundError):
        storage.aprovar_versao("x")


def test_sharepoint_gerar_url_temporaria_non_200_and_exception(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)

    httpx_non200 = SimpleNamespace(post=MagicMock(return_value=_Resp(status_code=403)))
    monkeypatch.setattr(storage, "_client", lambda: httpx_non200)
    assert storage.gerar_url_temporaria("x") is None

    httpx_exc = SimpleNamespace(post=MagicMock(side_effect=RuntimeError("blocked")))
    monkeypatch.setattr(storage, "_client", lambda: httpx_exc)
    assert storage.gerar_url_temporaria("x") is None


def test_sharepoint_health_check_non_200_error_code(monkeypatch, sp_cred):
    storage = SharePointBlobStorage("d", "root", sp_cred)
    httpx = SimpleNamespace(get=MagicMock(return_value=_Resp(status_code=503)))
    monkeypatch.setattr(storage, "_client", lambda: httpx)

    result = storage.health_check()
    assert result["status"] == "error"
    assert result["code"] == 503


def _sp_cred() -> SharePointCredential:
    cred = SharePointCredential(tenant_id="t", client_id="c", client_secret="s")
    cred._app = MagicMock()
    cred._app.acquire_token_for_client.return_value = {"access_token": "tok"}
    return cred


# ─── sharepoint adapter (greatest_gaps_batch2) ───────────────────────────────


def test_sharepoint_success_and_error_branches(tmp_path, monkeypatch):
    cred = _sp_cred()
    # Garantir que variáveis de env de SP não poluem o teste via settings cacheados
    monkeypatch.delenv("CONCILIUM__SP_DRIVE_ID", raising=False)
    monkeypatch.delenv("CONCILIUM__SP_CLIENT_SECRET", raising=False)

    class _SP:
        drive_id = "drv"
        root_path = "root"

    class _Storage:
        sharepoint = _SP()

    monkeypatch.setattr("concilium.infrastructure.adapters.blob_storage.sharepoint.get_storage", lambda: _Storage())
    monkeypatch.setattr(
        "concilium.infrastructure.adapters.blob_storage.sharepoint.SharePointCredential.from_env",
        lambda: cred,
    )

    storage = SharePointBlobStorage.from_env(cache_dir=tmp_path)
    assert isinstance(storage, SharePointBlobStorage)

    # _ler_blob_direct offline branch using stale cache
    storage._cache.put("offline.json", b"cached", "e", "lm")
    storage._offline = True
    assert storage._ler_blob_direct("offline.json", httpx=SimpleNamespace()) == b"cached"
    storage._offline = False

    # Small write path and optimistic concurrency 412 branch
    httpx_put_412 = SimpleNamespace(put=MagicMock(return_value=_Resp(status_code=412)))
    with pytest.raises(Exception):  # noqa: B017
        storage._gravar_pequeno(httpx_put_412, "x.bin", b"abc")

    # listar_blobs exception while online should raise wrapped FileNotFoundError
    httpx_list_err = SimpleNamespace(get=MagicMock(side_effect=RuntimeError("net")))
    monkeypatch.setattr(storage, "_client", lambda: httpx_list_err)
    with pytest.raises(FileNotFoundError):
        storage.listar_blobs("pref")

    # Success branches: approve (checkout + checkin), temporary URL, health_check=ok
    httpx_ok = SimpleNamespace(
        post=MagicMock(
            side_effect=[
                _Resp(status_code=200),  # checkout (best-effort)
                _Resp(status_code=200),  # checkin
                _Resp(status_code=200, data={"link": {"webUrl": "u"}}),  # createLink
            ]
        ),
        get=MagicMock(return_value=_Resp(status_code=200, data={"name": "Drive", "driveType": "documentLibrary"})),
    )
    monkeypatch.setattr(storage, "_client", lambda: httpx_ok)
    storage.aprovar_versao("ok.txt")
    assert storage.gerar_url_temporaria("ok.txt") == "u"
    health = storage.health_check()
    assert health["status"] == "ok"
    assert health["drive_name"] == "Drive"


# ─── infrastructure/adapters/blob_storage/_sharepoint_auth.py ─────────────────


class TestSharePointAuthCoverage:
    def test_blob_cache_ttl_expiry_returns_none(self, tmp_path):
        """Line 128: BlobCache.get returns None when TTL is expired."""
        import datetime

        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import _BlobCache

        cache = _BlobCache(tmp_path, ttl_minutes=60)
        cache.put("key.json", b"data", "etag", "Mon")
        cache._ttl = datetime.timedelta(seconds=0)
        result = cache.get("key.json")
        assert result is None

    def test_blob_cache_get_corrupt_meta_returns_none(self, tmp_path):
        """Lines 130-131: BlobCache.get with corrupt meta returns None."""
        import hashlib

        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import _BlobCache

        cache = _BlobCache(tmp_path, ttl_minutes=60)
        cache.put("key.json", b"data", "etag", "Mon")
        key = hashlib.sha256(b"key.json").hexdigest()[:24]
        (tmp_path / f"{key}.meta").write_text("CORRUPT_JSON", encoding="utf-8")
        result = cache.get("key.json")
        assert result is None

    def test_blob_cache_get_stale_corrupt_meta_returns_none(self, tmp_path):
        """Lines 141-142: BlobCache.get_stale with corrupt meta returns None."""
        import hashlib

        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import _BlobCache

        cache = _BlobCache(tmp_path, ttl_minutes=60)
        cache.put("key2.json", b"data", "etag", "Mon")
        key = hashlib.sha256(b"key2.json").hexdigest()[:24]
        (tmp_path / f"{key}.meta").write_text("CORRUPT", encoding="utf-8")
        result = cache.get_stale("key2.json")
        assert result is None

    def test_acquire_token_cert_path(self, tmp_path):
        """Lines 73-74: acquire_token uses cert credential when cert_path exists."""
        from concilium.infrastructure.adapters.blob_storage._sharepoint_auth import SharePointCredential

        cert_file = tmp_path / "cert.pem"
        cert_file.write_text("-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----", encoding="utf-8")

        cred = SharePointCredential(
            tenant_id="tenant",
            client_id="client",
            client_secret=None,
            cert_path=cert_file,
        )

        mock_app = MagicMock()
        mock_app.acquire_token_for_client.return_value = {"access_token": "cert_token"}
        mock_msal = MagicMock()
        mock_msal.ConfidentialClientApplication.return_value = mock_app

        with patch.dict("sys.modules", {"msal": mock_msal}):
            token = cred.acquire_token()

        assert token == "cert_token"
        call_kwargs = mock_msal.ConfidentialClientApplication.call_args[1]
        assert "private_key" in call_kwargs.get("client_credential", {})


# ---------------------------------------------------------------------------
# Incidente 2026-08-11: tempestade de 429 sustentada — Retry-After ignorado +
# concorrência ilimitada de sequências de retry no mesmo processo.
# ---------------------------------------------------------------------------


class TestRetryAfterSeconds:
    def test_absent_header_returns_default(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import _retry_after_seconds

        r = MagicMock()
        r.headers = {}
        assert _retry_after_seconds(r, default=0.5) == 0.5

    def test_seconds_header_larger_than_default_is_used(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import _retry_after_seconds

        r = MagicMock()
        r.headers = {"Retry-After": "3"}
        assert _retry_after_seconds(r, default=0.5) == 3.0

    def test_seconds_header_smaller_than_default_uses_default(self):
        """O Graph pode pedir menos que nosso próprio mínimo — não confiamos
        nisso, usamos o maior dos dois."""
        from concilium.infrastructure.adapters.blob_storage.sharepoint import _retry_after_seconds

        r = MagicMock()
        r.headers = {"Retry-After": "0.1"}
        assert _retry_after_seconds(r, default=0.5) == 0.5

    def test_capped_at_max(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import (
            _RETRY_AFTER_CAP_S,
            _retry_after_seconds,
        )

        r = MagicMock()
        r.headers = {"Retry-After": "9999"}
        assert _retry_after_seconds(r, default=0.5) == _RETRY_AFTER_CAP_S

    def test_http_date_header_parsed(self):
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime

        from concilium.infrastructure.adapters.blob_storage.sharepoint import _retry_after_seconds

        future = datetime.now(UTC) + timedelta(seconds=4)
        header_value = format_datetime(future, usegmt=True)
        r = MagicMock()
        r.headers = {"Retry-After": header_value}
        result = _retry_after_seconds(r, default=0.5)
        assert 2.0 <= result <= 4.5  # margem por tempo de execução do teste

    def test_invalid_header_falls_back_to_default(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import _retry_after_seconds

        r = MagicMock()
        r.headers = {"Retry-After": "not-a-date-or-number"}
        assert _retry_after_seconds(r, default=0.5) == 0.5


class TestGetWithRetryRespectsRetryAfter:
    def test_sleeps_for_retry_after_value_not_fixed_schedule(self):
        storage = _make_storage_no_cache()
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "3"}
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.headers = {}

        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.get.side_effect = [resp_429, resp_200]

        with patch("concilium.infrastructure.adapters.blob_storage.sharepoint.time.sleep") as mock_sleep:
            result = storage._get_with_retry(mock_httpx, "http://x", {})

        assert result is resp_200
        mock_sleep.assert_called_once_with(3.0)

    def test_no_retry_after_uses_fixed_schedule(self):
        storage = _make_storage_no_cache()
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {}
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.headers = {}

        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.get.side_effect = [resp_429, resp_200]

        with patch("concilium.infrastructure.adapters.blob_storage.sharepoint.time.sleep") as mock_sleep:
            storage._get_with_retry(mock_httpx, "http://x", {})

        mock_sleep.assert_called_once_with(0.5)


class TestConcurrencyLimiter:
    """issue 2026-08-11: várias sequências de retry concorrentes no mesmo processo
    amplificavam o throttling em vez de esperar ele passar — agora limitado a
    _MAX_CONCURRENT_REQUESTS sequências simultâneas."""

    def test_limits_concurrent_retry_sequences(self):
        import threading
        import time as time_module

        from concilium.infrastructure.adapters.blob_storage import sharepoint as sp_module

        limit = 2
        test_semaphore = threading.Semaphore(limit)
        state = {"active": 0, "peak": 0}
        lock = threading.Lock()

        def _slow_get(*args, **kwargs):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time_module.sleep(0.05)
            with lock:
                state["active"] -= 1
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            return resp

        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.get.side_effect = _slow_get

        storage = _make_storage_no_cache()

        with patch.object(sp_module, "_concurrency_limiter", test_semaphore):
            threads = [
                threading.Thread(target=storage._get_with_retry, args=(mock_httpx, "http://x", {})) for _ in range(6)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert state["peak"] <= limit
        assert mock_httpx.get.call_count == 6


# ---------------------------------------------------------------------------
# ler_blobs_batch — Graph $batch (issue #147/#148/#149/#153: ataca o N+1)
# ---------------------------------------------------------------------------


def _batch_response(pairs: list[tuple[str, int, object]]):
    """Monta um mock de resposta de `$batch`: pairs de (id, status, body)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "responses": [{"id": rid, "status": status, "body": body} for rid, status, body in pairs]
    }
    return resp


class TestSharePointBlobStorageLerBlobsBatch:
    def test_empty_paths_returns_empty_without_http_call(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            assert storage.ler_blobs_batch([]) == {}
        mock_httpx.post.assert_not_called()

    def test_decodes_native_json_body(self):
        """Caso esperado: arquivo .json volta como objeto JSON nativo no body
        (Content-Type application/json da sub-resposta), sem base64."""
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.post.return_value = _batch_response([("0", 200, {"id": "PROD-1", "valor_horario": 10.0})])
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["produtividades/PROD-1.json"])
        assert json.loads(result["produtividades/PROD-1.json"]) == {"id": "PROD-1", "valor_horario": 10.0}

    def test_decodes_base64_body(self):
        import base64

        raw = json.dumps({"id": "PROD-2"}).encode("utf-8")
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.post.return_value = _batch_response([("0", 200, base64.b64encode(raw).decode("ascii"))])
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["produtividades/PROD-2.json"])
        assert result["produtividades/PROD-2.json"] == raw

    def test_decodes_plain_string_body(self):
        """String que não decodifica como base64 válido é tratada como texto puro."""
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.post.return_value = _batch_response([("0", 200, "não é base64 válido")])
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["a.json"])
        assert result["a.json"] == "não é base64 válido".encode()

    def test_non_200_sub_response_omitted(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.post.return_value = _batch_response(
            [("0", 200, {"id": "OK"}), ("1", 404, None)]
        )
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["ok.json", "missing.json"])
        assert "ok.json" in result
        assert "missing.json" not in result

    def test_unrecognized_body_type_omitted(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.post.return_value = _batch_response([("0", 200, 12345)])
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["weird.json"])
        assert result == {}

    def test_batch_call_non_200_omits_whole_chunk_without_raising(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        resp = MagicMock()
        resp.status_code = 500
        mock_httpx.post.return_value = resp
        with (
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch("concilium.infrastructure.adapters.blob_storage.sharepoint.time.sleep"),
        ):
            result = storage.ler_blobs_batch(["a.json", "b.json"])
        assert result == {}

    def test_batch_call_exception_omits_chunk_without_raising(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.post.side_effect = RuntimeError("rede caiu")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["a.json"])
        assert result == {}

    def test_splits_into_chunks_of_20(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        def _respond(url, headers, json, timeout):
            pairs = [(r["id"], 200, {"i": r["id"]}) for r in json["requests"]]
            return _batch_response(pairs)

        mock_httpx.post.side_effect = _respond
        paths = [f"produtividades/PROD-{i:03d}.json" for i in range(45)]  # 3 lotes: 20+20+5

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(paths)

        assert mock_httpx.post.call_count == 3
        for call in mock_httpx.post.call_args_list[:-1]:
            assert len(call.kwargs["json"]["requests"]) == 20
        assert len(mock_httpx.post.call_args_list[-1].kwargs["json"]["requests"]) == 5
        assert len(result) == 45

    def test_retries_on_transient_429_then_succeeds(self):
        """$batch está sujeito ao mesmo throttling do Graph que as chamadas
        individuais — precisa do mesmo retry/backoff (_post_with_retry)."""
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {}
        resp_200 = _batch_response([("0", 200, {"id": "OK"})])
        mock_httpx.post.side_effect = [resp_429, resp_200]

        with (
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch("concilium.infrastructure.adapters.blob_storage.sharepoint.time.sleep"),
        ):
            result = storage.ler_blobs_batch(["a.json"])

        assert "a.json" in result
        assert mock_httpx.post.call_count == 2

    def test_relative_content_url_has_no_absolute_graph_prefix(self):
        """Sub-requests de $batch são relativas ao root do Graph — URL absoluta
        é rejeitada pela API."""
        storage = _make_storage()
        url = storage._batch_relative_content_url("produtividades/PROD-1.json")
        assert url == "/drives/drive-1/root:/Concilium/test/produtividades/PROD-1.json:/content"
        assert not url.startswith("http")

    def test_302_sub_response_follows_location_header(self):
        """Caso real (confirmado em produção, 2026-08-11): Graph retorna 302 com
        Location pré-autenticado para drives de SharePoint. O conteúdo deve ser
        buscado na URL do Location, não descartado."""
        download_url = "https://mendesloboconstrucao.sharepoint.com/sites/engenharia/_layouts/15/download.aspx?UniqueId=abc&tempauth=v1.token"
        content_bytes = json.dumps({"id": "CPU-001"}).encode("utf-8")

        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        resp_batch = MagicMock()
        resp_batch.status_code = 200
        resp_batch.json.return_value = {
            "responses": [{"id": "0", "status": 302, "headers": {"Location": download_url}, "body": ""}]
        }
        mock_httpx.post.return_value = resp_batch

        resp_download = MagicMock()
        resp_download.status_code = 200
        resp_download.content = content_bytes
        mock_httpx.get.return_value = resp_download

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["cpus/CPU-001.json"])

        assert json.loads(result["cpus/CPU-001.json"]) == {"id": "CPU-001"}
        mock_httpx.get.assert_called_once_with(download_url, follow_redirects=True, timeout=ANY)

    def test_302_without_location_header_omitted(self):
        """302 sem Location não vira conteúdo — cai pro fallback individual."""
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        resp_batch = MagicMock()
        resp_batch.status_code = 200
        resp_batch.json.return_value = {
            "responses": [{"id": "0", "status": 302, "headers": {}, "body": ""}]
        }
        mock_httpx.post.return_value = resp_batch

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["a.json"])

        assert result == {}
        mock_httpx.get.assert_not_called()

    def test_all_redirect_codes_collected(self):
        """301/303/307/308 também são seguidos — não só 302."""
        download_url = "https://cdn.example.com/file"
        content_bytes = b'{"id": "x"}'

        for redirect_status in (301, 303, 307, 308):
            storage = _make_storage()
            mock_httpx = MagicMock()
            mock_httpx.Client.return_value = mock_httpx

            resp_batch = MagicMock()
            resp_batch.status_code = 200
            resp_batch.json.return_value = {
                "responses": [{"id": "0", "status": redirect_status, "headers": {"Location": download_url}, "body": ""}]
            }
            mock_httpx.post.return_value = resp_batch

            resp_dl = MagicMock()
            resp_dl.status_code = 200
            resp_dl.content = content_bytes
            mock_httpx.get.return_value = resp_dl

            with patch.dict("sys.modules", {"httpx": mock_httpx}):
                result = storage.ler_blobs_batch(["a.json"])

            assert "a.json" in result, f"status {redirect_status} não foi seguido"

    def test_mixed_200_and_302_sub_responses(self):
        """200 direto e 302 redirect no mesmo lote — ambos resolvidos."""
        direct_bytes = json.dumps({"id": "direct"}).encode("utf-8")
        redirect_bytes = json.dumps({"id": "redirect"}).encode("utf-8")
        download_url = "https://cdn.example.com/redirect"

        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        resp_batch = MagicMock()
        resp_batch.status_code = 200
        resp_batch.json.return_value = {
            "responses": [
                {"id": "0", "status": 200, "body": {"id": "direct"}},
                {"id": "1", "status": 302, "headers": {"Location": download_url}, "body": ""},
            ]
        }
        mock_httpx.post.return_value = resp_batch

        resp_dl = MagicMock()
        resp_dl.status_code = 200
        resp_dl.content = redirect_bytes
        mock_httpx.get.return_value = resp_dl

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["direct.json", "redirect.json"])

        assert json.loads(result["direct.json"]) == {"id": "direct"}
        assert json.loads(result["redirect.json"]) == {"id": "redirect"}

    def test_302_download_failure_omits_path(self):
        """Falha no download da URL pré-autenticada omite o path — não levanta."""
        download_url = "https://cdn.example.com/file"

        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        resp_batch = MagicMock()
        resp_batch.status_code = 200
        resp_batch.json.return_value = {
            "responses": [{"id": "0", "status": 302, "headers": {"Location": download_url}, "body": ""}]
        }
        mock_httpx.post.return_value = resp_batch
        mock_httpx.get.side_effect = RuntimeError("download falhou")

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = storage.ler_blobs_batch(["a.json"])

        assert result == {}


class TestSharePointFetchDownloadUrlsParallel:
    def test_fetches_content_from_preauth_url(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        content = b'{"id": "CPU-001"}'
        resp = MagicMock()
        resp.status_code = 200
        resp.content = content
        mock_httpx.get.return_value = resp

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            httpx_client = storage._client()
            result = storage._fetch_download_urls_parallel(
                httpx_client, {"cpus/CPU-001.json": "https://cdn.example.com/file"}
            )

        assert result == {"cpus/CPU-001.json": content}

    def test_non_200_download_omitted(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        resp = MagicMock()
        resp.status_code = 403
        mock_httpx.get.return_value = resp

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            httpx_client = storage._client()
            result = storage._fetch_download_urls_parallel(
                httpx_client, {"a.json": "https://cdn.example.com/file"}
            )

        assert result == {}

    def test_exception_during_download_omitted(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx
        mock_httpx.get.side_effect = RuntimeError("timeout")

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            httpx_client = storage._client()
            result = storage._fetch_download_urls_parallel(
                httpx_client, {"a.json": "https://cdn.example.com/file"}
            )

        assert result == {}

    def test_multiple_urls_fetched_in_parallel(self):
        storage = _make_storage()
        mock_httpx = MagicMock()
        mock_httpx.Client.return_value = mock_httpx

        files = {f"f{i}.json": f"https://cdn.example.com/{i}" for i in range(5)}
        contents = {url: f'{{"i":{i}}}'.encode() for i, url in enumerate(files.values())}

        def _get(url, **_):
            r = MagicMock()
            r.status_code = 200
            r.content = contents[url]
            return r

        mock_httpx.get.side_effect = _get

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            httpx_client = storage._client()
            result = storage._fetch_download_urls_parallel(httpx_client, files)

        assert len(result) == 5
        assert mock_httpx.get.call_count == 5
