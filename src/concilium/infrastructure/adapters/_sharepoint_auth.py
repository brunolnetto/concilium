"""Autenticação e cache para SharePoint (ADR-047). Extraído de sharepoint_blob_storage."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = __import__("logging").getLogger(__name__)
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"


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
