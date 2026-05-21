"""ADR-047 — SharePoint como backend de armazenamento via BlobStoragePort.

Implementa BlobStoragePort sobre o Microsoft Graph API (SharePoint/OneDrive for Business).
Autenticação via MSAL client credentials flow (Service Principal).
HTTP via httpx com cache local por ETag + TTL.

Dependências opcionais — instalar com:
    pip install concilium[sharepoint]
    # ou: pip install msal httpx

Variáveis de ambiente:
    CONCILIUM_SP_TENANT_ID     — tenant UUID
    CONCILIUM_SP_CLIENT_ID     — App Registration UUID
    CONCILIUM_SP_CLIENT_SECRET — secret (dev/CI)
    CONCILIUM_SP_CERT_PATH     — caminho do certificado PEM (produção — preferido)
    CONCILIUM_SP_DRIVE_ID      — ID do Drive SharePoint
    CONCILIUM_SP_ROOT_PATH     — caminho base no Drive (ex: Concilium/producao)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_LARGE_FILE_THRESHOLD = 4 * 1024 * 1024  # 4 MB


# ── Auth ──────────────────────────────────────────────────────────────────────


@dataclass
class SharePointCredential:
    """Credencial de Service Principal para autenticação no Microsoft Graph.

    Usa MSAL ConfidentialClientApplication com client credentials flow (app-only).
    O token é cacheado internamente pelo MSAL e renovado automaticamente antes da
    expiração (padrão 60 min).

    Uso:
        cred = SharePointCredential.from_env()
        token = cred.acquire_token()
    """

    tenant_id: str
    client_id: str
    client_secret: str | None = None
    cert_path: Path | None = None  # PEM — preferido em produção

    _app: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.client_secret and not self.cert_path:
            raise ValueError("SharePointCredential requer client_secret ou cert_path.")

    @classmethod
    def from_env(cls) -> SharePointCredential:
        """Instancia a partir das variáveis de ambiente CONCILIUM_SP_*."""
        tenant_id = os.environ.get("CONCILIUM_SP_TENANT_ID", "")
        client_id = os.environ.get("CONCILIUM_SP_CLIENT_ID", "")
        secret = os.environ.get("CONCILIUM_SP_CLIENT_SECRET")
        cert = os.environ.get("CONCILIUM_SP_CERT_PATH")
        if not tenant_id or not client_id:
            raise OSError("CONCILIUM_SP_TENANT_ID e CONCILIUM_SP_CLIENT_ID são obrigatórios.")
        return cls(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=secret,
            cert_path=Path(cert) if cert else None,
        )

    def acquire_token(self) -> str:
        """Retorna Bearer token válido. Renova automaticamente via cache MSAL."""
        if self._app is None:
            try:
                import msal
            except ImportError as exc:
                raise ImportError(
                    "O pacote 'msal' é necessário para autenticação SharePoint. "
                    "Instale com: pip install 'concilium[sharepoint]'"
                ) from exc

            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            if self.cert_path and self.cert_path.exists():
                cert_pem = self.cert_path.read_text()
                self._app = msal.ConfidentialClientApplication(
                    self.client_id,
                    authority=authority,
                    client_credential={"private_key": cert_pem, "thumbprint": ""},
                )
            else:
                self._app = msal.ConfidentialClientApplication(
                    self.client_id,
                    authority=authority,
                    client_credential=self.client_secret,
                )

        result = self._app.acquire_token_for_client(scopes=[_GRAPH_SCOPE])
        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "auth_failed"))
            raise PermissionError(f"Falha na autenticação SharePoint: {error}")
        return str(result["access_token"])


# ── Cache ─────────────────────────────────────────────────────────────────────


@dataclass
class _CacheMeta:
    etag: str
    last_modified: str
    cached_at: float  # unix timestamp


class _BlobCache:
    """Cache local de blobs por ETag + TTL (ADR-047 §D3)."""

    def __init__(self, cache_dir: Path, ttl_minutes: int = 60) -> None:
        self._dir = cache_dir
        self._ttl = timedelta(minutes=ttl_minutes)
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _key(self, path: str) -> str:
        return hashlib.sha256(path.encode()).hexdigest()[:24]

    def _blob_path(self, path: str) -> Path:
        return self._dir / f"{self._key(path)}.blob"

    def _meta_path(self, path: str) -> Path:
        return self._dir / f"{self._key(path)}.meta"

    def get(self, path: str) -> tuple[bytes, _CacheMeta] | None:
        blob_p, meta_p = self._blob_path(path), self._meta_path(path)
        if not blob_p.exists() or not meta_p.exists():
            return None
        try:
            meta = _CacheMeta(**json.loads(meta_p.read_text(encoding="utf-8")))
            age = datetime.now(UTC) - datetime.fromtimestamp(meta.cached_at, tz=UTC)
            if age > self._ttl:
                return None  # TTL expired
            return blob_p.read_bytes(), meta
        except Exception:
            return None

    def get_stale(self, path: str) -> tuple[bytes, _CacheMeta] | None:
        """Retorna o cache mesmo expirado (modo offline)."""
        blob_p, meta_p = self._blob_path(path), self._meta_path(path)
        if not blob_p.exists() or not meta_p.exists():
            return None
        try:
            meta = _CacheMeta(**json.loads(meta_p.read_text(encoding="utf-8")))
            return blob_p.read_bytes(), meta
        except Exception:
            return None

    def put(self, path: str, content: bytes, etag: str, last_modified: str) -> None:
        meta = _CacheMeta(etag=etag, last_modified=last_modified, cached_at=time.time())
        self._blob_path(path).write_bytes(content)
        self._meta_path(path).write_text(
            json.dumps({"etag": meta.etag, "last_modified": meta.last_modified, "cached_at": meta.cached_at}),
            encoding="utf-8",
        )

    def invalidate(self, path: str) -> None:
        for p in (self._blob_path(path), self._meta_path(path)):
            p.unlink(missing_ok=True)


# ── SharePointBlobStorage ─────────────────────────────────────────────────────


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

    @classmethod
    def from_env(cls, *, cache_dir: Path | None = None) -> SharePointBlobStorage:
        """Instancia a partir das variáveis de ambiente CONCILIUM_SP_*."""
        drive_id = os.environ.get("CONCILIUM_SP_DRIVE_ID", "")
        root_path = os.environ.get("CONCILIUM_SP_ROOT_PATH", "Concilium/producao")
        if not drive_id:
            raise OSError("CONCILIUM_SP_DRIVE_ID é obrigatório.")
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

        # Cache hit check
        if self._cache:
            cached = self._cache.get(path)
            if cached:
                content, meta = cached
                # ETag re-validation
                try:
                    r = httpx.get(
                        self._item_url(path),
                        headers=self._headers({"If-None-Match": meta.etag}),
                        follow_redirects=True,
                    )
                    if r.status_code == 304:
                        return content  # Cache valid
                    if r.status_code == 200:
                        # Refresh cache with new etag from item metadata
                        etag = r.headers.get("ETag", meta.etag)
                        lm = r.headers.get("Last-Modified", meta.last_modified)
                        # Need to fetch content separately
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
                        stale = self._cache.get_stale(path)
                        if stale:
                            logger.warning(f"SharePoint offline — usando cache expirado: {path}")
                            return stale[0]
                    raise

        if self._offline:
            if self._cache:
                stale = self._cache.get_stale(path)
                if stale:
                    return stale[0]
            raise FileNotFoundError(f"Modo offline: blob não encontrado no cache: {path}")

        try:
            # Direct download
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
