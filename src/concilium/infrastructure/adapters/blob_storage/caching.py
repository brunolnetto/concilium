"""CachingBlobStorage — TTL in-memory read cache com offline fallback (issues #2/#3).

Wrap qualquer BlobStoragePort com cache TTL em memória e modo offline:
- `ler_blob` retorna do cache se fresco (< TTL); re-consulta backend na expiração.
- Se o backend falha com erro de infraestrutura, serve conteúdo stale do cache
  em vez de propagar exceção — mesmo comportamento do SharePointBlobStorage.offline.

Ativo via `CONCILIUM__BLOB_CACHE_TTL_SECONDS` (opt-in). Aplicado a S3, Azure e
GDrive por `store_factory.build_blob_storage()` — SharePoint já tem ETag cache próprio.
`gravar_blob` e `deletar_blob` delegam ao backend e atualizam/invalidam o cache local.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort, StorageUnavailableError

_DEFAULT_TTL_SECONDS = 300.0


class CachingBlobStorage(BlobStoragePort):
    """BlobStoragePort com TTL in-memory cache e fallback offline para qualquer backend."""

    def __init__(self, backend: BlobStoragePort, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self._backend = backend
        self._ttl = ttl_seconds
        # {path: (content, expire_monotonic)}
        self._cache: dict[str, tuple[bytes, float]] = {}
        self._lock = threading.Lock()

    # ── cache helpers ──────────────────────────────────────────────────────

    def _fresh(self, path: str) -> bytes | None:
        entry = self._cache.get(path)
        if entry and time.monotonic() <= entry[1]:
            return entry[0]
        return None

    def _stale(self, path: str) -> bytes | None:
        entry = self._cache.get(path)
        return entry[0] if entry else None

    def _put(self, path: str, content: bytes) -> None:
        with self._lock:
            self._cache[path] = (content, time.monotonic() + self._ttl)

    def _evict(self, path: str) -> None:
        with self._lock:
            self._cache.pop(path, None)

    # ── BlobStoragePort ────────────────────────────────────────────────────

    def ler_blob(self, path: str) -> bytes:
        with self._lock:
            fresh = self._fresh(path)
        if fresh is not None:
            return fresh
        try:
            content = self._backend.ler_blob(path)
            self._put(path, content)
            return content
        except FileNotFoundError:
            raise
        except Exception as exc:
            # Infraestrutura indisponível — serve conteúdo stale se disponível.
            with self._lock:
                stale = self._stale(path)
            if stale is not None:
                return stale
            raise StorageUnavailableError(
                f"Backend indisponível e sem cache local para '{path}': {exc}"
            ) from exc

    def gravar_blob(self, path: str, content: bytes) -> None:
        self._backend.gravar_blob(path, content)
        self._put(path, content)

    def listar_blobs(self, prefix: str) -> list[str]:
        return self._backend.listar_blobs(prefix)

    def blob_existe(self, path: str) -> bool:
        return self._backend.blob_existe(path)

    def deletar_blob(self, path: str) -> None:
        self._backend.deletar_blob(path)
        self._evict(path)

    def aprovar_versao(self, path: str) -> None:
        self._backend.aprovar_versao(path)

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900, *, scope: str = "anonymous") -> str | None:
        return self._backend.gerar_url_temporaria(path, ttl_segundos, scope=scope)

    def health_check(self) -> dict[str, Any]:
        result = self._backend.health_check()
        result["cache_ttl_seconds"] = self._ttl
        result["cache_entries"] = len(self._cache)
        return result
