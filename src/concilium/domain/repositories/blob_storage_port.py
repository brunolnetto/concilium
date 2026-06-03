"""Porta de abstração para Blob Storage (ADR-033 §D1)."""

from abc import ABC, abstractmethod


class BlobStoragePort(ABC):
    """Interface abstrata para armazenamento de blobs (arquivos brutos).

    Obriga o isolamento do filesystem local e permite acoplar Google Drive,
    SharePoint ou S3 sem alterar o código de domínio.
    """

    @abstractmethod
    def ler_blob(self, path: str) -> bytes:
        """Lê o conteúdo binário de um blob.

        Args:
            path: Caminho ou chave do blob (ex: 'catalogo/insumos.json').

        Raises:
            FileNotFoundError: Se o blob não for encontrado.
        """
        ...

    @abstractmethod
    def gravar_blob(self, path: str, content: bytes) -> None:
        """Grava conteúdo binário em um blob, sobrescrevendo se existir."""
        ...

    @abstractmethod
    def listar_blobs(self, prefix: str) -> list[str]:
        """Lista os caminhos/chaves de todos os blobs com o prefixo dado."""
        ...

    @abstractmethod
    def blob_existe(self, path: str) -> bool:
        """Retorna True se o blob existir no storage."""
        ...

    def aprovar_versao(self, path: str) -> None:
        """Marca o blob como versão aprovada (imutável).

        Local: chmod 444. SharePoint: checkin de versão major.
        Implementação padrão é noop — backends que suportam aprovação devem sobrescrever.
        """
        return
