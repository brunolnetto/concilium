"""Tests for ADR-180: AsyncSharePointBlobStorage (httpx.AsyncClient ponta a ponta).

Não é um espelho linha-a-linha da suíte síncrona (test_adr047_sharepoint.py,
~1560 linhas) — cobre os mesmos comportamentos-chave (leitura com cache,
retry transitório, escrita, listagem paginada/recursiva, delete, aprovação,
health_check) mais o teste que justifica a ADR inteira: cancelamento real
via asyncio.wait_for encerra a chamada em andamento, não abandona uma thread.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_async_httpx(status_code: int = 200, content: bytes = b"", json_data=None, headers=None):
    """Constrói um módulo httpx fake cujo AsyncClient() é um async context manager
    com get/put/post/delete AsyncMock, todos retornando a mesma resposta."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = content
    mock_resp.headers = headers or {}
    mock_resp.text = content.decode("utf-8", errors="ignore") if content else ""
    if json_data is not None:
        mock_resp.json.return_value = json_data
    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        mock_resp.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.put = AsyncMock(return_value=mock_resp)
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.delete = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_httpx = MagicMock()
    mock_httpx.AsyncClient = MagicMock(return_value=mock_client)
    return mock_httpx, mock_client, mock_resp


def _make_storage(cache_dir: Path | None = None):
    from concilium.infrastructure.adapters.blob_storage.sharepoint_async import AsyncSharePointBlobStorage

    cred = MagicMock()
    cred.acquire_token.return_value = "fake-token"
    return AsyncSharePointBlobStorage(
        drive_id="drive-1",
        root_path="root",
        credential=cred,
        cache_dir=cache_dir,
    )


class TestFromEnv:
    def test_missing_drive_id_raises(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint_async import AsyncSharePointBlobStorage

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("concilium.infrastructure.settings.get_storage") as mock_gs,
        ):
            mock_gs.return_value.sharepoint.drive_id = ""
            mock_gs.return_value.sharepoint.system_drive_id = ""
            with pytest.raises(OSError, match="DRIVE_ID"):
                AsyncSharePointBlobStorage.from_env()


class TestLerBlob:
    async def test_ler_blob_success(self):
        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(200, content=b"hello world")
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await storage.ler_blob("foo.json")
        assert result == b"hello world"

    async def test_ler_blob_404_raises_file_not_found(self):
        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(404)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            with pytest.raises(FileNotFoundError):
                await storage.ler_blob("missing.json")

    async def test_ler_blob_fills_cache(self, tmp_path):
        storage = _make_storage(cache_dir=tmp_path)
        mock_httpx, _client, _resp = _mock_async_httpx(
            200, content=b"data", headers={"ETag": "abc", "Last-Modified": "today"}
        )
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await storage.ler_blob("foo.json")
        assert result == b"data"
        cached = storage._cache.get("foo.json")
        assert cached is not None
        assert cached[0] == b"data"

    async def test_ler_blob_uses_cache_on_304(self, tmp_path):
        storage = _make_storage(cache_dir=tmp_path)
        storage._cache.put("foo.json", b"cached-content", "etag-1", "lm-1")

        mock_304 = MagicMock()
        mock_304.status_code = 304
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_304)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await storage.ler_blob("foo.json")
        assert result == b"cached-content"


class TestRetryTransientStatus:
    async def test_retries_then_succeeds_without_blocking_event_loop(self):
        """asyncio.sleep (não time.sleep) durante o backoff — outra tarefa
        concorrente deve progredir enquanto o retry está em andamento."""
        storage = _make_storage()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.content = b"ok"
        resp_200.headers = {}

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[resp_429, resp_200])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        progressed = []

        async def _other_task():
            await asyncio.sleep(0)
            progressed.append("ran-during-retry")

        with (
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch(
                "concilium.infrastructure.adapters.blob_storage.sharepoint_async._TRANSIENT_RETRY_DELAYS_S",
                (0.05,),
            ),
        ):
            result, _ = await asyncio.gather(storage.ler_blob("foo.json"), _other_task())

        assert result == b"ok"
        assert progressed == ["ran-during-retry"]
        assert mock_client.get.call_count == 2


