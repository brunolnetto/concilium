"""Porta de abstração assíncrona para Blob Storage (ADR-180 D1).

Coexiste com `BlobStoragePort` (síncrono, ADR-033/ADR-047) — não o substitui.
Espelha os mesmos métodos como `async def`, para backends cujo I/O real é de
rede e onde cancelamento cooperativo (`asyncio.wait_for`/`asyncio.CancelledError`)
precisa efetivamente interromper a chamada em andamento, não apenas abandonar
uma thread que continua rodando (ver ADR-180, P1/P4).

Hoje só existe uma implementação (`AsyncSharePointBlobStorage`) — os demais
backends (local, S3, Azure, GDrive, cloud) permanecem exclusivamente no port
síncrono; ver ADR-180 D6 para o critério de expansão.
"""

from abc import ABC, abstractmethod
from typing import Any

from .blob_storage_port import StorageUnavailableError  # noqa: F401 — reexport, mesmo erro do port síncrono


class AsyncBlobStoragePort(ABC):
    """Interface abstrata assíncrona para armazenamento de blobs (ADR-180 D1).

    Espelho 1:1 de `BlobStoragePort` — mesma semântica de cada método, só que
    `async def`. Ver `BlobStoragePort` para a documentação de contrato de cada
    operação (não duplicada aqui para evitar divergência de texto).
    """

    @abstractmethod
    async def ler_blob(self, path: str) -> bytes:
        """Ver `BlobStoragePort.ler_blob`."""
        ...

    @abstractmethod
    async def gravar_blob(self, path: str, content: bytes) -> None:
        """Ver `BlobStoragePort.gravar_blob`."""
        ...

    @abstractmethod
    async def listar_blobs(self, prefix: str) -> list[str]:
        """Ver `BlobStoragePort.listar_blobs`."""
        ...

    @abstractmethod
    async def blob_existe(self, path: str) -> bool:
        """Ver `BlobStoragePort.blob_existe`."""
        ...

    async def deletar_blob(self, path: str) -> None:
        """Ver `BlobStoragePort.deletar_blob`. Implementação padrão é noop."""
        return

    async def aprovar_versao(self, path: str) -> None:
        """Ver `BlobStoragePort.aprovar_versao`. Implementação padrão é noop."""
        return

    async def gerar_url_temporaria(self, path: str, ttl_segundos: int = 900, *, scope: str = "anonymous") -> str | None:
        """Ver `BlobStoragePort.gerar_url_temporaria`. Implementação padrão retorna None."""
        return None

    async def health_check(self) -> dict[str, Any]:
        """Ver `BlobStoragePort.health_check`. Implementação padrão é um stub."""
        return {"status": "ok", "backend": "unknown"}


__all__ = ["AsyncBlobStoragePort", "StorageUnavailableError"]
