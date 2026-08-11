"""SharePoint backend assíncrono via AsyncBlobStoragePort (ADR-180 F2).

Espelho de `sharepoint.py` (síncrono, ADR-047) usando `httpx.AsyncClient` de
ponta a ponta. Existe para permitir cancelamento real (`asyncio.wait_for`
sobre uma coroutine fecha o socket subjacente; sobre `asyncio.to_thread` só
abandona a espera — a thread continua presa, ver ADR-180 P1/P4).

Escopo desta fase (ADR-180 D6): só o suficiente para `ping()`/`listar_projetos()`
(issue #148/#149). O cache local ETag+TTL (`_BlobCache`) permanece síncrono —
é I/O de disco, não é a origem dos hangs observados (ADR-180 A4). A aquisição
de token MSAL (`SharePointCredential.acquire_token()`) também permanece
síncrona internamente e é chamada via `asyncio.to_thread` (ADR-180 D3) — já
tem timeout de 15s (`_MSAL_HTTP_TIMEOUT_S`) e raramente bate rede (MSAL
cacheia o token internamente).

Mantido deliberadamente como um espelho 1:1 de `sharepoint.py`, não uma
refatoração — qualquer divergência de comportamento entre os dois é bug,
não escolha de design (ver suíte de testes parametrizada, ADR-180 F5).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC
from pathlib import Path
from typing import Any

from concilium.domain.repositories.async_blob_storage_port import AsyncBlobStoragePort
from concilium.domain.repositories.blob_storage_port import StorageUnavailableError
from concilium.infrastructure.settings import get_storage

from ._sharepoint_auth import SharePointCredential, _BlobCache
from .sharepoint import (
    _GRAPH_BASE,
    _LARGE_FILE_THRESHOLD,
    _MAX_CONCURRENT_REQUESTS,
    _READ_TIMEOUT_S,
    _TRANSIENT_RETRY_DELAYS_S,
    _TRANSIENT_STATUS_CODES,
    _WRITE_TIMEOUT_S,
    StorageConcurrencyError,
    _retry_after_seconds,
)

logger = logging.getLogger(__name__)

# 2026-08-11: mesmo limite de concorrência do módulo síncrono (ver sharepoint.py),
# mas em domínio próprio — asyncio.Semaphore não é intercambiável com
# threading.Semaphore. Cada domínio (thread pool do caminho síncrono legado vs.
# coroutines deste módulo) tem seu próprio teto independente.
_concurrency_limiter = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)


class AsyncSharePointBlobStorage(AsyncBlobStoragePort):
    """AsyncBlobStoragePort backed by Microsoft SharePoint / OneDrive for Business.

    Ver `SharePointBlobStorage` (sharepoint.py) para a documentação completa
    de contrato de cada operação — não duplicada aqui.
    """

    def __init__(
        self,
        drive_id: str,
        root_path: str,
        credential: SharePointCredential,
        *,
        cache_dir: Path | None = None,
        cache_ttl_minutes: int = 60,
        read_only: bool = False,
        offline: bool = False,
    ) -> None:
        self._drive_id = drive_id
        self._root_path = root_path.strip("/")
        self._credential = credential
        self._read_only = read_only
        self._offline = offline
        self._cache: _BlobCache | None = _BlobCache(cache_dir, ttl_minutes=cache_ttl_minutes) if cache_dir else None

    @classmethod
    def from_env(cls, *, cache_dir: Path | None = None, system: bool = False) -> AsyncSharePointBlobStorage:
        """Instancia a partir das variáveis de ambiente CONCILIUM__SP_* — ver
        `SharePointBlobStorage.from_env` (mesma semântica, versão assíncrona)."""
        sp = get_storage().sharepoint
        drive_id = sp.system_drive_id if system else sp.drive_id
        root_path = sp.system_root_path if system else sp.root_path
        if not drive_id:
            env_var = "CONCILIUM__SP_SYSTEM_DRIVE_ID ou CONCILIUM__SP_DRIVE_ID" if system else "CONCILIUM__SP_DRIVE_ID"
            raise OSError(f"{env_var} é obrigatório.")
        return cls(
            drive_id=drive_id,
            root_path=root_path,
            credential=SharePointCredential.from_env(),
            cache_dir=cache_dir,
        )

    # ── HTTP helpers ───────────────────────────────────────────────────────

    async def _headers(self, extra: dict | None = None) -> dict[str, str]:
        # ADR-180 D3: MSAL não é async-native — roda em thread, com timeout
        # próprio (_MSAL_HTTP_TIMEOUT_S=15s) já configurado na credencial.
        token = await asyncio.to_thread(self._credential.acquire_token)
        h = {"Authorization": f"Bearer {token}"}
        if extra:
            h.update(extra)
        return h

    def _item_url(self, path: str) -> str:
        safe = path.strip("/")
        return f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}/{safe}"

    def _item_content_url(self, path: str) -> str:
        return f"{self._item_url(path)}:/content"

    async def _get_with_retry(
        self, url: str, headers: dict[str, str], params: dict[str, str] | None = None
    ) -> Any:
        """GET com retry/backoff em erros transitórios do Graph — espelho async de
        `SharePointBlobStorage._get_with_retry`, usando `asyncio.sleep` (não
        bloqueia o event loop durante o backoff, diferente de `time.sleep`).

        Toda a sequência de tentativas roda sob `_concurrency_limiter` — mesmo
        racional do módulo síncrono (ver sharepoint.py, incidente 2026-08-11).
        """
        import httpx

        last_response = None
        async with _concurrency_limiter, httpx.AsyncClient() as client:
            for attempt, delay in enumerate((*_TRANSIENT_RETRY_DELAYS_S, None)):
                r = await client.get(
                    url, headers=headers, params=params, follow_redirects=True, timeout=_READ_TIMEOUT_S
                )
                if r.status_code not in _TRANSIENT_STATUS_CODES:
                    return r
                last_response = r
                if delay is not None:
                    wait_s = _retry_after_seconds(r, delay)
                    logger.warning(
                        "SharePoint (async): status %s transitório (tentativa %d/%d) — retry em %.1fs%s",
                        r.status_code,
                        attempt + 1,
                        len(_TRANSIENT_RETRY_DELAYS_S) + 1,
                        wait_s,
                        " (Retry-After respeitado)" if wait_s != delay else "",
                    )
                    await asyncio.sleep(wait_s)
        return last_response

    def _raise_for_read_status(self, r: Any, path: str) -> None:
        """Como `SharePointBlobStorage._raise_for_read_status` — erros de leitura
        persistentes (não 404) viram StorageUnavailableError."""
        try:
            r.raise_for_status()
        except Exception as exc:
            raise StorageUnavailableError(
                f"SharePoint indisponível ao ler '{path}' (status={r.status_code}): {exc}"
            ) from exc

    # ── AsyncBlobStoragePort ─────────────────────────────────────────────────

    async def ler_blob(self, path: str) -> bytes:
        """Lê blob do SharePoint com cache ETag + TTL — espelho async de `ler_blob`."""
        if self._cache:
            result = await self._ler_blob_cached(path)
            if result is not None:
                return result
        return await self._ler_blob_direct(path)

    async def _ler_blob_cached(self, path: str) -> bytes | None:
        cache = self._cache
        assert cache is not None, "cache deve ser não-None quando _ler_blob_cached é chamado"
        cached = cache.get(path)
        if cached:
            content, meta = cached
            import httpx

            try:
                headers = await self._headers({"If-None-Match": meta.etag})
                async with httpx.AsyncClient() as client:
                    r = await client.get(
                        self._item_url(path),
                        headers=headers,
                        follow_redirects=True,
                        timeout=_READ_TIMEOUT_S,
                    )
                    if r.status_code == 304:
                        return content
                    if r.status_code == 200:
                        etag = r.headers.get("ETag", meta.etag)
                        lm = r.headers.get("Last-Modified", meta.last_modified)
                        content_r = await client.get(
                            self._item_content_url(path),
                            headers=await self._headers(),
                            follow_redirects=True,
                            timeout=_READ_TIMEOUT_S,
                        )
                        if content_r.status_code == 200:
                            cache.put(path, content_r.content, etag, lm)
                            return content_r.content
            except Exception:
                if self._offline:
                    stale = cache.get_stale(path)
                    if stale:
                        logger.warning(f"SharePoint (async) offline — usando cache expirado: {path}")
                        return stale[0]
                raise
        return None

    async def _ler_blob_direct(self, path: str) -> bytes:
        if self._offline:
            if self._cache:
                stale = self._cache.get_stale(path)
                if stale:
                    return stale[0]
            raise FileNotFoundError(f"Modo offline: blob não encontrado no cache: {path}")
        try:
            headers = await self._headers()
            r = await self._get_with_retry(self._item_content_url(path), headers)
        except Exception as exc:
            raise FileNotFoundError(f"Erro ao acessar SharePoint (async) para {path}: {exc}") from exc
        if r.status_code == 404:
            raise FileNotFoundError(f"Blob não encontrado no SharePoint: {path}")
        self._raise_for_read_status(r, path)
        content = r.content
        if self._cache:
            etag = r.headers.get("ETag", "")
            lm = r.headers.get("Last-Modified", "")
            self._cache.put(path, content, etag, lm)
        return content

    async def gravar_blob(self, path: str, content: bytes) -> None:
        """Grava blob no SharePoint — espelho async de `gravar_blob`."""
        if self._read_only:
            raise PermissionError(f"Storage configurado como read-only: {path}")

        if len(content) < _LARGE_FILE_THRESHOLD:
            await self._gravar_pequeno(path, content)
        else:
            await self._gravar_upload_session(path, content)

        if self._cache:
            self._cache.invalidate(path)

    async def _gravar_pequeno(self, path: str, content: bytes) -> None:
        import httpx

        headers = await self._headers({"Content-Type": "application/octet-stream"})
        async with httpx.AsyncClient() as client:
            r = await client.put(
                self._item_content_url(path),
                headers=headers,
                content=content,
                timeout=_WRITE_TIMEOUT_S,
            )
        if r.status_code == 412:
            raise StorageConcurrencyError(
                f"Conflito de escrita (ETag mismatch) para {path}. Outro agente gravou o arquivo concorrentemente."
            )
        r.raise_for_status()

    async def _gravar_upload_session(self, path: str, content: bytes) -> None:
        import httpx

        async with httpx.AsyncClient() as client:
            headers = await self._headers({"Content-Type": "application/json"})
            r = await client.post(
                f"{self._item_url(path)}:/createUploadSession",
                headers=headers,
                json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
                timeout=_WRITE_TIMEOUT_S,
            )
            r.raise_for_status()
            upload_url = r.json()["uploadUrl"]

            chunk_size = 5 * 1024 * 1024  # 5 MB
            total = len(content)
            offset = 0
            while offset < total:
                chunk = content[offset : offset + chunk_size]
                end = offset + len(chunk) - 1
                chunk_headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{total}",
                    "Content-Type": "application/octet-stream",
                }
                r = await client.put(upload_url, headers=chunk_headers, content=chunk, timeout=_WRITE_TIMEOUT_S)
                r.raise_for_status()
                offset += len(chunk)

    async def listar_blobs(self, prefix: str) -> list[str]:
        """Lista blobs com prefixo via children API com paginação — espelho
        async de `listar_blobs`."""
        safe = prefix.strip("/")
        url = (
            f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}/{safe}:/children"
            if safe
            else f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}:/children"
        )
        results: list[str] = []

        while url:
            try:
                headers = await self._headers()
                r = await self._get_with_retry(url, headers, params={"$select": "name,folder,file", "$top": "200"})
            except Exception as exc:
                if self._offline and self._cache:
                    logger.warning(f"SharePoint (async) offline — listar_blobs({prefix}) retorna lista vazia.")
                    return []
                raise FileNotFoundError(f"Erro ao listar SharePoint {prefix}: {exc}") from exc

            if r.status_code == 404:
                return []
            self._raise_for_read_status(r, prefix)
            data = r.json()

            for item in data.get("value", []):
                item_path = f"{safe}/{item['name']}".lstrip("/") if safe else item["name"]
                if "folder" in item:
                    sub = await self.listar_blobs(item_path)
                    results.extend(sub)
                else:
                    results.append(item_path)

            url = data.get("@odata.nextLink")  # pagination

        return results

    async def blob_existe(self, path: str) -> bool:
        """Verifica existência — sempre consulta a API (sem cache) — espelho
        async de `blob_existe`."""
        import httpx

        try:
            headers = await self._headers()
            async with httpx.AsyncClient() as client:
                r = await client.get(self._item_url(path), headers=headers, timeout=_READ_TIMEOUT_S)
            return r.status_code == 200
        except Exception:
            return False

    async def deletar_blob(self, path: str) -> None:
        """Remove um item do SharePoint via Graph DELETE — espelho async de
        `deletar_blob`."""
        import httpx

        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            r = await client.delete(self._item_url(path), headers=headers, timeout=_READ_TIMEOUT_S)
        if r.status_code == 404:
            raise FileNotFoundError(f"Blob não encontrado para deletar: {path}")
        if r.status_code not in (200, 204):
            r.raise_for_status()
        if self._cache:
            self._cache.invalidate(path)

    async def aprovar_versao(self, path: str) -> None:
        """Checkin de versão major no SharePoint — espelho async de `aprovar_versao`."""
        import httpx

        async with httpx.AsyncClient() as client:
            try:
                headers = await self._headers()
                await client.post(f"{self._item_url(path)}:/checkout", headers=headers, timeout=_READ_TIMEOUT_S)
            except Exception as exc:  # noqa: BLE001 — best-effort, checkin reporta o erro real
                logger.debug("checkout (async) best-effort falhou para '%s' (seguindo para checkin): %s", path, exc)

            headers = await self._headers({"Content-Type": "application/json"})
            r = await client.post(
                f"{self._item_url(path)}:/checkin",
                headers=headers,
                json={"checkInAs": "majorVersion", "comment": "Aprovado via Concilium"},
                timeout=_READ_TIMEOUT_S,
            )
        if r.status_code == 404:
            raise FileNotFoundError(f"Arquivo não encontrado para aprovar: {path}")
        r.raise_for_status()

    async def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900, *, scope: str = "anonymous") -> str | None:
        """Cria um sharing link de leitura com expiração — espelho async de
        `gerar_url_temporaria`."""
        from datetime import datetime, timedelta

        import httpx

        exp = (datetime.now(UTC) + timedelta(seconds=max(60, ttl_segundos))).isoformat()
        try:
            headers = await self._headers({"Content-Type": "application/json"})
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"{self._item_url(path)}:/createLink",
                    headers=headers,
                    json={"type": "view", "scope": scope, "expirationDateTime": exp},
                    timeout=_READ_TIMEOUT_S,
                )
            if r.status_code in (200, 201):
                return (r.json().get("link") or {}).get("webUrl")
            logger.warning(
                "gerar_url_temporaria (async) '%s': Graph createLink retornou %d: %s",
                path,
                r.status_code,
                r.text[:500],
            )
        except Exception:
            logger.warning("gerar_url_temporaria (async) '%s': falha ao chamar Graph createLink.", path, exc_info=True)
            return None
        return None

    async def ensure_root_path(self) -> None:
        """Cria root_path no SharePoint se não existir — espelho async de
        `ensure_root_path` (não faz parte de `AsyncBlobStoragePort`, é específico
        de SharePoint, como na versão síncrona)."""
        if not self._root_path:
            return
        import httpx

        async with httpx.AsyncClient() as client:
            headers = await self._headers()
            r = await client.get(
                f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}",
                headers=headers,
                timeout=10.0,
            )
            if r.status_code == 200:
                return
            if r.status_code != 404:
                r.raise_for_status()
            segments = self._root_path.split("/")
            current = ""
            for segment in segments:
                if current:
                    url = f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{current}:/children"
                else:
                    url = f"{_GRAPH_BASE}/drives/{self._drive_id}/root/children"
                headers = await self._headers({"Content-Type": "application/json"})
                r = await client.post(
                    url,
                    headers=headers,
                    json={"name": segment, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"},
                    timeout=10.0,
                )
                if r.status_code not in (200, 201):
                    r.raise_for_status()
                current = f"{current}/{segment}".lstrip("/") if current else segment
        logger.info("SharePoint (async) root_path criado: %s", self._root_path)

    async def health_check(self) -> dict[str, Any]:
        """Verifica conectividade com o SharePoint Drive — espelho async de
        `health_check`."""
        import httpx

        try:
            headers = await self._headers()
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{_GRAPH_BASE}/drives/{self._drive_id}",
                    headers=headers,
                    timeout=10.0,
                )
            if r.status_code == 200:
                data = r.json()
                return {
                    "status": "ok",
                    "drive_name": data.get("name", ""),
                    "drive_type": data.get("driveType", ""),
                    "backend": "sharepoint",
                }
            return {"status": "error", "code": r.status_code, "backend": "sharepoint"}
        except Exception as exc:
            return {"status": "error", "message": str(exc), "backend": "sharepoint"}


__all__ = ["AsyncSharePointBlobStorage"]