class TestGravarBlob:
    async def test_gravar_blob_small_file(self):
        storage = _make_storage()
        mock_httpx, mock_client, _resp = _mock_async_httpx(200)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            await storage.gravar_blob("foo.json", b"content")
        mock_client.put.assert_called_once()

    async def test_gravar_blob_412_raises_concurrency_error(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import StorageConcurrencyError

        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(412)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            with pytest.raises(StorageConcurrencyError):
                await storage.gravar_blob("foo.json", b"content")

    async def test_gravar_blob_read_only_raises(self):
        storage = _make_storage()
        storage._read_only = True
        with pytest.raises(PermissionError):
            await storage.gravar_blob("foo.json", b"content")


class TestBlobExiste:
    async def test_blob_existe_true(self):
        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(200)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            assert await storage.blob_existe("foo.json") is True

    async def test_blob_existe_false_on_404(self):
        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(404)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            assert await storage.blob_existe("foo.json") is False


class TestListarBlobs:
    async def test_listar_blobs_paginated_and_recursive(self):
        storage = _make_storage()

        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "value": [{"name": "sub", "folder": {}}],
            "@odata.nextLink": "https://graph/next",
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {"value": [{"name": "a.json", "file": {}}]}
        sub_page = MagicMock()
        sub_page.status_code = 200
        sub_page.json.return_value = {"value": [{"name": "b.json", "file": {}}]}

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[page1, sub_page, page2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await storage.listar_blobs("")

        assert "sub/b.json" in result
        assert "a.json" in result

    async def test_listar_blobs_404_returns_empty(self):
        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(404)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            assert await storage.listar_blobs("prefix") == []


class TestDeletarBlob:
    async def test_deletar_blob_success(self):
        storage = _make_storage()
        mock_httpx, mock_client, _resp = _mock_async_httpx(204)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            await storage.deletar_blob("foo.json")
        mock_client.delete.assert_called_once()

    async def test_deletar_blob_404_raises(self):
        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(404)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            with pytest.raises(FileNotFoundError):
                await storage.deletar_blob("foo.json")


class TestAprovarVersao:
    async def test_checkout_then_checkin(self):
        storage = _make_storage()
        mock_httpx, mock_client, _resp = _mock_async_httpx(200)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            await storage.aprovar_versao("foo.json")
        assert mock_client.post.call_count == 2
        urls = [str(call.args[0]) for call in mock_client.post.call_args_list]
        assert any("checkout" in u for u in urls)
        assert any("checkin" in u for u in urls)

    async def test_checkout_failure_does_not_block_checkin(self):
        storage = _make_storage()
        checkin_resp = MagicMock()
        checkin_resp.status_code = 200
        checkin_resp.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=[RuntimeError("checkout not supported"), checkin_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            await storage.aprovar_versao("foo.json")
        assert mock_client.post.call_count == 2


class TestHealthCheck:
    async def test_health_check_ok(self):
        storage = _make_storage()
        mock_httpx, _client, _resp = _mock_async_httpx(
            200, json_data={"name": "Concilium", "driveType": "documentLibrary"}
        )
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await storage.health_check()
        assert result["status"] == "ok"
        assert result["backend"] == "sharepoint"

    async def test_health_check_error_is_caught(self):
        storage = _make_storage()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)
        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = await storage.health_check()
        assert result["status"] == "error"


class TestCancelamentoReal:
    """O motivo de existir da ADR-180: asyncio.wait_for sobre uma coroutine
    nativa cancela de verdade — diferente de wait_for sobre asyncio.to_thread,
    que só abandona a espera e deixa a thread presa rodando (ver ADR-180 P1/P4).
    """

    async def test_wait_for_timeout_cancels_the_inflight_request(self):
        storage = _make_storage()
        cancelled = False

        async def _hangs_forever(*args, **kwargs):
            nonlocal cancelled
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                cancelled = True
                raise

        mock_client = MagicMock()
        mock_client.get = _hangs_forever
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(storage.ler_blob("foo.json"), timeout=0.05)

        # Dá uma volta no event loop para a CancelledError propagar antes de checar.
        await asyncio.sleep(0)
        assert cancelled is True


class TestRetryAfterRespectedAsync:
    """Espelho async de TestGetWithRetryRespectsRetryAfter (test_adr047_sharepoint.py) —
    mesmo incidente 2026-08-11, mesma correção (_retry_after_seconds compartilhado
    entre os dois módulos, ver import em sharepoint_async.py)."""

    async def test_sleeps_for_retry_after_value_not_fixed_schedule(self):
        storage = _make_storage()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "3"}
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.headers = {}
        resp_200.content = b"ok"

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[resp_429, resp_200])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with (
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch("concilium.infrastructure.adapters.blob_storage.sharepoint_async.asyncio.sleep") as mock_sleep,
        ):
            result = await storage.ler_blob("foo.json")

        assert result == b"ok"
        mock_sleep.assert_called_once_with(3.0)


class TestConcurrencyLimiterAsync:
    """Espelho async de TestConcurrencyLimiter (test_adr047_sharepoint.py) —
    asyncio.Semaphore em vez de threading.Semaphore, domínio próprio."""

    async def test_limits_concurrent_retry_sequences(self):
        import concilium.infrastructure.adapters.blob_storage.sharepoint_async as sp_async_module

        storage = _make_storage()
        limit = 2
        test_semaphore = asyncio.Semaphore(limit)
        state = {"active": 0, "peak": 0}

        async def _slow_get(*args, **kwargs):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.05)
            state["active"] -= 1
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            return resp

        mock_client = MagicMock()
        mock_client.get = _slow_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock(return_value=mock_client)

        with (
            patch.dict("sys.modules", {"httpx": mock_httpx}),
            patch.object(sp_async_module, "_concurrency_limiter", test_semaphore),
        ):
            await asyncio.gather(*(storage._get_with_retry(f"http://x/{i}", {}) for i in range(6)))

        assert state["peak"] <= limit
