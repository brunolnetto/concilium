"""Azure Blob Storage backend via BlobStoragePort (ADR-093 D4 / ADR-096).

Entrega de artefatos e persistência do ProjectStore na nuvem Azure. Gera URLs
pré-assinadas (SAS) com TTL para download direto por agentes/stakeholders.

Credenciais (em ordem de precedência):
  1. Connection string  (CONCILIUM__AZURE_CONNECTION_STRING)
  2. Account + key       (CONCILIUM__AZURE_ACCOUNT / CONCILIUM__AZURE_KEY)
  3. Managed Identity    (CONCILIUM__AZURE_ACCOUNT, sem key — usa DefaultAzureCredential)

SAS via account key (delegação por chave) ou user-delegation key (Managed Identity).
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort
from concilium.infrastructure.settings import get_storage


class AzureBlobStorage(BlobStoragePort):
    """BlobStoragePort backed by Azure Blob Storage (container privado)."""

    def __init__(
        self,
        *,
        container: str,
        account: str | None = None,
        account_key: str | None = None,
        connection_string: str | None = None,
        root_prefix: str = "",
    ) -> None:
        self._container = container
        self._account = account
        self._account_key = account_key
        self._connection_string = connection_string
        self._root_prefix = root_prefix.strip("/")
        self._service: Any = None  # lazy

    @classmethod
    def from_env(cls, *, system: bool = False) -> AzureBlobStorage:
        """Instancia a partir das variáveis de ambiente CONCILIUM__AZURE_*.

        system=True aponta para o container "sistema" (auth/config/distribuição),
        isolado do container de projetos — ver CONCILIUM__AZURE_SYSTEM_CONTAINER.
        """
        azure = get_storage().azure
        container = (azure.system_container if system else azure.container).strip()
        if not container:
            env_var = (
                "CONCILIUM__AZURE_SYSTEM_CONTAINER ou CONCILIUM__AZURE_CONTAINER"
                if system
                else "CONCILIUM__AZURE_CONTAINER"
            )
            raise OSError(f"{env_var} é obrigatório para o backend Azure Blob.")
        return cls(
            container=container,
            account=azure.account.strip() or None,
            account_key=azure.key.strip() or None,
            connection_string=azure.connection_string.strip() or None,
            root_prefix=(azure.system_root_prefix if system else azure.root_prefix).strip(),
        )

    # ── SDK / cliente ───────────────────────────────────────────────────────

    def _client(self) -> Any:
        if self._service is not None:
            return self._service
        try:
            from azure.storage.blob import BlobServiceClient  # ty: ignore[unresolved-import]
        except ImportError as exc:
            raise ImportError(
                "O pacote 'azure-storage-blob' é necessário para o backend Azure Blob. "
                "Instale com: pip install 'concilium[azure]'"
            ) from exc

        if self._connection_string:
            self._service = BlobServiceClient.from_connection_string(self._connection_string)
        elif self._account and self._account_key:
            self._service = BlobServiceClient(
                account_url=f"https://{self._account}.blob.core.windows.net",
                credential=self._account_key,
            )
        elif self._account:
            from azure.identity import DefaultAzureCredential  # Managed Identity  # ty: ignore[unresolved-import]

            self._service = BlobServiceClient(
                account_url=f"https://{self._account}.blob.core.windows.net",
                credential=DefaultAzureCredential(),
            )
        else:
            raise OSError(
                "Defina CONCILIUM__AZURE_CONNECTION_STRING, ou CONCILIUM__AZURE_ACCOUNT (+ "
                "CONCILIUM__AZURE_KEY ou Managed Identity)."
            )
        return self._service

    def _blob_client(self, path: str) -> Any:
        return self._client().get_blob_client(container=self._container, blob=self._full_key(path))

    def _full_key(self, path: str) -> str:
        safe = path.strip("/")
        return f"{self._root_prefix}/{safe}" if self._root_prefix and safe else (safe or self._root_prefix)

    # ── BlobStoragePort ────────────────────────────────────────────────────

    def ler_blob(self, path: str) -> bytes:
        try:
            from azure.core.exceptions import ResourceNotFoundError  # ty: ignore[unresolved-import]
        except ImportError as exc:
            raise ImportError(
                "O pacote 'azure-storage-blob' é necessário para o backend Azure Blob. "
                "Instale com: pip install 'concilium[azure]'"
            ) from exc

        try:
            return self._blob_client(path).download_blob().readall()
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(f"Blob não encontrado no Azure: {path}") from exc

    def gravar_blob(self, path: str, content: bytes) -> None:
        self._blob_client(path).upload_blob(content, overwrite=True)

    def listar_blobs(self, prefix: str) -> list[str]:
        container = self._client().get_container_client(self._container)
        full = self._full_key(prefix)
        names: list[str] = []
        for blob in container.list_blobs(name_starts_with=full):
            name = blob.name
            if self._root_prefix and name.startswith(f"{self._root_prefix}/"):
                name = name.removeprefix(f"{self._root_prefix}/")
            names.append(name)
        return names

    def blob_existe(self, path: str) -> bool:
        return bool(self._blob_client(path).exists())

    def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900, *, scope: str = "anonymous") -> str | None:
        """SAS URL de leitura com expiração (ADR-093 D4).

        `scope` é ignorado — SAS URLs não têm essa distinção (ver
        BlobStoragePort.gerar_url_temporaria).
        """
        try:
            from azure.storage.blob import BlobSasPermissions, generate_blob_sas  # ty: ignore[unresolved-import]
        except ImportError:
            return None

        bc = self._blob_client(path)
        key = self._full_key(path)
        # SAS por account key (direto) ou user-delegation key (Managed Identity).
        if self._account_key:
            sas = generate_blob_sas(
                account_name=bc.account_name,
                container_name=self._container,
                blob_name=key,
                account_key=self._account_key,
                permission=BlobSasPermissions(read=True),
                expiry=_expiry(ttl_segundos),
            )
        else:
            service = self._client()
            start = _now()
            udk = service.get_user_delegation_key(start, _expiry(ttl_segundos))
            sas = generate_blob_sas(
                account_name=bc.account_name,
                container_name=self._container,
                blob_name=key,
                user_delegation_key=udk,
                permission=BlobSasPermissions(read=True),
                expiry=_expiry(ttl_segundos),
            )
        return f"{bc.url}?{sas}"

    def health_check(self) -> dict[str, Any]:
        try:
            self._client().get_container_client(self._container).get_container_properties()
            return {"status": "ok", "backend": "azure_blob", "container": self._container}
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "backend": "azure_blob", "message": str(exc)}


def _now() -> Any:
    from datetime import datetime

    return datetime.now(UTC)


def _expiry(ttl_segundos: int) -> Any:
    from datetime import timedelta

    return _now() + timedelta(seconds=max(60, ttl_segundos))
