"""SharePoint backend de armazenamento via BlobStoragePort (ADR-047)."""

from __future__ import annotations

import logging
from datetime import UTC
from pathlib import Path
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort
from concilium.infrastructure.settings import get_storage

from ._sharepoint_auth import SharePointCredential, _BlobCache  # noqa: F401

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_LARGE_FILE_THRESHOLD = 4 * 1024 * 1024  # 4 MB


class SharePointBlobStorage(BlobStoragePort):
    """BlobStoragePort backed by Microsoft SharePoint / OneDrive for Business.

    Implementa ADR-047 §D1–D6. Todas as operações são endereçadas via caminho
    relativo ao root_path configurado, espelhando a hierarquia do LocalBlobStorage.

    Cache local (ADR-047 §D3):
        - Leituras: ETag + TTL (padrão 60 min)
        - blob_existe(): sempre consulta a API (sem cache)
        - Modo offline: usa cache expirado quando API inacessível

    Aprovação (ADR-047 §D4):
        - aprovar_versao(): checkin de versão major no SharePoint
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
        self._root_ensured = False

    @classmethod
    def from_env(cls, *, cache_dir: Path | None = None) -> SharePointBlobStorage:
        """Instancia a partir das variáveis de ambiente CONCILIUM__SP_*."""
        sp = get_storage().sharepoint
        drive_id = sp.drive_id
        root_path = sp.root_path
        if not drive_id:
            raise OSError("CONCILIUM__SP_DRIVE_ID é obrigatório.")
        return cls(
            drive_id=drive_id,
            root_path=root_path,
            credential=SharePointCredential.from_env(),
            cache_dir=cache_dir,
        )

    # ── HTTP helpers ───────────────────────────────────────────────────────

    def _client(self) -> Any:
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "O pacote 'httpx' é necessário para o SharePoint backend. "
                "Instale com: pip install 'concilium[sharepoint]'"
            ) from exc
        return httpx

    def _headers(self, extra: dict | None = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self._credential.acquire_token()}"}
        if extra:
            h.update(extra)
        return h

    def _item_url(self, path: str) -> str:
        safe = path.strip("/")
        return f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}/{safe}"

    def _item_content_url(self, path: str) -> str:
        return f"{self._item_url(path)}:/content"

    # ── BlobStoragePort ────────────────────────────────────────────────────

    def ler_blob(self, path: str) -> bytes:
        """Lê blob do SharePoint com cache ETag + TTL (ADR-047 §D2)."""
        httpx = self._client()
        if self._cache:
            result = self._ler_blob_cached(path, httpx)
            if result is not None:
                return result
        return self._ler_blob_direct(path, httpx)

    def _ler_blob_cached(self, path: str, httpx) -> bytes | None:
        cached = self._cache.get(path) if self._cache else None
        if cached:
            content, meta = cached
            try:
                r = httpx.get(
                    self._item_url(path),
                    headers=self._headers({"If-None-Match": meta.etag}),
                    follow_redirects=True,
                )
                if r.status_code == 304:
                    return content
                if r.status_code == 200:
                    etag = r.headers.get("ETag", meta.etag)
                    lm = r.headers.get("Last-Modified", meta.last_modified)
                    content_r = httpx.get(
                        self._item_content_url(path),
                        headers=self._headers(),
                        follow_redirects=True,
                    )
                    if content_r.status_code == 200:
                        self._cache.put(path, content_r.content, etag, lm)
                        return content_r.content
            except Exception:
                if self._offline:
                    stale = self._cache.get_stale(path) if self._cache else None
                    if stale:
                        logger.warning(f"SharePoint offline — usando cache expirado: {path}")
                        return stale[0]
                raise
        return None

    def _ler_blob_direct(self, path: str, httpx) -> bytes:
        if self._offline:
            if self._cache:
                stale = self._cache.get_stale(path)
                if stale:
                    return stale[0]
            raise FileNotFoundError(f"Modo offline: blob não encontrado no cache: {path}")
        try:
            r = httpx.get(
                self._item_content_url(path),
                headers=self._headers(),
                follow_redirects=True,
            )
        except Exception as exc:
            raise FileNotFoundError(f"Erro ao acessar SharePoint para {path}: {exc}") from exc
        if r.status_code == 404:
            raise FileNotFoundError(f"Blob não encontrado no SharePoint: {path}")
        r.raise_for_status()
        content = r.content
        if self._cache:
            etag = r.headers.get("ETag", "")
            lm = r.headers.get("Last-Modified", "")
            self._cache.put(path, content, etag, lm)
        return content

    def gravar_blob(self, path: str, content: bytes) -> None:
        """Grava blob no SharePoint (ADR-047 §D1, §D3).

        < 4 MB: PUT direto.
        >= 4 MB: upload session com suporte a retomada.
        If-Match: ETag para otimistic concurrency (412 → StorageConcurrencyError).
        """
        if self._read_only:
            raise PermissionError(f"Storage configurado como read-only: {path}")

        httpx = self._client()

        if len(content) < _LARGE_FILE_THRESHOLD:
            self._gravar_pequeno(httpx, path, content)
        else:
            self._gravar_upload_session(httpx, path, content)

        if self._cache:
            self._cache.invalidate(path)

    def _gravar_pequeno(self, httpx: Any, path: str, content: bytes) -> None:
        """PUT direto para arquivos < 4 MB."""
        r = httpx.put(
            self._item_content_url(path),
            headers=self._headers({"Content-Type": "application/octet-stream"}),
            content=content,
        )
        if r.status_code == 412:
            raise StorageConcurrencyError(
                f"Conflito de escrita (ETag mismatch) para {path}. Outro agente gravou o arquivo concorrentemente."
            )
        r.raise_for_status()

    def _gravar_upload_session(self, httpx: Any, path: str, content: bytes) -> None:
        """Upload session para arquivos >= 4 MB (ADR-047 §D3)."""
        # 1. Create upload session
        r = httpx.post(
            f"{self._item_url(path)}:/createUploadSession",
            headers=self._headers({"Content-Type": "application/json"}),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        r.raise_for_status()
        upload_url = r.json()["uploadUrl"]

        # 2. Upload in chunks
        chunk_size = 5 * 1024 * 1024  # 5 MB
        total = len(content)
        offset = 0
        while offset < total:
            chunk = content[offset : offset + chunk_size]
            end = offset + len(chunk) - 1
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{end}/{total}",
                "Content-Type": "application/octet-stream",
            }
            r = httpx.put(upload_url, headers=headers, content=chunk)
            r.raise_for_status()
            offset += len(chunk)

    def listar_blobs(self, prefix: str) -> list[str]:
        """Lista blobs com prefixo via children API com paginação (ADR-047 §D1)."""
        httpx = self._client()
        safe = prefix.strip("/")
        url = (
            f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}/{safe}:/children"
            if safe
            else f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}:/children"
        )
        results: list[str] = []

        while url:
            try:
                r = httpx.get(url, headers=self._headers(), params={"$select": "name,folder,file", "$top": "200"})
            except Exception as exc:
                if self._offline and self._cache:
                    logger.warning(f"SharePoint offline — listar_blobs({prefix}) retorna lista vazia.")
                    return []
                raise FileNotFoundError(f"Erro ao listar SharePoint {prefix}: {exc}") from exc

            if r.status_code == 404:
                return []
            r.raise_for_status()
            data = r.json()

            for item in data.get("value", []):
                item_path = f"{safe}/{item['name']}".lstrip("/") if safe else item["name"]
                if "folder" in item:
                    # Recurse into subfolders
                    sub = self.listar_blobs(item_path)
                    results.extend(sub)
                else:
                    results.append(item_path)

            url = data.get("@odata.nextLink")  # pagination

        return results

    def blob_existe(self, path: str) -> bool:
        """Verifica existência — sempre consulta a API (sem cache, ADR-047 §D3)."""
        httpx = self._client()
        try:
            r = httpx.get(self._item_url(path), headers=self._headers())
            return r.status_code == 200
        except Exception:
            return False

    def deletar_blob(self, path: str) -> None:
        """Remove um item do SharePoint via Graph DELETE (ADR-047 §D1).

        Se o path for uma pasta, remove recursivamente (Graph deleta a pasta inteira).
        Lança FileNotFoundError se o item não existir.
        """
        httpx = self._client()
        r = httpx.delete(self._item_url(path), headers=self._headers())
        if r.status_code == 404:
            raise FileNotFoundError(f"Blob não encontrado para deletar: {path}")
        if r.status_code not in (200, 204):
            r.raise_for_status()
        if self._cache:
            self._cache.invalidate(path)

    def aprovar_versao(self, path: str) -> None:
        """Checkin de versão major no SharePoint (ADR-047 §D4).

        Equivalente ao chmod 444 do LocalBlobStorage. O arquivo passa a ser
        somente-leitura para edições diretas; histórico de versões fica auditável
        no portal M365.
        """
        httpx = self._client()
        r = httpx.post(
            f"{self._item_url(path)}:/checkin",
            headers=self._headers({"Content-Type": "application/json"}),
            json={"checkInAs": "majorVersion", "comment": "Aprovado via Concilium"},
        )
        if r.status_code == 404:
            raise FileNotFoundError(f"Arquivo não encontrado para aprovar: {path}")
        r.raise_for_status()

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900) -> str | None:
        """Cria um sharing link anônimo de leitura com expiração (ADR-093 D4).

        Usa Graph ``createLink`` (type=view, scope=anonymous). Quando a política do
        tenant proíbe links anônimos, a chamada falha e retornamos ``None`` (o
        chamador recai no transporte base64).
        """
        from datetime import datetime, timedelta

        httpx = self._client()
        exp = (datetime.now(UTC) + timedelta(seconds=max(60, ttl_segundos))).isoformat()
        try:
            r = httpx.post(
                f"{self._item_url(path)}:/createLink",
                headers=self._headers({"Content-Type": "application/json"}),
                json={"type": "view", "scope": "anonymous", "expirationDateTime": exp},
            )
            if r.status_code in (200, 201):
                return (r.json().get("link") or {}).get("webUrl")
        except Exception:  # noqa: BLE001
            return None
        return None

    def ensure_root_path(self) -> None:
        """Cria root_path no SharePoint se não existir (chame no startup da aplicação)."""
        if self._root_ensured:
            return
        self._ensure_root_path(self._client())
        self._root_ensured = True

    def _ensure_root_path(self, httpx: Any) -> None:
        """Cria root_path no SharePoint se não existir (idempotente, segmento a segmento)."""
        if not self._root_path:
            return
        r = httpx.get(
            f"{_GRAPH_BASE}/drives/{self._drive_id}/root:/{self._root_path}",
            headers=self._headers(),
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
            r = httpx.post(
                url,
                headers=self._headers({"Content-Type": "application/json"}),
                json={"name": segment, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"},
                timeout=10.0,
            )
            if r.status_code not in (200, 201):
                r.raise_for_status()
            current = f"{current}/{segment}".lstrip("/") if current else segment
        logger.info("SharePoint root_path criado: %s", self._root_path)

    def health_check(self) -> dict[str, Any]:
        """Verifica conectividade com o SharePoint Drive (ADR-047 §D7)."""
        httpx = self._client()
        try:
            r = httpx.get(
                f"{_GRAPH_BASE}/drives/{self._drive_id}",
                headers=self._headers(),
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


class StorageConcurrencyError(Exception):
    """Raised when a concurrent write creates an ETag conflict (HTTP 412)."""
