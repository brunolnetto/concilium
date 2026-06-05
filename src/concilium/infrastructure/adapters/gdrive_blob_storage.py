"""Google Drive backend via BlobStoragePort (ADR-093 D4).

Mapeia o modelo de caminhos (``a/b/arquivo.ext``) sobre o Drive (pastas e arquivos
por ID): pastas são resolvidas/criadas sob um folder raiz; o último segmento é o
arquivo. Autenticação via service account (recomendado para serviço headless).

Limitação de URL: o Drive não tem URL pré-assinada com TTL como Azure SAS/S3. A
``gerar_url_temporaria`` cria uma permissão "anyone with link / reader" e devolve o
``webContentLink`` (download direto). Em Workspace, aplica ``expirationTime``; fora
dele, o link não expira sozinho — o chamador deve revogar quando apropriado.
"""

from __future__ import annotations

import io
import os
from datetime import UTC
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

_FOLDER_MIME = "application/vnd.google-apps.folder"


class GoogleDriveBlobStorage(BlobStoragePort):
    """BlobStoragePort backed by Google Drive (sob um folder raiz)."""

    def __init__(
        self,
        *,
        root_folder_id: str,
        service_account_json: str | None = None,
        ttl_dias_link: int = 7,
    ) -> None:
        self._root_folder_id = root_folder_id
        self._sa_json = service_account_json
        self._ttl_dias_link = ttl_dias_link
        self._svc: Any = None  # lazy
        self._folder_cache: dict[str, str] = {"": root_folder_id}

    @classmethod
    def from_env(cls) -> GoogleDriveBlobStorage:
        root = (os.environ.get("CONCILIUM__GDRIVE_ROOT_FOLDER_ID") or "").strip()
        if not root:
            raise OSError("CONCILIUM__GDRIVE_ROOT_FOLDER_ID é obrigatório para o backend Google Drive.")
        return cls(
            root_folder_id=root,
            service_account_json=(os.environ.get("CONCILIUM__GDRIVE_SA_JSON") or "").strip() or None,
        )

    # ── SDK / serviço ───────────────────────────────────────────────────────

    def _service(self) -> Any:
        if self._svc is not None:
            return self._svc
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise ImportError(
                "Os pacotes 'google-api-python-client' e 'google-auth' são necessários para o "
                "backend Google Drive. Instale com: pip install 'concilium[gdrive]'"
            ) from exc

        scopes = ["https://www.googleapis.com/auth/drive"]
        if self._sa_json:
            creds = service_account.Credentials.from_service_account_file(self._sa_json, scopes=scopes)
        else:
            from google.auth import default as google_default

            creds, _ = google_default(scopes=scopes)
        self._svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._svc

    def _files(self) -> Any:
        return self._service().files()

    def _permissions(self) -> Any:
        return self._service().permissions()

    @staticmethod
    def _split(path: str) -> tuple[list[str], str]:
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            raise ValueError("Caminho de blob vazio.")
        return parts[:-1], parts[-1]

    def _resolve_folder(self, segments: list[str], *, create: bool) -> str | None:
        key = "/".join(segments)
        if key in self._folder_cache:
            return self._folder_cache[key]
        parent = self._root_folder_id
        acc: list[str] = []
        for seg in segments:
            acc.append(seg)
            acc_key = "/".join(acc)
            if acc_key in self._folder_cache:
                parent = self._folder_cache[acc_key]
                continue
            fid = self._find_child(parent, seg, folder=True)
            if fid is None:
                if not create:
                    return None
                fid = self._files().create(
                    body={"name": seg, "mimeType": _FOLDER_MIME, "parents": [parent]},
                    fields="id",
                    supportsAllDrives=True,
                ).execute()["id"]
            self._folder_cache[acc_key] = fid
            parent = fid
        return parent

    def _find_child(self, parent_id: str, name: str, *, folder: bool) -> str | None:
        mime = f" and mimeType {'=' if folder else '!='} '{_FOLDER_MIME}'"
        q = f"name = '{name}' and '{parent_id}' in parents and trashed = false{mime}"
        resp = (
            self._files()
            .list(q=q, fields="files(id,name)", spaces="drive", supportsAllDrives=True, includeItemsFromAllDrives=True)
            .execute()
        )
        files = resp.get("files", [])
        return files[0]["id"] if files else None

    def _file_id(self, path: str, *, create_folders: bool = False) -> str | None:
        segments, name = self._split(path)
        folder_id = self._resolve_folder(segments, create=create_folders)
        if folder_id is None:
            return None
        return self._find_child(folder_id, name, folder=False)

    # ── BlobStoragePort ────────────────────────────────────────────────────

    def ler_blob(self, path: str) -> bytes:
        from googleapiclient.http import MediaIoBaseDownload

        fid = self._file_id(path)
        if fid is None:
            raise FileNotFoundError(f"Blob não encontrado no Google Drive: {path}")
        request = self._files().get_media(fileId=fid, supportsAllDrives=True)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
        return buf.getvalue()

    def gravar_blob(self, path: str, content: bytes) -> None:
        from googleapiclient.http import MediaIoBaseUpload

        segments, name = self._split(path)
        folder_id = self._resolve_folder(segments, create=True)
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/octet-stream", resumable=False)
        existing = self._find_child(folder_id, name, folder=False) if folder_id else None
        if existing:
            self._files().update(fileId=existing, media_body=media, supportsAllDrives=True).execute()
        else:
            self._files().create(
                body={"name": name, "parents": [folder_id]},
                media_body=media,
                fields="id",
                supportsAllDrives=True,
            ).execute()

    def listar_blobs(self, prefix: str) -> list[str]:
        segments = [p for p in prefix.strip("/").split("/") if p]
        folder_id = self._resolve_folder(segments, create=False)
        if folder_id is None:
            return []
        results: list[str] = []
        self._walk(folder_id, "/".join(segments), results)
        return results

    def _walk(self, folder_id: str, prefix: str, out: list[str]) -> None:
        resp = (
            self._files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="files(id,name,mimeType)",
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        for f in resp.get("files", []):
            child_path = f"{prefix}/{f['name']}".lstrip("/")
            if f.get("mimeType") == _FOLDER_MIME:
                self._walk(f["id"], child_path, out)
            else:
                out.append(child_path)

    def blob_existe(self, path: str) -> bool:
        try:
            return self._file_id(path) is not None
        except Exception:  # noqa: BLE001
            return False

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900) -> str | None:
        """Cria permissão anyone/reader e devolve webContentLink (ADR-093 D4)."""
        try:
            fid = self._file_id(path)
            if fid is None:
                return None
            perm: dict[str, Any] = {"type": "anyone", "role": "reader"}
            # expirationTime só é aceito em contas Workspace e para roles específicas.
            try:
                from datetime import datetime, timedelta

                exp = datetime.now(UTC) + timedelta(seconds=max(3600, ttl_segundos))
                perm_exp = {**perm, "expirationTime": exp.isoformat()}
                self._permissions().create(fileId=fid, body=perm_exp, supportsAllDrives=True).execute()
            except Exception:  # noqa: BLE001 — fallback sem expiração
                self._permissions().create(fileId=fid, body=perm, supportsAllDrives=True).execute()
            meta = self._files().get(fileId=fid, fields="webContentLink,webViewLink", supportsAllDrives=True).execute()
            return meta.get("webContentLink") or meta.get("webViewLink")
        except Exception:  # noqa: BLE001
            return None
